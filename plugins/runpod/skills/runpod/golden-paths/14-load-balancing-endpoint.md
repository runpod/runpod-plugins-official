# Golden path 14 — load-balancing serverless endpoint (custom HTTP worker)

**Goal:** deploy a **load-balancing** Serverless endpoint — where your worker runs its own
HTTP server and Runpod routes requests **directly** to it (custom URL paths, single-hop, no
queue), as opposed to the queue/handler `/run` model — using a **custom image + headless
API** (no Console, no flash).
**Status:** ✅ COVERED — live-verified 2026-07-13. A stdlib-only FastAPI-free HTTP worker
(`<your-registry>/gp14-lb:v1`) was deployed as an `LB`-type endpoint via GraphQL `saveEndpoint`,
and `GET /ping`, `POST /echo`, `GET /stats` all returned `200` at
`https://<ENDPOINT_ID>.api.runpod.ai/<path>` with request state persisting on the worker.
**Lane(s):** custom Docker image + `runpodctl template create` + **GraphQL `saveEndpoint`
(`type: "LB"`)** or **v2 REST / Runpod MCP (`LOAD_BALANCER`)** + plain HTTP invocation.
(flash covers LB code-first; this is the image/API way.)

## When to use this
Reach for a load-balancing endpoint instead of the queue/handler model when you need:
- **Direct access to your model's own HTTP server** (vLLM's OpenAI-compatible server, a
  Triton/TGI server, any FastAPI/Flask app) — expose it as-is, no handler wrapper.
- **Custom URL paths and HTTP verbs** (`POST /v1/chat/completions`, `GET /stats`,
  WebSockets) rather than fixed `/run` + `/runsync`.
- **Lower, single-hop latency** for real-time apps and streaming.
- **Non-JSON payloads** or multiple logical endpoints inside one worker.

Stick with **queue-based** endpoints (golden paths 03/05/12) when you want guaranteed request
processing, automatic retries, and queue buffering under burst — the LB model **drops**
requests when overloaded (UDP-like) and has **no built-in retry** (queue-based is TCP-like).

| | Load balancing | Queue-based |
| --- | --- | --- |
| Request flow | direct to worker HTTP server | through the job queue |
| You implement | a full HTTP server (any framework) | a `handler(job)` function |
| API surface | your own paths/verbs | fixed `/run`, `/runsync`, `/status` |
| Under overload | drops requests, no retry | buffers in queue, auto-retries |
| Invoke URL | `https://<ID>.api.runpod.ai/<path>` | `https://api.runpod.ai/v2/<ID>/run` |

## The worker contract (the thing to get right)
A load-balancing worker is **just an HTTP server**, with two rules Runpod enforces:

1. **Expose a `GET /ping` health route.** The load balancer polls it and routes only to
   workers that answer `200`:
   | `/ping` returns | Worker state |
   | --- | --- |
   | `200` | healthy — receives traffic |
   | `204` | still initializing (cold start) |
   | anything else | unhealthy — pulled from the pool |
2. **Listen on the configured port.** Two env vars drive this — set **both explicitly** and
   **expose that port** on the template (see the gotcha below):
   | Env var | Meaning | Default |
   | --- | --- | --- |
   | `PORT` | main app server port | `80` |
   | `PORT_HEALTH` | port the `/ping` probe hits | same as `PORT` |

Everything else — routes, request/response shape — is yours. Requests to
`https://<ENDPOINT_ID>.api.runpod.ai/<path>` land on your server's `<path>` unchanged; Runpod
enforces bearer auth (`Authorization: Bearer <RUNPOD_API_KEY>`) at the edge before routing.

## Prerequisites
- `RUNPOD_API_KEY` exported; Docker running; a Docker Hub (or other) registry login.
- `runpodctl` (any recent version — used only for `template create`).
- The endpoint type is set by **v2 REST** (`"type": "LOAD_BALANCER"` on `POST /v2/serverless`)
  or by **GraphQL `saveEndpoint`** (`type: "LB"`). Neither the **v1** REST
  `POST /v1/endpoints` body nor `runpodctl serverless create` exposes an endpoint-type field,
  so those two can't produce a load balancer.

## Walkthrough (verified commands)

### 1. Build a tiny LB worker (an HTTP server, no Runpod SDK)
No `runpod` package, no handler — just a server that answers `/ping` plus your own routes.
This example uses the Python stdlib so the image is tiny and dependency-free:

```python
# app.py
import os, json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.getenv("PORT", "80"))     # Runpod injects PORT; bind to it
START, COUNT = time.time(), 0

class H(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == "/ping":   self._send(200, {"status": "healthy"})   # health probe
        elif self.path == "/stats": self._send(200, {"requests": COUNT})
        else: self._send(404, {"error": "not found"})
    def do_POST(self):
        global COUNT; COUNT += 1
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}") if n else {}
        if self.path == "/echo":
            self._send(200, {"worker": os.getenv("RUNPOD_POD_ID", "?"),
                             "request_number": COUNT, "you_sent": data})
        else: self._send(404, {"error": "not found"})
    def log_message(self, *a): pass

ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
```
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY app.py .
CMD ["python3", "app.py"]
```
(FastAPI/Flask work identically — the docs' reference worker uses FastAPI + uvicorn. The
contract is only "serve `/ping` on the port," not a specific framework.)

```bash
docker build --platform linux/amd64 -t <your-registry>/gp14-lb:v1 .
docker push <your-registry>/gp14-lb:v1
```

### 2. Create a serverless template — expose the port AND set PORT/PORT_HEALTH
This is the step that makes or breaks it (see [Gotchas](#gotchas)). Expose the chosen HTTP
port and set **both** `PORT` and `PORT_HEALTH` to it:

```bash
runpodctl template create --name gp14-lb-tmpl2 --serverless \
  --image <your-registry>/gp14-lb:v1 --container-disk-in-gb 5 \
  --ports "5000/http" --env '{"PORT":"5000","PORT_HEALTH":"5000"}'
# → template id, e.g. <template-id>
```

### 3. Create the endpoint as a load balancer

Two headless routes. Prefer **a** — v2 REST is the current shape on both the production
and dev hosts (verified 2026-07-29: both serve a byte-identical OpenAPI spec).

**a. v2 REST / Runpod MCP (preferred).** v2 REST takes `"type": "LOAD_BALANCER"` on
`POST /v2/serverless`. Load balancers have no queue, so the scaler must be
`REQUEST_COUNT` — the spec forbids `QUEUE_DELAY` for this type **on create**. Read the
invoke URL from the reply's `requestUrls.base` rather than assembling it:

```bash
curl -s -X POST https://v2-rest.runpod.io/v2/serverless \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"gp14-lb-ep","image":"<your-registry>/gp14-lb:v1","type":"LOAD_BALANCER",
       "gpu":{"pools":["ADA_24"],"count":1},"disk":5,"ports":["5000/http"],
       "env":{"PORT":"5000","PORT_HEALTH":"5000"},
       "workers":{"min":0,"max":1,"idleTimeout":5},
       "scaling":{"type":"REQUEST_COUNT","requestCount":4}}'
# → {"id":"<endpoint-id>","type":"LOAD_BALANCER",
#    "requestUrls":{"base":"https://<endpoint-id>.api.runpod.ai",
#                   "health":"https://<endpoint-id>.api.runpod.ai/ping"}, ...}
```

This is image-based (no template needed), so step 2 is optional on this route. `type` is
**required** on create (the spec lists it alongside `name`/`image`/`gpu`/`scaling`) and
**fixed** afterwards — `UpdateEndpointRequest` has no `type` field, so no PATCH can change
it.

> **Via the Runpod MCP server:** `create-endpoint` takes `endpointType: "LOAD_BALANCER"` and
> rejects `scalerType: QUEUE_DELAY` for it client-side, before spending a round trip — the
> shortest path when MCP is connected.
>
> If your server's `create-endpoint` has **no `endpointType` parameter**, it predates the v2
> serverless reshape and will 422 against production on any endpoint create or update. Upgrade
> it, or use the raw v2 REST call above meanwhile.

**b. GraphQL `saveEndpoint`.** The `type` field takes `QB`
(queue-based, the default) or `LB`. Use a browser `User-Agent` (Cloudflare) and pass the
api key in the query string:

```bash
curl -s -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -H 'User-Agent: Mozilla/5.0' \
  -d '{"query":"mutation($input:EndpointInput!){saveEndpoint(input:$input){id name type templateId}}",
       "variables":{"input":{"name":"gp14-lb-ep","templateId":"<template-id>","type":"LB",
       "gpuIds":"AMPERE_16","scalerType":"QUEUE_DELAY","scalerValue":4,
       "workersMin":0,"workersMax":1,"idleTimeout":5}}}'
# → {"data":{"saveEndpoint":{"id":"<endpoint-id>","type":"LB",...}}}
```
`gpuIds` is required by `saveEndpoint` (tiers: `AMPERE_16`/`AMPERE_24`/`ADA_24`/`AMPERE_48`/
`ADA_48_PRO`/`AMPERE_80`/`ADA_80_PRO`). `workersMin: 0` = scale-to-zero. Confirm the type
stuck: the mutation echoes `"type": "LB"`.

GraphQL still accepts `scalerType: "QUEUE_DELAY"` on an `LB` endpoint (it is the legacy
flat scaler field and is not validated against the type here). It is not meaningful — a
load balancer has no queue to measure — and the v2 REST route above rejects the same
combination, so prefer `scalerType: "REQUEST_COUNT"` even on this route.

> **See also:** [17 — WebSocket worker](17-serverless-websocket.md) applies this same
> `type: "LB"` substrate to a WebSocket server — start here to understand the LB base path,
> then go there for a persistent-connection worker on top of it.

### 4. Warm the worker, then call your custom routes
Scale-to-zero means the first hit triggers a cold start. Poll the standard health API
(worker counts) until a worker is `ready`, then call your paths directly:

```bash
# trigger + wait for a healthy worker
curl -s "https://api.runpod.ai/v2/<endpoint-id>/health" -H "Authorization: Bearer $RUNPOD_API_KEY"
# {"workers":{"idle":1,"ready":1,"running":0,...}}   ← ready:1 means routable

BASE="https://<endpoint-id>.api.runpod.ai"           # ← the LB base URL: <ID>.api.runpod.ai
curl -s "$BASE/ping"  -H "Authorization: Bearer $RUNPOD_API_KEY"
curl -s -X POST "$BASE/echo" -H "Authorization: Bearer $RUNPOD_API_KEY" \
     -H 'Content-Type: application/json' -d '{"prompt":"golden path 14 lb","n":2}'
curl -s "$BASE/stats" -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Verify it works (observed 2026-07-13)
```text
GET  /ping   → 200  {"status": "healthy"}
POST /echo   → 200  {"worker": "9agv3pjgc40qwb", "request_number": 1,
                     "you_sent": {"prompt": "golden path 14 lb", "n": 2}}
GET  /stats  → 200  {"requests": 1, "uptime_s": 22.4}
POST /echo   → 200  {"worker": "9agv3pjgc40qwb", "request_number": 2, ...}   # counter++, same worker
GET  /ping   (no Authorization header) → 401                                 # edge auth enforced
```
Two facts this proves about the LB model: requests hit **your** paths verbatim (there is no
`/run` indirection), and the in-memory `request_number` incremented `1 → 2` across calls —
you're talking to the worker's own long-lived process directly, not a stateless job.

## Gotchas
- **Set `PORT_HEALTH` and expose the port — a "running" worker is not a "ready" worker.**
  The failure mode: the worker shows `running: 1` in `/health` but `ready: 0`, and every
  request hangs until the LB's ~2-min "no worker available" timeout (`400 timed out waiting
  for worker`, or a client-side timeout). That means the health probe never got a `200`.
  The fix that worked here: expose the exact port on the template (`--ports "5000/http"`)
  **and** set **both** `PORT` and `PORT_HEALTH` env vars to it. Relying on the documented
  `PORT` default of `80` alone was not sufficient in practice — set them explicitly.
- **The type is set at creation, by v2 REST or GraphQL only.** v2 REST takes
  `"type": "LOAD_BALANCER"`; GraphQL `saveEndpoint` takes `type: "LB"`. **v1** REST
  `EndpointCreateInput` and `runpodctl serverless create` have no endpoint-type field. There is
  no way to *flip* an existing endpoint either way — `UpdateEndpointRequest` has no `type`
  field at all, so create it right or recreate it (or use the Console's **Endpoint Type →
  Load Balancer** at creation). A queue-based worker image called on an LB path — or vice
  versa — returns `{"error":"not allowed for QB API"}`.
- **Two URLs, don't mix them.** LB is invoked at `https://<ID>.api.runpod.ai/<path>`; the
  queue API lives at `https://api.runpod.ai/v2/<ID>/run`. The `/health` worker-count endpoint
  (`.../v2/<ID>/health`) still works for LB endpoints and is the cleanest readiness signal.
- **Cold starts need retries.** On scale-to-zero, expect a first-request miss while `/ping`
  is still `204`. The docs recommend ≥3 retries with 5–10 s delays; here, polling `/health`
  for `ready: 1` before sending real traffic was reliable.
- **No queue buffer, no retry.** Overload drops requests. If you need guaranteed processing,
  use a queue-based endpoint instead.
- **Limits:** request timeout 2 min (no worker), processing timeout 5.5 min/request, payload
  30 MB each way.

## Cost & cleanup
Endpoint is scale-to-zero (`workersMin: 0`), so idle cost is ~$0; a GPU worker only bills
during the brief warm test. Delete the endpoint (set workers to 0 first) and the template;
the image can stay in the registry.

```bash
# set workers to 0, then delete the endpoint
curl -s -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -H 'User-Agent: Mozilla/5.0' \
  -d '{"query":"mutation($i:EndpointInput!){saveEndpoint(input:$i){id workersMax}}",
       "variables":{"i":{"id":"<endpoint-id>","name":"gp14-lb-ep","templateId":"<template-id>",
       "type":"LB","gpuIds":"AMPERE_16","workersMin":0,"workersMax":0}}}'
curl -s -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -H 'User-Agent: Mozilla/5.0' \
  -d '{"query":"mutation{deleteEndpoint(id:\"<endpoint-id>\")}"}'
runpodctl template delete <template-id>
runpodctl serverless list          # confirm the endpoint is gone
```
Kept image: `<your-registry>/gp14-lb:v1` (the tiny stdlib LB worker above).

## Skill gaps folded back
- The load-balancing endpoint type is settable headlessly two ways: **v2 REST**
  (`"type": "LOAD_BALANCER"`) or **GraphQL `saveEndpoint`** (`type: "LB"`). The **v1** REST
  endpoint-create call and `runpodctl serverless create` have no type field, and no API can change
  the type after creation. Skills that create endpoints should note this when a custom-HTTP/LB
  endpoint is wanted.
- **Setting `PORT_HEALTH` (and exposing the port) explicitly is effectively required**, not
  optional — a worker that binds the app port but leaves `PORT_HEALTH` at its documented
  default failed to become `ready`. Treat "expose the port + set `PORT` + set `PORT_HEALTH`"
  as one atomic step for LB workers.
- Readiness for an LB endpoint is best observed via the queue-style `/v2/<ID>/health`
  worker-count endpoint (`ready`/`running`/`initializing`) rather than by hammering `/ping`,
  which blocks up to the 2-min no-worker timeout during cold start.
