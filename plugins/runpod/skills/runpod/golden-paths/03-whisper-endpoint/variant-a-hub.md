# Golden path 03 — Whisper — Variant A: Runpod Hub worker

**Status:** COVERED — live-verified 2026-07-07. **Lane:** runpodctl + Runpod Hub.
**When to use this variant:** the recommended default — a **heavy, prebuilt, known**
model (Whisper/WhisperX) where a maintained Hub worker already ships what you need.
Zero handler code, no image build. Prefer to own a from-scratch code handler
instead? See [Variant B — flash](variant-b-flash.md). Shared schema, gotchas, and
cost notes live in the [folder README](README.md).

## Prerequisites

- `runpodctl` installed and on `PATH` — see
  [../../../runpodctl/SKILL.md](../../../runpodctl/SKILL.md).
- A Runpod API key exported for non-interactive use:
  ```bash
  export RUNPOD_API_KEY=...   # https://console.runpod.io/user/settings
  ```

## Walkthrough

1. **Search the Hub for a Whisper worker.**
   ```bash
   runpodctl hub search whisper --type SERVERLESS   # find deployable transcription workers
   ```
   There is **no** official `runpod-workers/worker-faster_whisper` in the Hub; the
   dedicated transcription workers are community WhisperX images.

2. **Pick the right worker — this decides success (see the picking lesson below).**
   Choose the actively-maintained worker on a broad, high-availability GPU pool.
   For this run that was `kodxana/whisperx-worker_v2` v1.0.7
   (hub-id `cmpo4s6ma000008jl2x6y49hh`).

3. **Deploy it scale-to-zero with runpodctl.** The Hub config supplies the GPU
   pool, container disk, and CUDA version automatically — you only set scaling.
   ```bash
   runpodctl serverless create \
     --hub-id cmpo4s6ma000008jl2x6y49hh \
     --name whisperx-v2 \
     --workers-min 0 --workers-max 3        # min 0 = scale-to-zero, ~0 idle cost
   ```
   Returns an endpoint id (this run: `tlftkn7v2ixdw0`).

4. **First call cold-starts — use `/run` + poll for it, then `runsync` once warm.**
   See [Verify it works](#verify-it-works). Report success only after a real input
   returns the right transcript.

### Picking the worker (this matters — not all Hub workers work)

Two workers were tried:

| Worker | hub-id | GPU pool | Result |
| --- | --- | --- | --- |
| `hapnan/whisperx-worker` v1.0.6 | `cmh98s0m8000002jpc7gz8v0i` | pinned `ADA_48_PRO` | **Failed** — workers reported `ready` but never consumed the queue (in-progress stuck at 0 for >8 min); pool also threw `throttled` workers. Deleted. |
| **`kodxana/whisperx-worker_v2` v1.0.7** | **`cmpo4s6ma000008jl2x6y49hh`** | `AMPERE_16,AMPERE_24,ADA_24` | **Works** — first job COMPLETED in ~27s total (18s cold-start delay + 9s exec). Chosen. |

**Lesson:** prefer the actively-maintained worker on a **broad, high-availability
GPU pool** (16–24 GB tiers) over one pinned to a scarce 48 GB tier. WhisperX
large-v2 only needs ~10 GB VRAM, so pinning `ADA_48_PRO` bought nothing and cost
availability. When a Hub worker's workers go `ready` but jobs sit `IN_QUEUE` with
`inProgress: 0`, that worker image is broken/mis-dispatching — **switch workers,
don't wait it out.** (This is the shared "broken Hub worker" gotcha in the
[README](README.md); the same rule is in
[../../../runpod-usage/reference/gotchas.md](../../../runpod-usage/reference/gotchas.md).)

## Verify it works

Warm / small-payload sync call (see the shared
[input & output schema](README.md#input--output-schema-shared) for all fields):

```bash
curl -s https://api.runpod.ai/v2/<endpoint-id>/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"audio_file":"https://github.com/runpod-workers/sample-inputs/raw/main/audio/gettysburg.wav"}}'
```

Returned (warm: **127 ms delay + 4.7 s exec**):

```
Four score and seven years ago, our fathers brought forth on this continent a new
nation, conceived in liberty and dedicated to the proposition that all men are
created equal.
```

First request cold-starts (image pull + model load) ~20–90 s, which can exceed
`runsync`'s 60 s sync window — for the first call use `/run` and poll
`/status/<job-id>`, then switch to `runsync` once warm:

```bash
# first / cold call — async, then poll (bound the loop):
curl -s https://api.runpod.ai/v2/<endpoint-id>/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"audio_file":"https://github.com/runpod-workers/sample-inputs/raw/main/audio/gettysburg.wav"}}'
curl -s https://api.runpod.ai/v2/<endpoint-id>/status/<job-id> \
  -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Variant-specific gotchas

- **Not all Hub workers work.** A `ready` worker with jobs stuck `IN_QUEUE` /
  `inProgress: 0` is a broken image — switch, don't wait (see the picking lesson).
- **Worker logs were the missing signal on this run** — at the time runpodctl had no
  worker-log command, REST v1 has no worker-log path, and GraphQL introspection was a
  dead end, so diagnosis relied on the endpoint `/health` worker counts alone.
  **Fixed upstream:** `runpodctl serverless logs <endpoint-id>` shipped in v2.10.0 and
  is now the fast way to make the broken-worker call — `--source system` showing
  repeated `start container` with no `container` output is the crash-loop tell this run
  had to infer. (MCP `stream-worker-logs` does the same when it's connected.)
- **`serverless update` has no `--gpu-id` flag.** To change an existing endpoint's
  GPU pool you must `PATCH https://rest.runpod.io/v1/endpoints/<id>` with
  `{"gpuTypeIds":[...]}`. (To *override* the pool at create time, pass `--gpu-id` on
  `serverless create`.)
- **`--workers-min 0` is scale-to-zero** and is the default when omitted; the Hub
  config controls the GPU pool unless you override with `--gpu-id`.

## Cost & cleanup (link back to README for shared)

Scale-to-zero (`--workers-min 0`) means ~$0 while idle. Teardown for this run:

```bash
runpodctl serverless delete <endpoint-id>   # e.g. tlftkn7v2ixdw0
```

Full shared cost/cleanup and the 204-on-delete note are in the
[folder README](README.md#cost--cleanup-shared).
