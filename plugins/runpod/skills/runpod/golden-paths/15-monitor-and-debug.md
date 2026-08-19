# Golden path 15 — monitor & debug serverless (is my endpoint healthy, why is a job failing)

**Goal:** the observability toolkit for a running serverless endpoint — answer "are my
workers healthy?", "why is this job stuck?", and "what did the worker actually do?" using
`/health` worker+job counts, the job `/status` lifecycle, and worker logs. This is
the loop you run when a request is slow, stuck `IN_QUEUE`, or `FAILED`.
**Status:** ✅ **COVERED — live-verified 2026-07-13, re-verified against runpodctl v2.9.0 on
2026-08-06. Command surface re-checked against runpodctl v2.10.0 on 2026-08-19** (the
`serverless logs` / `pod logs` route below is verified from the shipped v2.10.0 binary's
interface, not from a live log capture — the captured frames are still the 2026-08-06 SSE run
against the identical upstream service). The 2026-07-13 pass deployed a tiny CPU scale-to-zero echo endpoint
(`python:3.11-slim` + `runpod`), sent one async job, and captured `/health` moving **idle →
ready → throttled → ready** while a job moved **`IN_QUEUE` → `IN_PROGRESS` → `COMPLETED`**, the
completed `/status` carrying `delayTime`/`executionTime`/`workerId`, the **v2 REST worker-log
SSE stream** returning `system` and `container` frames, and config toggles applied via v1
`PATCH` (HTTP 200 each). The 2026-08-06 pass re-ran the read path with `runpodctl serverless
health`/`status`/`run` against a live GPU endpoint and captured the **failure** branch end to
end: one job walked `IN_QUEUE` → `IN_PROGRESS` → **`FAILED`** with a server-side retry, and the
worker `container` log named the real cause the `/status` `error` string hid.
**Lane(s):** runpodctl (`serverless health` / `run` / `status` / `update`, v2.9.0+;
`serverless logs` / `pod logs`, v2.10.0+) + REST/HTTP (`/health`, `/status`, v1 `PATCH`) +
v2 REST worker logs (`GET /v2/serverless/{id}/workers/{workerId}/logs`, SSE) + Runpod MCP
(`stream-worker-logs`, `list-endpoint-workers`, `endpoint-health`) + Console
(Logs/Workers/Metrics tabs)

## When to use this
Reach for this path whenever a deployed endpoint isn't behaving:
- A request sits `IN_QUEUE` far longer than expected (→ check worker counts for `throttled`
  or zero-`ready`).
- A job returns `FAILED` and you need the handler-side traceback (→ worker container logs).
- You want to confirm an endpoint is warm/scaled before a burst (→ `/health` `ready`/`idle`).
- You changed the config (max workers, region) and want to see it take.

It pairs with any deploy path ([05](05-model-to-endpoint-pipeline.md),
[09](09-custom-serverless-dev-loop/README.md), [10](10-multi-region-ha-serverless.md)) — those get the
endpoint up; this one tells you whether it's healthy and why a job did what it did.

## The four signals (and where each comes from)

| Question | Signal | First choice | Zero-dependency fallback |
| --- | --- | --- | --- |
| Are workers healthy / how many? | worker state counts | `runpodctl serverless health <id>` · MCP `endpoint-health` | `GET api.runpod.ai/v2/<id>/health` |
| Where is *this* job? | job state + timings | `runpodctl serverless status <id> <job-id>` · MCP `get-job-status` | `GET api.runpod.ai/v2/<id>/status/<job-id>` |
| What did the worker *do*? | container/system logs | `runpodctl serverless logs <id>` · MCP `stream-worker-logs` | `GET v2-rest.runpod.io/v2/serverless/<id>/workers/<worker-id>/logs` (SSE) · Console Workers tab |
| Did my config change take? | endpoint config | `runpodctl serverless update <id> …` then `serverless get <id>` | v1 `PATCH`/`GET rest.runpod.io/v1/endpoints/<id>` |

All four signals are free to read. The raw HTTP column is what you hand a user for copy-paste,
what a non-Runpod client speaks, and what you fall back to on an older binary.

**All four are first-class `runpodctl` commands as of v2.10.0** — `serverless health`,
`serverless status`, `serverless update` (v2.9.0+) and `serverless logs` (v2.10.0+). The
v2.10.0 `serverless` surface is `create`, `delete`, `get`, `health`, `list`, `logs`, `run`,
`status`, `update`. Mind the version floor: on a **v2.9.0** binary there is no `logs`
subcommand, and the worker-log signal has to come from the v2 REST SSE path, the Runpod MCP
`stream-worker-logs` tool, or the Console **Workers** tab. Check `runpodctl version` first.

## Prerequisites
- `RUNPOD_API_KEY` resolvable (the same key authorizes `api.runpod.ai/v2`, `rest.runpod.io/v1`,
  and `v2-rest.runpod.io/v2`). `runpodctl` also reads the key saved by `runpodctl doctor`.
- A deployed endpoint id. Below uses a tiny CPU echo endpoint (build any handler; see
  [05](05-model-to-endpoint-pipeline.md) for the two-step template→endpoint pattern).

## 1. `/health` — worker & job counts (start here)

```bash
runpodctl serverless health <endpoint-id>            # v2.9.0+, pretty-prints; -o yaml also works
# zero-dependency equivalent:
curl -s https://api.runpod.ai/v2/<endpoint-id>/health -H "Authorization: Bearer $RUNPOD_API_KEY"
```
The CLI passes the invoke API's response through verbatim, so the two agree field for field —
✅ verified live 2026-08-06, run back to back against the same endpoint:
```jsonc
// runpodctl serverless health <id>   (and curl, minus the indentation)
{"jobs":{"completed":27,"failed":0,"inProgress":0,"inQueue":0,"retried":0},
 "workers":{"idle":0,"initializing":0,"ready":0,"running":0,"throttled":1,"unhealthy":0}}
```
✅ Live — a second endpoint idle, then holding a queued job, then running it, then after it
failed:
```jsonc
// idle, scale-to-zero
{"jobs":{"completed":31,"failed":0,"inProgress":0,"inQueue":0,"retried":0},
 "workers":{"idle":2,"initializing":0,"ready":2,"running":0,"throttled":0,"unhealthy":0}}
// a job queued, a worker coming up
{"jobs":{"completed":31,"failed":0,"inProgress":0,"inQueue":1,"retried":0},
 "workers":{"idle":1,"initializing":1,"ready":1,"running":0,"throttled":0,"unhealthy":0}}
// job picked up
{"jobs":{"completed":31,"failed":0,"inProgress":1,"inQueue":0,"retried":0},
 "workers":{"idle":0,"initializing":1,"ready":0,"running":1,"throttled":0,"unhealthy":0}}
// after it failed (note failed + retried)
{"jobs":{"completed":31,"failed":1,"inProgress":0,"inQueue":0,"retried":1},
 "workers":{"idle":1,"initializing":0,"ready":1,"running":1,"throttled":0,"unhealthy":0}}
```

**Worker states** (the live `/health` payload carries all six — richer than the two-field
`{idle,running}` shown in some docs):

| State | Meaning | Billed |
| --- | --- | --- |
| `initializing` | pulling image / loading code | yes |
| `idle` / `ready` | up, waiting for work | no (idle) |
| `running` | processing a request | yes |
| `throttled` | host is resource-constrained; can't run right now | no |
| `unhealthy` | crashed; auto-retried for up to 7 days | no |

**`jobs` counters** aggregate the queue: `inQueue`, `inProgress`, `completed`, `failed`,
`retried`. SDK equivalents exist (`endpoint.health()` in the Python/JS SDKs).

### Reading it: healthy vs. stuck
- **Healthy & scaled:** `ready`/`idle` ≥ 1 and `inQueue` draining. A request will be picked up.
- **Stuck `IN_QUEUE`:** `inQueue` > 0 but `running`/`ready` = 0. Look at *why* no worker is
  free — the two common causes below.
- **`throttled` > 0:** the host pool is momentarily constrained (verified live). Workers usually
  recover on their own; a **persistently** throttled endpoint on a scarce GPU means you pinned
  too narrow a pool — widen GPU types or data centers.
- **`unhealthy` > 0:** the worker crashed on start or mid-job — go straight to the logs.

### `/health` counts and the worker list are two different views
`/health` is the scheduler's rolled-up gauge; the v2 worker list (next section) enumerates the
actual worker records. They can disagree, and neither is wrong — ✅ observed live 2026-08-06,
the two calls made back to back against the same endpoint:
```jsonc
// GET /v2/<id>/health
"workers":{"idle":1,"initializing":0,"ready":1,"running":1,"throttled":0,"unhealthy":0}
// GET v2-rest.runpod.io/v2/serverless/<id>/workers  →  summary
{"idle":1,"initializing":2,"running":0,"throttled":2,"total":5,"unhealthy":0}
```
Use `/health` for "can this endpoint take work right now"; use the worker list when you need a
specific `workerId`, its data center, or its image. Note the worker-list `summary` has **no
`ready` key** — `ready` exists only on `/health`.

## 2. Job `/status` — the request lifecycle

```bash
# submit and get a job id back immediately (v2.9.0+)
runpodctl serverless run <endpoint-id> --input '{"prompt":"hi"}' --no-wait
# poll it — one check, or --wait to block until terminal
runpodctl serverless status <endpoint-id> <job-id>
runpodctl serverless status <endpoint-id> <job-id> --wait 5m
# zero-dependency equivalent:
curl -s https://api.runpod.ai/v2/<endpoint-id>/status/<job-id> -H "Authorization: Bearer $RUNPOD_API_KEY"
```
Job states: `IN_QUEUE` → `IN_PROGRESS` (a.k.a. `RUNNING`) → `COMPLETED`, or `FAILED` /
`CANCELLED` / `TIMED_OUT`.

✅ Live 2026-08-06 — one async job (deliberately empty `--input '{}'`) walking the whole path to
a **real failure**, with `/health` in lockstep:
```
17:42:13  IN_QUEUE                                     health workers={idle:1,initializing:1,ready:1}  jobs={inQueue:1}
17:42:49  IN_QUEUE     worker z3jr9rv2k3tt2y → RUNNING
17:43:02  IN_PROGRESS  delayTime=61372   workerId=z3jr9rv2k3tt2y                                        jobs={inProgress:1}
17:43:48  IN_PROGRESS  delayTime=101050  retries=1     # server-side retry; delayTime was recomputed    jobs={retried:1}
17:44:30  FAILED       delayTime=101050  executionTime=42078  retries=1                                 jobs={failed:1,retried:1}
```
The terminal payload, straight from `runpodctl serverless status`:
```jsonc
{"delayTime":101050,          // ms the job waited before its (final) attempt started
 "error":"job timed out after 1 retries",
 "executionTime":42078,       // ms the handler side actually held it
 "id":"bd9227e3-…-u1",
 "retries":1,                 // the platform re-dispatched it once
 "status":"FAILED",
 "workerId":"z3jr9rv2k3tt2y"} // which worker served it — feed this to worker logs
```
On a terminal non-`COMPLETED` status the CLI still prints that payload on **stdout**, adds
`{"error":"job … finished with status FAILED","code":"job_failed"}` on **stderr**, and exits
**1** (observed). A `COMPLETED` job's payload additionally carries `output` with whatever the
handler returned. `error` and `retries` only appear when the platform produced them.

`delayTime` vs. `executionTime` is the key split: a big `delayTime` with a small
`executionTime` = a scheduling/scaling problem (cold start, throttle, `IN_QUEUE`), not a slow
handler. The `workerId` is your handle for the next step. Note that a retry **resets**
`delayTime` to the wait before the final attempt — the 61 s → 101 s jump above is the retry, not
a lengthening queue.

> **Do not trust the `error` string alone.** `"job timed out after 1 retries"` reads like a
> capacity or timeout problem. The worker log (next section) showed the actual cause was the
> empty payload — see the worked example below. This is the failure mode written up in
> [`../../runpod-usage/reference/gotchas.md`](../../runpod-usage/reference/gotchas.md)
> ("Serverless job goes `IN_PROGRESS` then times out"), reproduced here live.

> **Job-state semantics** live in
> [`../../runpod-usage/reference/endpoint-workflows.md`](../../runpod-usage/reference/endpoint-workflows.md);
> always `/run` + poll `/status` (bound the loop) rather than blocking on `/runsync` for
> anything slow. `runpodctl serverless run` does exactly that for you.

## 3. Worker logs — what the worker actually did

Endpoint (aggregate, 90-day retained) logs and per-worker (ephemeral, on-host) logs are both
in the Console (**Logs** and **Workers** tabs). For programmatic/agent access there are three
routes, in preference order: the CLI (v2.10.0+), the MCP tool, or the raw v2 REST stream.

### Route A — `runpodctl serverless logs` (v2.10.0+, prefer this)
```bash
# every worker's recent logs, json lines — one {source,line,ts,workerId} per line
runpodctl serverless logs <endpoint-id>

# narrow to the worker that served the failed job (workerId comes from /status)
runpodctl serverless logs <endpoint-id> --worker <worker-id> --source container

# why a worker will not start, last hour of platform lines
runpodctl serverless logs <endpoint-id> --since 1h --source system

# live tail; picks up workers that scale up while it runs
runpodctl serverless logs <endpoint-id> --follow
```
Logs belong to a **worker**, not the endpoint, so without `--worker` this resolves the
endpoint's workers and reads them all at once, tagging each line with its `workerId` — which is
what you want when you don't yet know which worker misbehaved. Flags: `--source
container|system|both` (default `both`), `--tail 0-5000` (default 100, `0` = live only),
`--since 30m|2h|7d|<rfc3339>` (overrides `--tail`), `--worker`, `--follow`, and `--max-wait`
(default `5s`, how long to wait for output before exiting when *not* following).

Two things this buys over the raw stream: it is **json lines, not SSE**, so `| jq` works with no
frame parsing, and without `--follow` it **terminates on its own** once the replayed lines stop
arriving instead of hanging on an open connection. With `--follow` it reconnects itself if the
connection drops.

```bash
# the handler's own error lines for one worker
runpodctl serverless logs <endpoint-id> --worker <worker-id> --source container \
  | jq -r 'select(.line | contains("ERROR")) | "\(.ts) \(.line)"'
```

> **Crash-loop tell:** repeated `system` `start container` lines with **no** `container` output
> means the container exits before the handler runs. Jobs then pile up `IN_QUEUE` even though
> `/health` shows workers — nothing is wrong with capacity, the image is wrong.

Same story for pods: `runpodctl pod logs <pod-id>` (identical flags minus `--worker`) is the
first thing to run on a pod that never becomes usable, and `--source system` is where a stalled
image pull or a `create container` that never reaches `start` shows up.

### Route B — v2 REST logs (SSE, or a pre-v2.10.0 binary)
```bash
# workerId comes from /status.workerId or the workers list below
curl -sN -m 20 "https://v2-rest.runpod.io/v2/serverless/<endpoint-id>/workers/<worker-id>/logs?source=container&tail=100" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Accept: text/event-stream'
```
It's a **Server-Sent Events** stream — each frame is an `id:` line carrying the timestamp plus a
`data: {"source","line","ts"}` line; bound it with `curl -m <sec>`. Query params:
`source=container|system` (omit for both), `tail=<N>` (historical lines to backfill, API default
100, max 5000; `0` = live only), `since=<RFC3339>` (resume from a timestamp; `tail` is ignored
when it is set).

✅ Live 2026-08-06 — `source=container` on the worker that served the failed job, showing the
fitness checks and then the real cause, twice (the original attempt and the retry):
```
id: 2026-08-06T17:43:01.179039264Z
data: {"source":"container","line":"--- Starting Serverless Worker |  Version 1.11.0 ---","ts":"2026-08-06T17:43:01.179039264Z"}
data: {"source":"container","line":"{\"requestId\": null, \"message\": \"Running 7 fitness check(s)...\", \"level\": \"INFO\"}", ...}
data: {"source":"container","line":"{\"requestId\": null, \"message\": \"GPU binary test passed: 1 GPU(s) healthy (CUDA 12.8)\", \"level\": \"INFO\"}", ...}
data: {"source":"container","line":"{\"requestId\": null, \"message\": \"All fitness checks passed. (919.19ms)\", \"level\": \"INFO\"}", ...}
data: {"source":"container","line":"{\"requestId\": null, \"message\": \"Failed to get job. | Error Type: Exception | Error Message: Job has missing field(s): id or input.\", \"level\": \"ERROR\"}", "ts":"…T17:43:02.47Z"}
data: {"source":"container","line":"{\"requestId\": null, \"message\": \"Failed to get job. | Error Type: Exception | Error Message: Job has missing field(s): id or input.\", \"level\": \"ERROR\"}", "ts":"…T17:43:42.14Z"}
```
That is the whole point of this step: `/status` said *"job timed out after 1 retries"* on a
worker whose seven fitness checks all passed. The container log says the worker was **healthy
and rejected the payload**. When a handler does serve a request normally you get per-request
`Started`/`Finished` lines with a real `requestId` you can match to the job id.

`source=system` carries the host/lifecycle view — ✅ live, the same worker's cold start and
scale-down:
```
data: {"source":"system","line":"create container justinrunpod/vo:v1","ts":"2026-08-06T17:42:52Z"}
data: {"source":"system","line":"start container for justinrunpod/vo:v1: begin","ts":"2026-08-06T17:42:52Z"}
data: {"source":"system","line":"model ready","ts":"2026-08-06T17:44:37Z"}
data: {"source":"system","line":"stop container a6a111ed…","ts":"2026-08-06T17:45:27Z"}
data: {"source":"system","line":"remove container","ts":"2026-08-06T17:45:30Z"}
```
Use `container` for your handler's stdout/stderr and the SDK's per-request lines; `system` to
diagnose slow cold starts (image pull/extract progress shows up here frame by frame) and to
confirm a worker actually went away.

To find worker ids without a job in hand, list the endpoint's workers (also v2 REST):
```bash
curl -s https://v2-rest.runpod.io/v2/serverless/<endpoint-id>/workers -H "Authorization: Bearer $RUNPOD_API_KEY"
```
✅ Live — returns `endpointVersion`, a `summary` (`idle`/`initializing`/`running`/`throttled`/
`unhealthy`/`total`), and one object per worker with `id`, `status`
(`RUNNING`/`IDLE`/`THROTTLED`/`INITIALIZING`/`UNHEALTHY`), `gpuTypeId`, `gpuCount`,
`dataCenterId`, `image`, `startedAt`, `isStale`, `version`:
```json
{"dataCenterId":"US-NC-1","gpuCount":1,"gpuTypeId":"NVIDIA GeForce RTX 4090",
 "id":"z3jr9rv2k3tt2y","image":"justinrunpod/vo:v1","isStale":false,
 "startedAt":"2026-08-05T21:42:31.705Z","status":"RUNNING","version":2}
```
`runpodctl serverless get <id> --include-workers` also lists workers, but it goes through the
v1 control plane and returns the raw worker records — far more fields, including the endpoint's
`RUNPOD_AI_API_KEY`/`RUNPOD_ENDPOINT_SECRET` in `env`. Prefer the v2 list (or the MCP tool)
when you just need ids and states, and don't paste `--include-workers` output into a ticket.

### Route C — Runpod MCP `stream-worker-logs`
The hosted Runpod MCP (`https://mcp.getrunpod.io/`) wraps the exact same endpoint as a tool:
`list-endpoint-workers` → pick a `workerId` → `stream-worker-logs` (params `source`, `tail`,
`since`, `maxWaitMs`). It returns a bounded, already-parsed snapshot — `{"items":[{"source",
"line","ts"}…],"count","truncated"}` — a convenient shape inside an agent (✅ used live
2026-08-06). This is the same tool golden path
[07](07-network-volume-handoff.md) used to distinguish a healthy worker from a bad payload.
Since v2.10.0 it is a **convenience over Route A, not a capability the CLI lacks**; pick it when
MCP is already connected and you want parsed frames without shelling out.

> Routes B and C live on the **v2 serverless REST service** (`v2-rest.runpod.io/v2`), not on
> `rest.runpod.io/v1` — v1 has no worker-log path at all. That is a statement about which
> service you call, *not* about the endpoint's own `version` field: ✅ verified live that a
> `version: 1` endpoint's workers and logs are readable through the v2 route (HTTP 200, real
> frames). If you can't reach the v2 logs path, use the MCP tool or the Console **Workers** tab
> (click a worker → its logs + request history).

## 4. Config-change events (max-workers / region changes fire alerts)

Endpoint config is edited with a v1 `PATCH`; each applied change is a config-change event
(the same events surface as endpoint alerts/notifications). `runpodctl serverless update` is
the first-class wrapper — source-verified in the v2.9.0 tree, it issues exactly that
`PATCH /endpoints/<id>` against `rest.runpod.io/v1`:
```bash
# scale ceiling — CLI
runpodctl serverless update <endpoint-id> --workers-max 3
# other flags on the same command: --workers-min --idle-timeout --name --template-id
#                                  --scale-by --scale-threshold --model-reference --clear-models
# confirm
runpodctl serverless get <endpoint-id>
```
The CLI has **no data-center flag**, so a region change is still a raw `PATCH` (verified live
2026-07-13, HTTP 200 each):
```bash
# network region / data-center set
curl -s -X PATCH https://rest.runpod.io/v1/endpoints/<endpoint-id> \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"dataCenterIds":["EU-RO-1","EU-CZ-1"]}'
# ...and the curl equivalent of the CLI call above
curl -s -X PATCH https://rest.runpod.io/v1/endpoints/<endpoint-id> \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"workersMax":3}'
curl -s https://rest.runpod.io/v1/endpoints/<endpoint-id> -H "Authorization: Bearer $RUNPOD_API_KEY"
```
Changing **max workers** (capacity) or the **network region / data-center** set are the two
config changes worth watching — they directly move the `/health` worker counts and where jobs
can schedule. Re-read `/health` right after a change to confirm workers redistribute.

## The debug loop (putting it together)

1. **`runpodctl serverless health <id>`** — is any worker `ready`/`running`? If all
   `throttled`/`unhealthy` or the endpoint won't scale, that's the problem, not your handler.
2. **`runpodctl serverless status <id> <job-id>`** — where is the job? Split `delayTime`
   (queue/scaling) vs. `executionTime` (handler). Grab `workerId`. Exit code 1 + `job_failed`
   means the job itself failed, not the call.
3. **`runpodctl serverless logs <id> --worker <workerId> --source container`** (v2.10.0+; MCP
   `stream-worker-logs` or the v2 REST SSE path on an older binary) — read the fitness checks
   and the per-`requestId` lines. A `FAILED` job's real cause is here, and it is often *not*
   what `/status.error` says.
4. **Config** — if capacity/region is the constraint, `runpodctl serverless update
   --workers-max` (or `PATCH` `dataCenterIds`) and re-check health.

## Gotchas
- **`serverless logs` needs runpodctl ≥ v2.10.0** — it does not exist on v2.9.0, where the
  worker-log signal has to come from the v2 REST logs path, the Runpod MCP
  `stream-worker-logs`, or the Console Workers tab. `runpodctl version` first; the Homebrew tap
  can lag the GitHub release.
- **`/status.error` can name the wrong culprit** — seen live: `"job timed out after 1 retries"`
  on a worker whose fitness checks all passed; the container log showed it was rejecting the
  request payload. Always read the worker log before blaming capacity or the image.
- **Worker logs are ephemeral, and `container` dies with the container** — ✅ observed: two
  minutes after the worker's `remove container` system line, `source=container` returned **zero**
  frames for that worker while `source=system` still returned its lifecycle history. Capture
  container logs *while the worker is up*. Aggregate **endpoint** logs (Console Logs tab) are
  retained 90 days; for permanent logs, write to a network volume or an external sink.
- **The raw v2 logs path is SSE, not JSON** — on Route B parse `data:` frames and always
  time-bound the read (`curl -m`), or it will hang tailing live output: a worker with nothing to
  say holds the connection open and sends nothing, so an unbounded read never returns. Route A
  (`serverless logs`) removes both hazards — json lines, and it exits on its own without
  `--follow` (`--max-wait` bounds that).
- **`throttled` is usually transient** — it means the host pool is momentarily constrained
  (seen live: workers flipped `throttled` then recovered on their own within ~30 s). A
  scale-to-zero endpoint can also show a lone `throttled` leftover record while genuinely idle.
  Only a *persistent* throttle on a narrow/scarce GPU pool needs action (widen GPU types / DCs).
- **`delayTime` includes cold-start + throttle, and resets on a retry** — a large `delayTime` on
  a scale-to-zero endpoint is often just the first worker warming. If `retries` ≥ 1, `delayTime`
  describes the *last* attempt, not the total time since submission.
- **`/health` and the v2 worker list can disagree** — different views (scheduler gauge vs.
  worker records), and only `/health` has a `ready` count. Don't treat a mismatch as a bug.
- **Log throttling** — a worker that floods stdout can have logs dropped; keep handler logging
  structured and modest.

## Cost & cleanup
The endpoint is CPU scale-to-zero (`workersMin 0`) — ~$0 idle. All monitoring calls
(`serverless health`/`status`/`get`, `/health`, `/status`, worker logs, `PATCH`/`GET`) are free;
only the job itself bills, and the worker returns to idle on its own (✅ confirmed live: the
worker's `stop container` / `remove container` system lines landed ~1 min after the job went
terminal).
```bash
runpodctl serverless delete <endpoint-id>
runpodctl template delete <template-id>
runpodctl serverless list && runpodctl pod list && runpodctl network-volume list   # confirm clean
```
The pushed image `<your-registry>/gp15-echo:v1` (a ~150 MB `python:3.11-slim` + `runpod` echo
handler that returns its input plus `RUNPOD_POD_ID`/`RUNPOD_DC_ID`) is left public so this doc
cites a real, pullable tag; it costs nothing.

## Skill facts confirmed / folded back
- **All four signals are first-class CLI commands as of v2.10.0** — `serverless health` and
  `serverless status` hit the invoke service (`api.runpod.ai/v2`) and pass its JSON through
  verbatim; `serverless update` `PATCH`es the v1 control plane; `serverless logs` (v2.10.0)
  closed the last gap, wrapping the v2 worker-log stream as json lines with its own worker
  resolution and reconnect. Three of the four arrived in v2.9.0, so a doc pinned to that release
  reads the log signal as MCP-only — it isn't.
- **`/health` returns six worker-state fields** (`idle`, `initializing`, `ready`, `running`,
  `throttled`, `unhealthy`) — richer than the `{idle,running}` shape in the operation
  reference, and richer than the v2 worker-list `summary`, which has no `ready`.
- **The `job_failed` exit path is real, not just documented** — a terminal `FAILED` job prints
  its payload on stdout, `{"code":"job_failed"}` on stderr, and exits 1, matching
  [`../../runpodctl/reference/output-and-errors.md`](../../runpodctl/reference/output-and-errors.md).
- **`/status` gains `error` and `retries` on the failure path** — and `delayTime` is recomputed
  per attempt, so `delayTime` + `executionTime` does not reconstruct wall-clock across a retry.
- **Worker log streaming is a real, reachable v2 REST endpoint** —
  `GET https://v2-rest.runpod.io/v2/serverless/<id>/workers/<workerId>/logs` (SSE, params
  `source`/`tail`/`since`), and `.../workers` lists workers with status/GPU/DC. Both work for
  `version: 1` endpoints too. Both the Runpod MCP (`list-endpoint-workers` +
  `stream-worker-logs`) and `runpodctl serverless logs` (v2.10.0+) wrap it — the CLI does the
  worker resolution for you, so `--worker` is optional.
- **`serverless get --include-workers` echoes endpoint secrets** — it returns raw v1 worker
  records including `RUNPOD_AI_API_KEY`/`RUNPOD_ENDPOINT_SECRET` in `env`. Use the v2 worker
  list when you only need ids and states.
