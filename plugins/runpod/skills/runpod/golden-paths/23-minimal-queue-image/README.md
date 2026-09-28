---
lanes: [docker, runpodctl, rest]
mcp: partial
concepts: [serverless-handler, template, serverless-endpoint, container-image, worker]
---

# Golden path 23 — minimal serverless **queue** image

✅ **Live-verified** (built → pushed → deployed on a CPU worker → invoked `/runsync` → torn down).

The smallest possible **queue-based** serverless worker: a Python handler wrapped in
`runpod.serverless.start`. This is the queue *image contract* — Runpod pulls jobs off the
queue and hands each one to your `handler(event)`. Contrast with the load-balanced contract
([golden path 14](../14-load-balancing-endpoint.md)), where your worker serves HTTP itself
with **no** handler.

See [building-images.md](../../../runpod-usage/reference/building-images.md) for the concepts
(base image, layering, image contract per target).

## Prerequisites

See the shared [Before you run any path](../README.md#before-you-run-any-path-shared-prerequisites)
block first. For this path specifically:

- **Runpod auth** — `export RUNPOD_API_KEY=<key>` (from the
  [console](https://runpod.io/console/user/settings); see
  [getting-started](../../../runpod-usage/reference/getting-started.md)). Powers `runpodctl` + the invoke below.
- **Docker** running **and `docker login`** to a registry you can push to (Docker Hub, etc.) —
  substitute your namespace for `<namespace>` below. See
  [companion-clis docker](../../../companion-clis/reference/docker.md).

## The image

[`template/`](template/) — three files, nothing else:

- **`handler.py`** — `handler(event)` reads `event["input"]`, returns a dict.
  `runpod.serverless.start({"handler": handler})` runs the worker loop.
- **`requirements.txt`** — just `runpod`.
- **`Dockerfile`** — `FROM python:3.11-slim`; deps layer before code; `CMD` runs the handler.

> This CPU demo uses `python:3.11-slim` (honest + pulls fast). A GPU workload should build
> `FROM runpod/pytorch:<tag>` for the pre-cached CUDA/torch base — see
> [building-images.md](../../../runpod-usage/reference/building-images.md) (the single source
> for base-image choice).

## Build + push

Runpod hosts are **x86_64 Linux** — always `--platform=linux/amd64` (emulated on Apple Silicon):

```bash
cd template
docker buildx build --platform linux/amd64 -t <namespace>/rp-gp23-queue:v1 --push .
```

## Deploy (CPU — cheapest; this handler needs no GPU)

```bash
# 1. serverless template pointing at the image
runpodctl template create --name gp23-queue \
  --image <namespace>/rp-gp23-queue:v1 --serverless --container-disk-in-gb 5
# → returns a template id, e.g. jvhybsopo4

# 2. CPU endpoint from that template (min workers 0, scales to zero when idle)
runpodctl serverless create --template-id <template-id> \
  --compute-type CPU --instance-id cpu3g-1-4 \
  --name gp23-queue-ep --workers-min 0 --workers-max 1 --idle-timeout 5
# → returns an endpoint id, e.g. b5nopviq75s0cn
```

## Invoke

```bash
# Uses $RUNPOD_API_KEY (the recommended setup); falls back to runpodctl's config.toml.
KEY="${RUNPOD_API_KEY:-$(grep '^apikey' ~/.runpod/config.toml 2>/dev/null | sed "s/apikey = '//;s/'//")}"
curl -s -X POST "https://api.runpod.ai/v2/<endpoint-id>/runsync" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"input":{"name":"Justin"}}'
```

**Actual response (this run):**

```json
{"delayTime":3355,"executionTime":40,"id":"sync-74e1ff96-...-u2",
 "output":{"echo":{"name":"Justin"},"message":"hello Justin"},
 "status":"COMPLETED","workerId":"nlzo8ccfn6q1t0"}
```

`delayTime` (~3.4s) is the cold start — worker scaling from zero + pulling the image.
`executionTime` (40ms) is the handler itself. Warm calls skip the delay.

- `/runsync` — blocks, returns the result inline (above). Best for short jobs.
- `/run` — returns a job id immediately; poll `/status/<id>`. Best for long jobs.

## Test locally first (no spend)

The image runs the handler as its command, but Runpod's SDK also has a local test mode —
pass a test input and it invokes the handler once and exits (the dual-mode loop in
[golden path 09](../09-custom-serverless-dev-loop/README.md)):

```bash
# --platform linux/amd64 because the image is amd64 (emulated on Apple Silicon)
docker run --rm --platform linux/amd64 <namespace>/rp-gp23-queue:v1 \
  python -u handler.py --test_input '{"input":{"name":"local"}}'
```

**Observed locally:**

```text
--- Starting Serverless Worker | Version 1.10.1 ---
INFO   | test_input set, using test_input as job input.
INFO   | local_test | Handler output: {'message': 'hello local', 'echo': {'name': 'local'}}
INFO   | Local testing complete, exiting.
```

## Tear down

```bash
runpodctl serverless delete <endpoint-id>
runpodctl template delete <template-id>
```

## What this proves

- The queue image contract: **handler + `runpod.serverless.start`**, container `CMD` runs it.
- `--platform=linux/amd64` build works from Apple Silicon (QEMU).
- Deps-before-code layering; a slim base; CPU compute for a CPU workload.
- End-to-end: build → push → template → endpoint → `/runsync` → teardown.
