---
lanes: [docker, runpodctl, rest]
mcp: partial
concepts: [serverless-handler, serverless-endpoint, template, container-image, job, api-rate-limit]
---

# Golden path 12 — serverless streaming (`/stream`)

**Goal:** get **incremental** output out of a serverless handler — each chunk visible
as it's produced, not one blob at the end — via the `/stream/<jobId>` endpoint, and
know when to reach for it instead of `/run`+poll.
**Status:** ✅ COVERED — live-verified 2026-07-13 end to end. A tiny CPU handler
`yield`ed a sentence word-by-word (0.5s apart); polling `/stream/<jobId>` returned the
words **as they were generated** (chunks at t≈11s, 18s, 20s, 21s), and the same job's
`/status` returned the full aggregated list. Image: `<your-registry>/gp12-stream:v1`.
**Lane(s):** custom handler image (`python:3.11-slim` + `runpod`) + runpodctl (template + CPU endpoint) + REST invoke (`/run` → `/stream` → `/status`)

## When to use this
Reach for `/stream` when output is produced **progressively** and you want to show it
early:
- **LLM token streaming** — render tokens as they generate (chat UIs, "typing" effect).
- **Long jobs with progress** — emit step/percentage updates while work continues.
- **Batch fan-out** — yield each item's result the moment it's done instead of after all.

Use plain **`/run` + poll `/status`** (golden path
[`../../runpod-usage/reference/endpoint-workflows.md`](../../runpod-usage/reference/endpoint-workflows.md))
when you only need the **final** result — it's simpler and there's nothing to show mid-flight.
Use **`/runsync`** for a short warm job where you'll block for the whole answer anyway.

## The one thing to get right: a *generator* handler
Streaming is a property of the **handler**, not a flag on the request. A handler that
`return`s a value is one-shot; a handler that **`yield`s** is a stream — Runpod exposes
each yielded value as a `/stream` chunk. (Async handlers may `yield` too.)

```python
# handler.py
import runpod
import time

def handler(job):
    job_input = job.get("input", {})
    sentence = job_input.get("sentence", "the quick brown fox")
    delay = float(job_input.get("delay", 0.4))
    for i, word in enumerate(sentence.split()):
        time.sleep(delay)          # stand-in for token-by-token generation
        yield {"index": i, "word": word}   # <-- each yield becomes a /stream chunk

runpod.serverless.start({
    "handler": handler,
    "return_aggregate_stream": True,   # also expose the full list via /run + /runsync
})
```

`return_aggregate_stream: True` is optional: without it, yielded results are **only**
reachable via `/stream` — `/run`/`/runsync`/`/status` return an empty output. With it,
Runpod also collects every yield into a single list you can fetch the normal way. Turn it
on unless the result set is huge (see [Gotchas](#gotchas)).

## Prerequisites
- `RUNPOD_API_KEY` exported (verify: `curl -s -o /dev/null -w '%{http_code}' https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`).
- Docker running; a Docker Hub account. `runpodctl` installed.

## Walkthrough (verified commands)

### 1. Build & push a tiny handler image
`Dockerfile` (CPU, ~150 MB base):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir runpod
COPY handler.py /app/handler.py
CMD ["python", "-u", "handler.py"]
```
```bash
docker build --platform linux/amd64 -t <your-registry>/gp12-stream:v1 .   # amd64 is required
docker push <your-registry>/gp12-stream:v1                                 # explicit tag, never :latest
```

### 2. Create a template, then a CPU scale-to-zero endpoint
```bash
runpodctl template create --name gp12-stream-tmpl --serverless \
  --image <your-registry>/gp12-stream:v1 --container-disk-in-gb 10        # → template id

runpodctl serverless create --template-id <template-id> --name gp12-stream-ep \
  --compute-type CPU --workers-min 0 --workers-max 1 --data-center-ids EU-RO-1  # → endpoint id
```
Use `runpodctl serverless create --compute-type CPU` (not the REST `POST /v1/endpoints`
with `"computeType":"CPU"` — that path provisioned a **GPU** endpoint in testing).

### 3. Submit a job, then read the stream
```bash
EP=<endpoint-id>
# Async submit — returns a job id immediately:
curl -s -X POST https://api.runpod.ai/v2/$EP/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"input":{"sentence":"streaming from a runpod serverless handler works","delay":0.5}}'
# → {"id":"c165626f-...-u1","status":"IN_QUEUE"}

# Poll /stream repeatedly until status is COMPLETED — each GET returns the NEW chunks
# produced since your last call:
curl -s https://api.runpod.ai/v2/$EP/stream/<job-id> -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Verify it works (actual output)
Polling `/stream/<jobId>` once per second while the handler yielded a word every 0.5s.
The response shape is `{"status": ..., "stream": [ {"output": <your yield>}, ... ]}`, and
each poll drains only the chunks buffered since the previous poll — proving incremental
delivery (not a single dump at the end):

```
[t=  0.0s] {"status":"IN_QUEUE","stream":[]}
[t= 11.1s] {"status":"IN_PROGRESS","stream":[{"output":{"index":0,"word":"streaming"}}]}
[t= 18.3s] {"status":"IN_PROGRESS","stream":[{"output":{"index":1,"word":"from"}}]}
[t= 19.6s] {"status":"IN_PROGRESS","stream":[{"output":{"index":2,"word":"a"}},{"output":{"index":3,"word":"runpod"}}]}
[t= 20.7s] {"status":"IN_PROGRESS","stream":[{"output":{"index":4,"word":"serverless"}},{"output":{"index":5,"word":"handler"}}]}
[t= 21.8s] {"status":"COMPLETED","stream":[{"output":{"index":6,"word":"works"}}]}
```
(The ~11s to the first chunk is the cold start — image pull + worker boot. Once warm,
chunks arrive at the handler's own pace.)

Because `return_aggregate_stream` was on, the **same job** also exposes the full list via
`/status` (and any streaming job via `/runsync`):
```bash
curl -s https://api.runpod.ai/v2/$EP/status/<job-id> -H "Authorization: Bearer $RUNPOD_API_KEY"
```
```json
{"status":"COMPLETED","delayTime":24422,"executionTime":4574,
 "output":[{"index":0,"word":"streaming"},{"index":1,"word":"from"},{"index":2,"word":"a"},
           {"index":3,"word":"runpod"},{"index":4,"word":"serverless"},
           {"index":5,"word":"handler"},{"index":6,"word":"works"}]}
```
A warm `/runsync` returned the aggregated list directly in ~2.5s:
```json
{"status":"COMPLETED","output":[{"index":0,"word":"aggregate"},{"index":1,"word":"works"},{"index":2,"word":"too"}]}
```

## Gotchas
- **`yield`, not `return`.** A `return` handler is one-shot; only a generator streams.
  If `/stream` is always empty, the handler isn't yielding.
- **`/stream` is poll-drain, not one long SSE.** Each GET returns the chunks buffered
  since your last call and a `status`. Loop until `status` is `COMPLETED`/`FAILED`
  (bound the loop). The Runpod SDKs (`run_request.stream()` in Python,
  `endpoint.stream(id)` in JS) wrap this loop for you.
- **Cold start delays the first chunk, not the streaming.** On a scale-to-zero endpoint
  expect several seconds (here ~11s) before chunk 0; that's boot, not the stream.
- **Without `return_aggregate_stream`, `/run`/`/runsync`/`/status` return no output** —
  the results live only on `/stream`. Enable it if any consumer wants the whole result.
  But **don't** aggregate huge result sets: `/run` caps at ~10 MB, `/runsync` at ~20 MB,
  and a single streamed chunk caps at **1 MB** (larger yields are split across chunks).
- **Rate limits on `/stream`:** 2000 requests / 10s, 400 concurrent — don't poll a tight
  hot loop with zero sleep across many jobs.
- **CPU endpoint:** create it with `runpodctl serverless create --compute-type CPU`.
  `POST /v1/endpoints` with `"computeType":"CPU"` provisioned a GPU endpoint in testing.

## Cost & cleanup
Scale-to-zero (`--workers-min 0`), tiny CPU worker → ~$0 idle; the whole live run was a
few seconds of CPU execution.
```bash
runpodctl serverless delete <endpoint-id>
runpodctl template delete <template-id>
runpodctl serverless list && runpodctl network-volume list && runpodctl pod list  # confirm clean
```
Keep the image `<your-registry>/gp12-stream:v1` for re-runs.

## Skill gaps folded back
- `endpoint-workflows.md` documented `/runsync` and `/run`+`/status` but **not**
  `/stream`. Added a streaming note there (generator handler + poll-drain contract +
  `return_aggregate_stream`) so the invoke section covers all three modes.
- Confirmed live: streaming is a **handler** property (`yield`), the `/stream` response is
  `{"status", "stream":[{"output":...}]}` and drains incrementally, and
  `return_aggregate_stream: True` is what makes a streaming job's output also readable via
  `/run`/`/runsync`/`/status`.
- Confirmed the CPU-endpoint creation caveat (use `runpodctl serverless create
  --compute-type CPU`, not the REST `computeType` field) — same finding applies to any
  CPU serverless golden path.
