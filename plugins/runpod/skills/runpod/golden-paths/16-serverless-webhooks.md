---
lanes: [runpodctl, rest]
mcp: partial
concepts: [job, serverless-endpoint, serverless-handler, template]
---

# Golden path 16 — serverless webhooks (get pushed the result instead of polling)

**Goal:** from "tell me when the job is done" — submit an async `/run` job with a `webhook`
callback URL and have Runpod **POST the finished job payload to you**, so you never poll
`/status`. This is the push alternative to golden path polling: fire-and-forget the job,
let the result come to your endpoint.
**Status:** ✅ COVERED — live-verified 2026-07-13 end to end. Deployed a tiny CPU
scale-to-zero echo endpoint (`<your-registry>/gp16-echo:v1`), submitted `/run` with a
`webhook` URL, and captured the **real callback** Runpod delivered to a
[webhook.site](https://webhook.site) receiver. Also proved the **retry-on-failure**
behavior live: a receiver returning `500` got **3 delivery attempts** (1 initial + 2
retries).
**Lane(s):** runpodctl (template) + Runpod REST (`/run`) + any public HTTPS receiver

## When to use this
Use a webhook when the job is **async and slow** (seconds to hours) and you don't want a
client sitting in a poll loop against `/status`:
- Serverless-to-serverless / server-to-server: your backend submits the job, then a route
  on your backend receives the completion POST and moves the workflow forward.
- Batch / fan-out: submit N jobs, let N callbacks land instead of running N poll loops.
- Cost/latency: no repeated `/status` calls, and you learn the result the instant it's done.

**Prefer polling `/status` instead when:** the caller can't expose a public HTTPS endpoint
(e.g. a laptop, a CLI, a browser), or the job is short enough that `/runsync` returns the
result inline. Webhooks require a **publicly reachable** receiver — Runpod's workers POST
to it from the public internet.

## Prerequisites
- `RUNPOD_API_KEY` resolvable. Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`.
- A serverless endpoint (any handler — the `webhook` field is orthogonal to what your
  handler does). Here: a 3-line echo handler on CPU scale-to-zero.
- A **public HTTPS receiver**. For this walkthrough we use webhook.site's API to spin one
  up in one call; in production this is a route on your own server.

## The shape (what you send, what you get back)
```
POST /v2/<endpoint-id>/run                     Runpod worker  ──POST──▶  your webhook URL
  { "input": {...},                             (when job reaches a         { ...full job...,
    "webhook": "https://you/hook" }              terminal state)            "output": {...} }
        │                                                                        │
        └── returns {id, IN_QUEUE} immediately ──── you do NOT poll ─────────────┘
```
The `webhook` is a **top-level** field in the `/run` body, a sibling of `input` (not inside
it). Runpod POSTs to it once the job reaches a terminal state (`COMPLETED` / `FAILED`).

## Walkthrough (verified commands)

### 1. Stand up a public receiver (webhook.site, one call)
```bash
# create a token → your receiver URL is https://webhook.site/<uuid>
UUID=$(curl -s -X POST https://webhook.site/token -H 'Content-Type: application/json' -d '{}' | jq -r .uuid)
echo "receiver: https://webhook.site/$UUID"
# read what arrived later with:
#   curl -s "https://webhook.site/token/$UUID/requests?sorting=newest" | jq '.data[].content'
```
In production this step is instead "have a route like `POST /runpod/webhook` deployed and
publicly reachable." Any receiver that returns `200` works.

### 2. Deploy a tiny endpoint (skip if you already have one)
The handler is irrelevant to webhooks — this echo handler just proves the round trip:
```python
# handler.py
import runpod
def handler(job):
    return {"echo": job.get("input", {})}
runpod.serverless.start({"handler": handler})
```
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /
RUN pip install --no-cache-dir runpod~=1.7.6
COPY handler.py .
CMD ["python", "-u", "/handler.py"]
```
```bash
docker build --platform=linux/amd64 -t <your-registry>/gp16-echo:v1 .
docker push <your-registry>/gp16-echo:v1                                 # public image → no registry auth

runpodctl template create --name gp16-echo-tpl --serverless \
  --image <your-registry>/gp16-echo:v1 --container-disk-in-gb 5          # → template id, e.g. <template-id>

runpodctl serverless create --template-id <template-id> --name gp16-echo-ep \
  --compute-type CPU --workers-min 0 --workers-max 1 --data-center-ids EU-RO-1  # → endpoint id, e.g. <endpoint-id>
```
> Use `runpodctl serverless create --compute-type CPU`, **not** the REST `POST
> /v1/endpoints` with `"computeType":"CPU"` — that call silently provisions a **GPU**
> endpoint (verified 2026-07-14: it returns `gpuCount:1` / `cpuFlavorIds:null`).

### 3. Submit the job WITH the webhook, then walk away
```bash
EP=<endpoint-id>
curl -s -X POST "https://api.runpod.ai/v2/$EP/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d "{\"input\":{\"x\":1},\"webhook\":\"https://webhook.site/$UUID\"}"
# → {"id":"d7c6aa87-...-u1","status":"IN_QUEUE"}
```
`/run` returns immediately with the job id. **You don't poll** — the result will be POSTed
to your webhook when the job finishes.

## Verify it works (the actual delivered callback)
Reading the receiver after the job completed (real capture, 2026-07-13):
```bash
curl -s "https://webhook.site/token/$UUID/requests?sorting=newest" | jq '.data[0] | {method, content}'
```
```json
{
  "method": "POST",
  "content": "{\"delayTime\":9533,\"executionTime\":88,\"id\":\"d7c6aa87-df8d-49db-982b-8890054fe56f-u1\",\"input\":{\"x\":1},\"output\":{\"echo\":{\"x\":1}},\"status\":\"COMPLETED\",\"webhook\":\"https://webhook.site/fae18fab-...\"}"
}
```
Delivered headers on that POST (observed):
```
content-type: application/json
content-length: 218
user-agent: Go-http-client/2.0
traceparent: 00-8e9faaae...-9e37fb68e8b71837-00
```
**The delivered body is the full job object** — the same shape `/status` would return
(`id`, `status`, `delayTime`, `executionTime`, `output`), plus the original `input` and the
`webhook` URL echoed back. Your handler's return value is under `output`. So a webhook
receiver reads exactly what a `/status` poller would, pushed to it. Green: a `COMPLETED`
payload with `output.echo` matching the submitted `input`.

### Retry-on-failure (also verified live)
Runpod expects a `2xx` from your receiver. If it doesn't get one, it **retries up to 2 more
times with a delay between attempts** (docs: 10-second delay). Proven by pointing a job at a
receiver hard-coded to return `500`:
```bash
# a token that always answers 500
UUID_FAIL=$(curl -s -X POST https://webhook.site/token -H 'Content-Type: application/json' \
  -d '{"default_status":500}' | jq -r .uuid)
# ...submit a /run with webhook https://webhook.site/$UUID_FAIL, then count deliveries
```
Observed: **3 delivery attempts** for the one job (1 initial + 2 retries), consistent with
"up to 2 more times." Delivery timestamps: `15:36:22`, `15:36:27`, `15:36:42`. After the
retries are exhausted Runpod gives up — the job itself still `COMPLETED` (the webhook
failing does **not** fail the job; the result is still retrievable via `/status` for the
normal retention window).

## Gotchas we hit
1. **`webhook` is top-level, not inside `input`.** It's a sibling of `input` in the `/run`
   body: `{"input":{...},"webhook":"https://..."}`. Putting it inside `input` just passes it
   to your handler and no callback fires.
2. **The delivered body is the whole job, not just your output.** Don't expect a bare
   `output` — parse `status` first, then read `.output`. `input` and `webhook` are echoed
   back too. Content-type is `application/json`.
3. **Your receiver must return `2xx` or you get retried.** A non-2xx (or a timeout) triggers
   up to 2 retries. Make the receiver idempotent — the **same completion can arrive more
   than once**. Dedupe on the job `id`.
4. **A failing webhook does not fail the job.** If all 3 attempts fail, the job is still
   `COMPLETED` and retrievable via `/status` (async result retention ≈ 30 min). Treat the
   webhook as best-effort push, and keep `/status` as the fallback for anything critical.
5. **The receiver must be public HTTPS.** Runpod workers POST from the public internet —
   `localhost`, a private VPC address, or an unreachable host will never receive the
   callback. This is the main reason to fall back to polling.
6. **Scale-to-zero adds cold-start delay before the callback.** With `workersMin 0`, the
   webhook only fires after the worker cold-starts and runs the job (`delayTime` in the
   payload was 9.5 s warm-ish and ~74 s on a cold start here) — the push isn't instant, it's
   "as soon as the job actually finishes."

## Cost & cleanup
```bash
runpodctl serverless delete <endpoint-id>          # the endpoint
runpodctl template delete <template-id>                # the template
runpodctl serverless list && runpodctl template list && runpodctl pod list   # confirm clean
```
Endpoint is CPU scale-to-zero (`workersMin 0`), ~$0 idle — deleted anyway. The pushed image
(`<your-registry>/gp16-echo:v1`, public on Docker Hub) was left in place so this doc references
a real, pullable tag; it costs nothing. No pod or volume is created by this path.
webhook.site tokens expire on their own (7 days) — no cleanup needed.

## Skill gaps folded back
- New golden path: the `webhook` field is the documented push alternative to polling
  `/status`, but had no live-verified walkthrough. This proves the request shape, the
  **exact delivered payload** (full job object under `application/json`), and the
  **retry-on-failure** behavior (3 attempts) against a real receiver.
- Confirmed in practice: `webhook` is a top-level sibling of `input`; the callback body is
  the same shape as `/status`; a failing receiver is retried up to 2 more times and does not
  fail the underlying job.
