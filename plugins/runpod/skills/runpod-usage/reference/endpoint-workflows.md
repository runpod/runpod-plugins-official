# The serverless endpoint loop

The serverless specialization of the development loop (`development-loop.md`) — for
a **request/response API that scales to zero** (transcription, inference). Unlike a
pod there's no SSH, no exposed ports, no proxy: you deploy a worker and invoke it
over the Runpod job API. Proven on the Whisper golden path (both variants).

## 1. Pick the source (in order of preference)

1. **Hub worker (fastest, least fragile)** — a maintained prebuilt worker.
   `runpodctl hub search <app>` → deploy with runpodctl (Hub is runpodctl-only).
   Best when a good worker ships what you need.
2. **flash (from scratch, custom/light)** — write an `@Endpoint` handler and
   `flash deploy`. Best when you need your own model size / I/O schema / a lighter
   image, or no good Hub worker exists.
3. **Custom image + endpoint (last resort)** — write a handler, `docker build
   --platform=linux/amd64`, push (private image → registry auth), create the
   endpoint (runpodctl/MCP). Only when neither of the above fits.

## 2. Deploy (scale-to-zero)

```bash
# Hub
runpodctl serverless create --hub-id <id> --name <name> --workers-min 0 --workers-max 3
# flash
flash deploy                                  # @Endpoint(workers=(0,3)) in the code
# Custom image — TWO steps: serverless create takes --template-id/--hub-id, NOT an image.
runpodctl template create --name <tpl> --serverless \
  --image <you>/<img>:<tag> --container-disk-in-gb 15 \
  --env '{"KEY":"VALUE"}'                      # --env is a JSON object here; → template id
runpodctl serverless create --template-id <template-id> --name <name> \
  --gpu-id "NVIDIA GeForce RTX 4090" --workers-min 0 --workers-max 2   # --gpu-id, not --gpu-type
```

`--workers-min 0` = no GPU billing while idle (pay only per request-second). Don't pin
`--data-center-ids` for a custom-image endpoint **unless a network volume forces it** — a
single-DC pin on a scarce GPU leaves workers `throttled` and jobs stuck `IN_QUEUE`
(observed live, 2026-07-10: EU-RO-1 4090 pin → `throttled:1`; unpinned → scheduled at once).

### Picking a Hub worker (this decides success)

Prefer an **actively-maintained** worker on a **broad, high-availability GPU pool**
— don't pin a scarce large tier a small model doesn't need. If deployed workers go
`ready` but jobs sit `IN_QUEUE` with `inProgress: 0`, the image is broken /
mis-dispatching — **switch workers, don't wait it out.** (Confirm it before switching:
`runpodctl serverless health <id>` for the counts (v2.9.0+) and `runpodctl serverless logs
<id> --source system` for the cause (v2.10.0+) — repeated `start container` with no
`container` output is a crash loop, not a capacity problem. MCP `stream-worker-logs` reads
the same logs.)

## 3. Invoke

The raw protocol is below because it is what you hand a user for copy-paste, and what a
non-Runpod client speaks. If you are driving it yourself, the tool lanes wrap it:
`runpodctl serverless run <id> --input '{...}'` (v2.9.0+) does submit-and-poll with auth,
local payload validation and bounded waiting; the MCP lane has typed job tools.

```bash
# warm / small payloads (sync, 60s window):
curl -s https://api.runpod.ai/v2/<endpoint-id>/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": { ... }}'

# first / cold call — async, then poll:
curl -s https://api.runpod.ai/v2/<endpoint-id>/run  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" -d '{"input": { ... }}'
curl -s https://api.runpod.ai/v2/<endpoint-id>/status/<job-id> -H "Authorization: Bearer $RUNPOD_API_KEY"
```

- Body is always `{"input": {...}}`. **flash quirk:** a flash handler nests the
  value under its parameter name → `{"input": {"<param>": {...}}}` (name the param
  `input` to get the plain contract).
- Large inputs: pass a **URL**, not bytes (payload limits `/run` ~10MB, `/runsync`
  ~20MB); base64 rides the payload for small files.
- **Streaming** (`/stream/<job-id>`):
  - Works **only when the handler is a generator** (`yield`s instead of `return`s).
  - Submit with `/run`, then GET `/stream/<job-id>` in a loop — each call drains the
    chunks buffered since the last one and returns `{"status", "stream":[{"output": <yield>}]}`.
  - Stop when `status` is `COMPLETED`.
  - Add `"return_aggregate_stream": True` to `runpod.serverless.start(...)` to *also*
    expose the full list via `/run`/`/runsync`/`/status` (single chunk caps at 1MB).
  - Worked example: golden path 12 (serverless streaming).

## 4. Verify with a real request — "ready" ≠ working

The **first call cold-starts** (image pull + model load), often exceeding
`runsync`'s 60s — use `/run` + poll `/status/<id>` for the first request, then
`runsync` once warm. Only report success once a real input returns the right
output. Bound any poll loop.

## 5. Deliver & tear down

Give the user the endpoint id + a copy-paste `curl` and the input schema (how to
pass a URL and/or base64). Scale-to-zero means it's safe to leave; delete with
`runpodctl serverless delete <id>` (or `flash app delete <app>`).

See [`golden-paths/03-whisper-endpoint/`](../../runpod/golden-paths/03-whisper-endpoint/README.md)
for a fully worked example of both the Hub and flash variants (a README plus one
file per variant).
