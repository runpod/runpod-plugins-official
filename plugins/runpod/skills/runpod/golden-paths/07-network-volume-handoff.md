---
lanes: [runpodctl, ssh, flash, runpod-mcp]
mcp: partial
concepts: [pod, network-volume, data-center, serverless-endpoint, worker, serverless-handler, flash, log-stream]
---

# Golden path 07 — network-volume handoff (pod → volume → serverless)

**Goal:** produce data on a **pod**, persist it to a **network volume**, and have a
**serverless endpoint** read that same data — the pattern behind "fine-tune on a pod,
then serve the adapter from an endpoint."
**Status:** COVERED — live-verified 2026-07-10 end to end (pod wrote `/workspace/hello.txt`;
a `runpod-flash` serverless worker read it back at `/runpod-volume/hello.txt` and returned the
exact contents). Step 3 is ported to the Runpod SDK (`runpod` 2.0.0rc1): on 2026-10-16 an SDK
app deployed with `rp flash deploy` wrote to a network volume from one endpoint and read the
exact contents back from another. Run it with `rp flash deploy`, not `rp flash dev`; dev
sessions on the built-in runtime images fail on volume apps (flash SKILL gotcha 14). The earlier read-back failures were a handler-signature / empty-input bug, not the
handoff — see [Root cause](#root-cause-why-the-reader-first-timed-out-found-via-mcp-worker-logs).
**Lane(s):** runpodctl (volume + pod) + flash (serverless reader) + Runpod MCP (`stream-worker-logs`, for diagnosis)

## When to use this
Any two-phase workflow where a pod produces an artifact and serverless consumes it:
fine-tune → serve the adapter, preprocess a dataset → batch-infer, download/convert a
model once → many endpoint workers reuse it. A network volume is the handoff medium.

## The one thing to get right: same volume, two mount paths

A network volume has **one identity (its ID)** but mounts at a **different path** on each
side (see [`../../runpod-usage/reference/storage.md`](../../runpod-usage/reference/storage.md)):

| Side | How it attaches | Mount path |
| --- | --- | --- |
| **Pod** | `runpodctl pod create --network-volume-id <id> --volume-mount-path /workspace` | **`/workspace`** (you choose it) |
| **Serverless** | attach the **same** volume id to the endpoint | **`/runpod-volume`** (fixed, not configurable) |

So a pod writing `/workspace/hello.txt` is read by the endpoint at
**`/runpod-volume/hello.txt`** — same bytes, different path. This is the gotcha to watch.
The volume is **pinned to one data center**; the pod AND the endpoint workers must run in
that DC.

## Prerequisites
- `RUNPOD_API_KEY` resolvable (runpodctl and the Runpod SDK both read it).
- `runpodctl` + the Runpod SDK installed (`pip install "runpod>=2.0.1"`, which provides `rp`).
- An SSH key registered **before** creating the pod — Runpod injects registered keys into
  the pod at startup, so a key added after boot won't work until a restart (`runpodctl ssh
  list-keys`; see
  [`../../runpod-usage/reference/getting-started.md`](../../runpod-usage/reference/getting-started.md)).

## Walkthrough (verified commands)

### 1. Create the volume
```bash
runpodctl network-volume create --name handoff-demo --size 10 --data-center-id EU-RO-1
# → id, e.g. uov9m8om3w, in EU-RO-1. Pin everything below to this DC.
```

### 2. Pod writes the artifact, then is removed (volume persists)
```bash
runpodctl pod create --name handoff-writer \
  --template-id runpod-torch-v280 --gpu-id "NVIDIA GeForce RTX 4090" \
  --data-center-ids EU-RO-1 \
  --network-volume-id <vol-id> --volume-mount-path /workspace \
  --ssh                                              # no --ports: nothing to serve

runpodctl pod get <pod-id>                            # poll until it has a runtime
# once the runtime is up, read ip / port / key from `ssh info` (JSON) into shell vars
# (the SSH-over-TCP form from golden path 06):
eval "$(runpodctl ssh info <pod-id> | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(f"IP={d[\"ip\"]} PORT={d[\"port\"]} KEY={d[\"ssh_key\"][\"path\"]}")')"
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" \
  'echo "handoff ok" > /workspace/hello.txt && cat /workspace/hello.txt'   # verify BEFORE removing

runpodctl pod remove <pod-id>                         # volume (and the file) persist
```
Verified: the file was written and read back on the pod (48 bytes), and after
`pod remove` the volume still listed — data persists independent of the pod.

### 3. Serverless endpoint attaches the SAME volume and reads at `/runpod-volume`
Use the **Runpod SDK** for a code-first reader. Reference the existing volume **by id** with
`create=False` (deterministic, and it fails instead of creating a new one), and pin the same DC:

```python
# main.py
import os
import runpod

app = runpod.App("handoff")

vol = runpod.NetworkVolume("<vol-id>", create=False)    # attach EXISTING by id (or name)

@app.queue(cpu="cpu3c-1-2", workers=(0, 1), datacenter="EU-RO-1",
           mounts={"/runpod-volume": vol})
def read(path: str = "hello.txt") -> dict:              # input keys = parameter names
    p = os.path.join("/runpod-volume", path)            # /runpod-volume, not /workspace
    return {"exists": os.path.exists(p),
            "content": open(p).read() if os.path.exists(p) else None,
            "runpod_volume_listing": sorted(os.listdir("/runpod-volume"))}

@runpod.local_entrypoint
def main():
    print(read.remote())
```
**Handler signature matters** — the worker calls the function as `read(**job_input)`, so
the request's `input` keys must be parameter names. A plain `def read(input: dict)` fails with
`read() got an unexpected keyword argument …`. See [Root cause](#root-cause-why-the-reader-first-timed-out-found-via-mcp-worker-logs).
```bash
rp flash deploy main.py          # app "handoff", environment "default"
runpodctl serverless list        # confirm the endpoint's networkVolumeId == your volume id
```
The `runpod-flash` run verified that the deployed endpoint reported `networkVolumeId` equal to
the volume the pod wrote to — the **same volume is attached to both sides**.

### 4. Invoke and read the artifact back
Send a **non-empty** `input` whose keys are the function's parameters (an empty `{}` is
rejected by the worker SDK as "missing input"):
```bash
curl -s https://api.runpod.ai/v2/<endpoint-id>/run -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -d '{"input":{"path":"hello.txt"}}'   # then poll /status/<job-id>
```
From Python: `runpod.Queue(app="handoff", name="read").remote(path="hello.txt")`.
Verified result (2026-07-10) — the serverless worker read exactly what the pod wrote:
```json
"output": { "exists": true, "content": "handoff via MCP+skills 2026-07-10\n",
            "runpod_volume_listing": ["hello.txt"] }, "status": "COMPLETED"
```

> **Redeploy note:** with `runpod-flash`, warm workers kept the **old** artifact after a
> `flash deploy` until they recycled. If a code change doesn't take effect after
> `rp flash deploy`, `rp flash undeploy --app handoff --env default --yes` then deploy again
> for fresh workers.

## Root cause: why the reader first timed out (found via MCP worker logs)
Early runs returned `"job timed out after 1 retries"` with the worker `IN_PROGRESS` but never
returning — which *looked* like a broken worker. It wasn't the handoff, the volume, or the
data center. Streaming the worker's logs with the Runpod MCP's `stream-worker-logs` (once the
prod v2 REST API was up) showed the worker was **healthy** — fitness checks passed, handler
loaded — and the real errors:

1. With an **empty** `input` (`{"input":{}}`): `Failed to get job … Job has missing field(s):
   id or input.` The SDK rejects an empty input as missing → send a non-empty `input`.
2. With a non-empty input against a `def read(input: dict)` handler:
   `read() got an unexpected keyword argument 'noop'` — flash calls the handler as
   `read(**job_input)`, spreading the input dict as kwargs.

**Fix:** handler takes `**kwargs` (or params matching the input keys) **and** invoke with a
non-empty `input`. Lesson: with no worker-log visibility a job-reject is indistinguishable
from a broken worker — get the logs before assuming the worker is bad. This run used MCP
`stream-worker-logs`, which was the only option at the time; since runpodctl v2.10.0
`runpodctl serverless logs <id> --source container` reads the same stream from a shell.

## Cost & cleanup
```bash
rp flash app delete handoff --yes                # SDK reader; or delete endpoints by id:
runpodctl serverless delete <endpoint-id>        # (flash may create a new endpoint per
runpodctl serverless delete <endpoint-id-2>      #  compute-type change — delete each)
runpodctl network-volume delete <vol-id>         # pod must already be removed
runpodctl serverless list && runpodctl pod list && runpodctl network-volume list   # confirm clean
```
Pod cost guard: `runpodctl pod remove <pod-id>` when done (`--terminate-after` never worked). The reader
endpoint is scale-to-zero (`workers=(0,1)`), ~$0 idle.

## Real application (spec): LoRA fine-tune → serve the adapter
The verified simple case scales directly to the motivating workflow:
1. **Train on a pod** onto the volume — golden path
   [`04-finetune-pod.md`](04-finetune-pod.md) writes the adapter to `/workspace/outputs/…`.
2. **Serve from serverless** — a flash/handler endpoint with the **same volume** loads the
   adapter from `/runpod-volume/outputs/…` (the mount-path swap) on top of the base model.

Same three moves as above (volume · pod writes · endpoint reads at `/runpod-volume`) — only
the payload changes from a text file to a trained adapter. The handoff itself is verified;
this specific fine-tune variant hasn't been run end to end (spec).

## Skill facts confirmed / folded back
- `storage.md` already documents the `/workspace` (pod) vs `/runpod-volume` (serverless)
  mount-path split — confirmed correct in practice.
- The SDK attaches an existing volume via `runpod.NetworkVolume("<vol-id>", create=False)`
  (deterministic); the pod side uses `--network-volume-id`. Both must be in the volume's DC.
- **Handler contract:** the worker calls `read(**job_input)` — the `input` keys must be the
  function's parameter names, and the `input` must be non-empty (an empty `{}` is rejected as
  "missing input"). A `def read(input: dict)` handler fails.
- **Diagnosis:** the Runpod MCP `stream-worker-logs` distinguishes a job-reject (healthy
  worker, bad payload/handler) from a genuinely broken worker — reach for it before assuming
  the worker image is bad. Requires the prod v2 REST API to be reachable.
- A brand-new pod can draw a bad machine where the runtime never becomes ready (`ssh info`
  stays "pod not ready", `runtime: false`); delete it and create a fresh one rather than
  waiting indefinitely.
