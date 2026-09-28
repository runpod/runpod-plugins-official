---
lanes: [docker, runpodctl, rest]
mcp: partial
concepts: [serverless-endpoint, worker, template, exposed-port, container-image, endpoint-autoscaling]
---

# Golden path 17 — serverless WebSocket worker (load-balancing endpoint)

**Goal:** serve a **bidirectional, persistent WebSocket** from a serverless worker — a
client opens one `wss://` connection, sends messages, and receives streamed frames back
over the *same* socket, in real time. The mechanism that makes this possible is the
**load-balancing endpoint**: traffic is routed straight to a worker's own HTTP server
(FastAPI/uvicorn), bypassing the job queue, so protocols the queue can't express —
WebSockets, SSE, long-lived duplex streams — work natively.
**Status:** ✅ **COVERED — live-verified 2026-07-13** end to end. Built
`<your-registry>/gp17-ws:v1` (a `python:3.10-slim` FastAPI worker with `@app.websocket("/ws")`),
deployed it as an **`LB` (load-balancing) endpoint** via the GraphQL `saveEndpoint`
mutation, and connected a real Python `websockets` client to
`wss://<ep>.api.runpod.ai/ws`: sent a JSON prompt, received token-by-token frames + a
`{"done": true}` frame, and proved the socket is **persistent** by sending a second
prompt on the *same* connection and getting a second stream back. HTTP `/ping`,
`/generate`, `/stats` on the same endpoint URL all verified, and endpoint auth
(`Authorization: Bearer`) confirmed enforced (401 without / with a bad token).
**Lane(s):** custom FastAPI worker image (`python:3.10-slim` + `fastapi`/`uvicorn`/`websockets`) + runpodctl (template) + **GraphQL `saveEndpoint` with `type: "LB"`** (endpoint) + a WebSocket client (`websockets` / `wscat`). Shares the load-balancing mechanism with golden path [14](14-load-balancing-endpoint.md).

> **Prerequisite reading:** WebSocket serving is a *specialization* of the load-balancing
> endpoint — understand the substrate first via golden path
> [14 (load-balancing endpoint)](14-load-balancing-endpoint.md), which documents how an `LB`
> endpoint is created (`type:"LB"` via GraphQL `saveEndpoint`) and the exposed-port ==
> `PORT` == `PORT_HEALTH` routing contract. This path reuses all of that and adds only the
> `@app.websocket` route, the `wss://` scheme, and the raised client `open_timeout`.

## Prerequisites
- Shared setup first: [../README.md](README.md#before-you-run-any-path-shared-prerequisites) and
  [getting-started.md](../../runpod-usage/reference/getting-started.md) (auth resolution, SSH,
  companion-CLI credentials).
- Read golden path [14](14-load-balancing-endpoint.md) first (the LB substrate — see the
  prerequisite-reading note above).
- `RUNPOD_API_KEY` resolvable. Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`. The same
  key is the Bearer token on every HTTP request and on the WS upgrade.
- `docker` running and `docker login` to a registry you can push to (`<your-registry>`, e.g. your
  Docker Hub user) — you build and push the FastAPI worker image below.
- `runpodctl` installed + authenticated (creates the template).
- A **WebSocket client** to verify: Python `websockets` (`pip install websockets`) or
  `wscat` (`npm i -g wscat`).

## When to use WebSocket vs `/stream` vs the queue

Three ways to get data off a serverless worker — pick by connection shape, not by habit:

| You need | Use | Endpoint type | How it flows |
| --- | --- | --- | --- |
| **Bidirectional / interactive** — client keeps sending on an open connection (chat turns, live audio, control channel), server pushes back anytime | **WebSocket** (`wss://<ep>.api.runpod.ai/ws`) — *this path* | **Load-balancing (`LB`)** | one persistent full-duplex socket, direct to the worker |
| **One request → incremental output** — you submit once, want chunks as they're produced, don't send more | **`/stream/<jobId>`** — golden path [12](12-serverless-streaming.md) | Queue-based (`QB`) | submit `/run`, poll `/stream` for chunks |
| **Fire-and-forget / batch / guaranteed execution** — async jobs, retries, backlog buffering | **`/run` + `/status`** | Queue-based (`QB`) | job queued, processed in order, result retrievable later |

Rule of thumb: **queue-based = TCP-like** (buffered, guaranteed, retried, sequential);
**load-balancing = UDP-like** (direct, low-latency, no queue, no built-in retry). A
WebSocket is inherently a persistent duplex connection, so it *requires* the direct path
— **queue-based endpoints reject WebSocket/custom routes** (the gateway returns
`not allowed for QB API`). If you only need server→client chunks for a single request and
want the queue's durability, `/stream` (path 12) is simpler and cheaper. Reach for WS
only when the client needs to **keep talking** on the same connection.

## Architecture — how a load-balancing WS worker is wired

```
                    Runpod LB gateway (auth + routing)
   wss://<ep>.api.runpod.ai/ws  ──►  https://<ep>.api.runpod.ai/*
        │  Authorization: Bearer <RUNPOD_API_KEY>
        ▼
   ┌───────────────────────────────────────────────┐
   │  worker container                              │
   │   uvicorn on PORT (here 80)                    │
   │   FastAPI app:                                 │
   │     GET  /ping        ← health (LB polls this) │
   │     POST /generate    ← normal HTTP route      │
   │     GET  /stats                                │
   │     WS   /ws          ← @app.websocket("/ws")  │
   └───────────────────────────────────────────────┘
```

Key facts, all from the live run:

- **One URL, one port.** Every route — HTTP *and* WebSocket — is served by the same
  uvicorn process on the same `PORT`. The LB gateway exposes them all under
  `https://<ep>.api.runpod.ai/<path>` (HTTP) and `wss://<ep>.api.runpod.ai/<path>` (WS).
  No separate TCP port, no public-IP juggling.
- **Health = `/ping` on `PORT_HEALTH`.** The LB polls `GET /ping`; `200` = healthy (in
  the routing pool), `204` = initializing, anything else = unhealthy (pulled from the
  pool). Cold-start time is measured as the gap between the first `204` and the first
  `200`. A worker whose HTTP server never answers `/ping` never joins the pool — see the
  **port** gotcha below, which is the #1 way this fails.
- **Auth is at the gateway.** `Authorization: Bearer <RUNPOD_API_KEY>` is required on
  every HTTP request and on the WS upgrade (as a connection header). Verified: no token
  → `401 no token provided`; bad token → `401 invalid api key`. Your app code never sees
  the key. (You *can* add a second app-level check — e.g. an ephemeral `?token=` query
  param validated in the handler — but that's defence-in-depth, not required.)
- **No queue.** Requests hit a worker directly. That means lower latency but **no
  backlog buffering and no automatic retries** — if no worker is available the gateway
  returns `no workers available` (retry) or times out. Limits: request timeout 2 min (no
  worker), processing timeout 5.5 min/request, payload 30 MB.

## The worker (FastAPI)

Based on the official [`worker-lb-websocket`](https://github.com/runpod-workers/worker-lb-websocket)
example (referenced from the [build-a-worker](https://docs.runpod.io/serverless/load-balancing/build-a-worker#optional-websocket-support)
docs). The WebSocket route is just FastAPI's `@app.websocket` decorator — a `while True`
loop that reads JSON, streams frames back, and ends each turn with a `done` frame:

```python
# app.py (excerpt)
import os, asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

@app.get("/ping")                      # required — LB health check
async def health_check():
    return {"status": "healthy"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:                    # persistent: many turns per connection
            data = await websocket.receive_json()
            prompt = data.get("prompt", "")
            if not prompt:
                await websocket.send_json({"error": "prompt is required"})
                continue
            words = f"Streaming response for: '{prompt}'".split()
            for i, word in enumerate(words[: int(data.get("max_tokens", 50))]):
                await websocket.send_json({"token": word, "index": i})   # stream back
                await asyncio.sleep(0.05)                                # sim. inference
            await websocket.send_json({"done": True, "total_tokens": len(words)})
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 80)))    # bind the exposed port
```

Swap the mock loop for real model inference (vLLM, a HF pipeline, etc.). The important
contract for the platform is only: **serve `/ping`, and bind `0.0.0.0:$PORT`.**

**Dockerfile** — a slim base is fine (the app is CPU-side FastAPI; the GPU, if any, is
your model's concern):

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt   # fastapi uvicorn[standard] websockets pydantic
COPY app.py .
EXPOSE 80
CMD ["python3", "app.py"]
```

## Walkthrough

### 1. Build & push the image (`--platform linux/amd64`)
```bash
docker build --platform linux/amd64 -t <your-registry>/gp17-ws:v1 .
docker push <your-registry>/gp17-ws:v1
```
✅ Live: pushed `<your-registry>/gp17-ws:v1` (digest `sha256:66453f…`). Tested locally first
(`docker run -p 8080:80 …` → `ws://localhost:8080/ws` streamed correctly) before deploying.

### 2. Create a template — **expose the HTTP port your app binds, and set `PORT` to match**
This is the crux. `runpodctl template create` defaults its exposed HTTP port to `8888`,
but the app binds `80`. If they disagree, the LB health check can never reach `/ping`,
the worker never becomes "ready", and every request to `<ep>.api.runpod.ai` hangs/`000`
even though the worker shows `running`. Align them explicitly:
```bash
runpodctl template create --name gp17-ws-tpl --serverless \
  --image <your-registry>/gp17-ws:v1 --container-disk-in-gb 10 \
  --ports '80/http' --env '{"PORT":"80"}'            # → template id (e.g. <template-id>)
```
✅ Live: template reported `ports ['80/http']`, `env {'PORT': '80'}`. (Equivalently, keep
the `8888/http` default and set `--env '{"PORT":"8888"}'` — the two just have to match.)

### 3. Create the endpoint as **type `LB`** (GraphQL `saveEndpoint`)
The REST `POST /v1/endpoints` schema has **no endpoint-type field** — it only makes
queue-based (`QB`) endpoints. Load-balancing endpoints are created with the GraphQL
`saveEndpoint` mutation and `type: "LB"` (Console: New Endpoint → **Endpoint Type →
Load Balancer** does the same) — the same `LB` creation recipe documented in golden path
[14](14-load-balancing-endpoint.md). `api.runpod.io/graphql` needs a browser-ish `User-Agent`
(Cloudflare), and LB endpoints require a **GPU tier** (`gpuIds`, e.g. `AMPERE_16`):
```bash
curl -s -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -H 'User-Agent: Mozilla/5.0' \
  -d '{"query":"mutation($input:EndpointInput!){saveEndpoint(input:$input){id name type templateId gpuIds}}",
       "variables":{"input":{"name":"gp17-ws-lb","templateId":"<template-id>","type":"LB",
         "gpuIds":"AMPERE_16","flashBootType":"FLASHBOOT",
         "scalerType":"REQUEST_COUNT","scalerValue":1,"idleTimeout":5,
         "workersMin":1,"workersMax":1}}}'
```
✅ Live: returned `{"id":"<endpoint-id>","type":"LB","gpuIds":"AMPERE_16", …}`.
> **`workersMin: 1` for a reliable first test.** Runpod's LB does **not** reliably count
> open WebSocket connections as "active work" for autoscaling — a scale-to-zero endpoint
> can leave you with `no workers available`/timeouts on the WS upgrade. Keeping one warm
> worker (`workersMin: 1`) removes cold-start flakiness while you verify; for production
> either keep 1 warm, or drive scaling with a lightweight HTTP `GET /ping` keepalive.
> Delete promptly after testing to stop the bill.

### 4. Wait for the worker to be routable (poll `/ping`)
`workers.running` in `GET https://api.runpod.ai/v2/<ep>/health` flips to `1` well before
the app answers — wait for `/ping` to return **HTTP 200**, not just for the worker to
exist. Always bound the client timeout (a not-yet-ready LB URL hangs, returning `000`):
```bash
EP=<endpoint-id>
for i in $(seq 1 9); do
  out=$(curl -s --max-time 12 -w '|HTTP%{http_code}' "https://$EP.api.runpod.ai/ping" \
        -H "Authorization: Bearer $RUNPOD_API_KEY")
  echo "try $i: $out"; case "$out" in *HTTP200*) break;; esac; sleep 8
done
```
✅ Live: `try 1/2: |HTTP000` → `try 3: {"status":"healthy"}|HTTP200` (ready ~20 s after
the image was already cached on the host).

## Verify it works — ✅ live 2026-07-13

**HTTP routes on the same endpoint URL:**
```
$ curl -s -X POST https://<endpoint-id>.api.runpod.ai/generate \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
    -d '{"prompt":"Hello from golden path 17","max_tokens":40,"temperature":0.5}'
{"generated_text":"Response to: 'Hello from golden path 17' (tokens=40, temp=0.5, request #1)"}

$ curl -s https://<endpoint-id>.api.runpod.ai/stats -H "Authorization: Bearer $RUNPOD_API_KEY"
{"total_requests":1,"active_websocket_connections":0}
```

**The WebSocket** — Python `websockets` client to `wss://<ep>.api.runpod.ai/ws`, Bearer
token as a connection header, `open_timeout` raised so the connect survives scale-up:
```python
import asyncio, json, websockets
async def main():
    url = "wss://<endpoint-id>.api.runpod.ai/ws"
    headers = {"Authorization": f"Bearer {RUNPOD_API_KEY}"}
    async with websockets.connect(url, additional_headers=headers, open_timeout=60) as ws:
        await ws.send(json.dumps({"prompt": "golden path 17 websocket test", "max_tokens": 20}))
        while True:
            msg = json.loads(await ws.recv())
            print(msg)
            if msg.get("done"): break
asyncio.run(main())
```
Observed stream (token frames → done frame):
```
{'token': 'Streaming', 'index': 0}
{'token': 'response', 'index': 1}
{'token': 'for:', 'index': 2}
{'token': "'golden", 'index': 3}
{'token': 'path', 'index': 4}
{'token': '17', 'index': 5}
{'token': 'websocket', 'index': 6}
{'token': "test'", 'index': 7}
{'done': True, 'total_tokens': 8}
```

**Persistent / bidirectional** — two prompts sent on **one** open socket, each streamed
back independently (proves it's a live duplex connection, not a one-shot request):
```
sent='first message'                  -> recv 5 tokens: Streaming response for: 'first message'
sent='second message on same socket'  -> recv 8 tokens: Streaming response for: 'second message on same socket'
```

**Auth enforced at the gateway:**
```
$ curl -s -w '|HTTP%{http_code}' https://<endpoint-id>.api.runpod.ai/ping
{"status":401,"title":"Unauthorized","detail":"no token provided"}|HTTP401
$ curl -s -w '|HTTP%{http_code}' .../ping -H "Authorization: Bearer BADKEY123"
{"status":401,"title":"Unauthorized","detail":"invalid api key"}|HTTP401
```

**`wscat` alternative** (no Python): `npm i -g wscat`, then
`wscat --connect "wss://<ep>.api.runpod.ai/ws" --header "Authorization: Bearer $RUNPOD_API_KEY"`
and type a JSON line — same token/done frames come back.

## Gotchas

- **Exposed HTTP port must equal the port the app binds.** The single biggest failure
  mode. `runpodctl template create` defaults to `8888/http`; the example app binds `80`.
  Mismatch → LB health check unreachable → worker shows `running` but `/ping` (and every
  request) hangs with HTTP `000`, and the endpoint "does nothing". Fix by setting both
  `--ports '<p>/http'` **and** `--env '{"PORT":"<p>"}'` to the same value (this path used
  `80`). Use a separate `PORT_HEALTH` only if your health server runs on a different port.
  This exposed-port == `PORT` == `PORT_HEALTH` contract is the load-balancing substrate's
  cardinal rule — golden path [14](14-load-balancing-endpoint.md) documents it in full; this
  path doesn't re-derive it.
- **WebSocket needs a load-balancing (`LB`) endpoint.** Queue-based endpoints have no
  worker-facing HTTP server and reject custom routes — the gateway answers
  `not allowed for QB API`. There's no `/ws` on `/run`-style endpoints.
- **REST can't create an LB endpoint.** `POST /v1/endpoints` only makes `QB`. Use GraphQL
  `saveEndpoint` with `type: "LB"` (needs `gpuIds` + `User-Agent: Mozilla/5.0`), or the
  Console's **Endpoint Type → Load Balancer**.
- **Autoscaling may ignore idle WS connections.** An open socket with no traffic isn't
  reliably counted as active work, so a `workersMin: 0` endpoint can scale to zero
  mid-session or refuse the upgrade with `no workers available`. Keep ≥1 warm worker, or
  emit a periodic HTTP keepalive, for anything long-lived.
- **Raise the client `open_timeout`.** The `websockets` default (~5 s) is too short when a
  worker is scaling up; use `open_timeout=60`. Symptom otherwise: connect fails with a
  timeout even though the endpoint is fine.
- **Bearer token on the *upgrade*, not per-message.** Pass `Authorization: Bearer` as a
  connection header on `websockets.connect(...)` (`additional_headers=`) — the auth is
  checked once at the HTTP upgrade, not on each frame.
- **No queue safety net.** No retries, no backlog buffering; a request with no available
  worker fails fast. Build retry/reconnect into the client. Hard limits: 2 min connect
  (no worker), 5.5 min processing/request, 30 MB payload.
- **Poll `/ping` for 200, with a bounded curl timeout.** `workers.running:1` ≠ routable;
  and an un-ready LB URL hangs — always `--max-time` your health poll or it blocks.

## Cost & cleanup
```bash
runpodctl serverless delete <endpoint-id>     # the LB endpoint (stops the warm worker's bill)
runpodctl template delete   <template-id>         # the template (delete any earlier attempts too)
runpodctl serverless list && runpodctl network-volume list && runpodctl pod list   # confirm clean
```
✅ All returned `{"deleted": true}` on the live run; no `gp17` endpoints/templates/pods
remained. **Keep costs near zero:** LB endpoints require a GPU tier, so a warm
`workersMin: 1` worker bills continuously — delete the moment you've verified. The pushed
image `<your-registry>/gp17-ws:v1` (~150 MB `python:3.10-slim` + FastAPI) was **left public**
so this doc references a real, pullable tag; storage-only, costs nothing to keep.

## Relation to other paths & skill gaps
- **[14 — load-balancing endpoint](14-load-balancing-endpoint.md)** is the shared substrate
  and the **prerequisite read** for this path: it stands up the same `LB` endpoint
  (`type:"LB"` via `saveEndpoint`), the exposed-port == `PORT` == `PORT_HEALTH` routing
  contract, and the `https://<ep>.api.runpod.ai/<route>` addressing. This path (WebSocket)
  adds only the `@app.websocket` route, the `wss://` scheme, and the raised `open_timeout`.
- **[12 — serverless streaming (`/stream`)](12-serverless-streaming.md)** is the
  queue-based cousin: server→client chunks for a *single* `/run` job, with the queue's
  durability. Use `/stream` when the client submits once and only listens; use WebSocket
  (this path) when the client keeps talking on a persistent connection.
- **Skill gap folded back:** creating an `LB` endpoint headlessly is **GraphQL
  `saveEndpoint` + `type:"LB"` + `gpuIds`** (REST `POST /v1/endpoints` can't) — worth
  noting alongside the multi-volume `saveEndpoint` recipe in
  [endpoint-workflows.md](../../runpod-usage/reference/endpoint-workflows.md), and the
  **exposed-port must equal `PORT`** rule is the load-balancing worker's cardinal setup
  step.
```
