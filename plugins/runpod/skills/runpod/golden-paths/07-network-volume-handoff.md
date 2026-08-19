# Golden path 07 — network-volume handoff (pod → volume → serverless)

**Goal:** produce data on a **pod**, persist it to a **network volume**, and have a
**serverless endpoint** read that same data — the pattern behind "fine-tune on a pod,
then serve the adapter from an endpoint."
**Status:** COVERED — live-verified 2026-07-10 end to end (pod wrote `/workspace/hello.txt`;
a flash serverless worker read it back at `/runpod-volume/hello.txt` and returned the exact
contents). The earlier read-back failures were a handler-signature / empty-input bug, not the
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
- `RUNPOD_API_KEY` resolvable (both runpodctl and flash read it).
- `runpodctl` + `flash` installed.
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
  --ssh --terminate-after <iso8601 ~1h out>          # no --ports: nothing to serve

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
Use **flash** for a code-first reader. Attach the existing volume **by id** (deterministic
— no name matching), pin the same DC:

```python
# main.py
import os
from runpod_flash import Endpoint, DataCenter, NetworkVolume
from runpod_flash.core.resources.cpu import CpuInstanceType

vol = NetworkVolume(id="<vol-id>", datacenter=DataCenter.EU_RO_1)   # attach EXISTING by id

@Endpoint(name="handoff-reader", cpu=CpuInstanceType.CPU3C_1_2,
          workers=(0, 1), datacenter=DataCenter.EU_RO_1, volume=vol)
async def read(**kwargs) -> dict:                    # see Root cause: flash calls read(**job_input)
    p = "/runpod-volume/hello.txt"                   # NOTE: /runpod-volume, not /workspace
    return {"exists": os.path.exists(p),
            "content": open(p).read() if os.path.exists(p) else None}
```
**Handler signature matters** — flash invokes the handler as `read(**job_input)`, spreading
the request's `input` dict as keyword arguments. Use `**kwargs` (or name parameters to match
the input keys); a plain `def read(input: dict)` fails with
`read() got an unexpected keyword argument …`. See [Root cause](#root-cause-why-the-reader-first-timed-out-found-via-mcp-worker-logs).
```bash
RUNPOD_API_KEY=... flash deploy
runpodctl serverless list        # confirm the endpoint's networkVolumeId == your volume id
```
Verified: the deployed endpoint reported `networkVolumeId` equal to the volume the pod
wrote to — the **same volume is attached to both sides**. `NetworkVolume(id=...)` attaches
the existing volume deterministically (there is also a `name=`/`dataCenterId=` form).

### 4. Invoke and read the artifact back
Send a **non-empty** `input` (an empty `{}` is rejected by the worker SDK as "missing input"):
```bash
curl -s https://api.runpod.ai/v2/<endpoint-id>/run -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -d '{"input":{"noop":true}}'   # then poll /status/<job-id>
```
Verified result (2026-07-10) — the serverless worker read exactly what the pod wrote:
```json
"output": { "exists": true, "content": "handoff via MCP+skills 2026-07-10\n",
            "runpod_volume_listing": ["hello.txt"] }, "status": "COMPLETED"
```

> **Redeploy note:** flash keeps warm workers on the **old** artifact after a `flash deploy`
> until they recycle. If a code change doesn't take effect, `flash undeploy <name> --force`
> then `flash deploy` for fresh workers.

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
runpodctl serverless delete <endpoint-id>        # (flash may create a new endpoint per
runpodctl serverless delete <endpoint-id-2>      #  compute-type change — delete each)
runpodctl network-volume delete <vol-id>         # pod must already be removed
runpodctl serverless list && runpodctl pod list && runpodctl network-volume list   # confirm clean
```
Pod cost guard: `--terminate-after` (deletes the pod), not `--stop-after`. The reader
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
- flash attaches an existing volume via `NetworkVolume(id=...)` (deterministic); the pod
  side uses `--network-volume-id`. Both must be in the volume's DC.
- **flash handler contract:** flash calls `read(**job_input)` — the handler must accept the
  input keys as kwargs (`**kwargs` is safest), and the `input` must be non-empty (an empty
  `{}` is rejected as "missing input"). A `def read(input: dict)` handler fails.
- **Diagnosis:** the Runpod MCP `stream-worker-logs` distinguishes a job-reject (healthy
  worker, bad payload/handler) from a genuinely broken worker — reach for it before assuming
  the worker image is bad. Requires the prod v2 REST API to be reachable.
- A brand-new pod can draw a bad machine where the runtime never becomes ready (`ssh info`
  stays "pod not ready", `runtime: false`); delete it and create a fresh one rather than
  waiting indefinitely.
