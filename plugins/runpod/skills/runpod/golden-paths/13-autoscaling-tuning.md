# Golden path 13 — autoscaling tuning (scaler types + worker knobs under load)

**Goal:** understand how serverless scaling *actually* behaves so you can trade cost
against latency on purpose, not by guessing. Five knobs govern it — **active (min)
workers, max workers, scaler type + value, idle timeout, execution timeout** — and the
scaler comes in two flavors (**Request Count** vs **Queue Delay**) that ramp very
differently under a burst. This path proves both by firing real bursts at a CPU endpoint
and **watching the worker count climb** on `GET /v2/<id>/health`.
**Status:** ✅ **COVERED — live-verified 2026-07-13** end to end. Built a tiny CPU handler
that sleeps 8 s/job (`<your-registry>/gp13-scale:v1`), deployed one endpoint
(`workersMin 0`, `workersMax 3`, `idleTimeout 5`), and ran **four real bursts**:
**Request Count (value 1)** from cold scaled **0 → 1 → 2 running** as the queue persisted,
and with 3 workers already warm reached **running = 3 (= max)**; **Queue Delay (4 s)** on
the same burst stayed **conservative at 2 running**. Reconfigured live between runs with
`runpodctl serverless update --scale-by`. Real `/health` snapshots below.
**Lane(s):** docker (tiny handler) + runpodctl **v2.3+** (`serverless create/update
--scale-by requests|delay --scale-threshold N`, `--workers-min/-max`, `--idle-timeout`) +
Runpod REST (`/run`, `/health`, `GET /v1/endpoints/<id>`)

## Prerequisites
- Shared setup first: [../README.md](README.md#before-you-run-any-path-shared-prerequisites) and
  [getting-started.md](../../runpod-usage/reference/getting-started.md) (auth resolution, SSH,
  companion-CLI credentials).
- `RUNPOD_API_KEY` resolvable (runpodctl + REST). Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`.
- `docker` running and `docker login` to a registry you can push to (`<your-registry>`, e.g. your
  Docker Hub user) — you build and push the tiny sleep handler below.
- `runpodctl` installed + authenticated, **v2.3+** for the `--scale-by`/`--scale-threshold` flags.

## When to use this
Whenever an endpoint is **too slow under load** (requests pile up before workers appear)
or **too expensive** (workers stay warm doing nothing). Before adding workers, check
whether **per-worker concurrency** ([18](18-concurrent-handler.md)) fixes
it more cheaply — concurrency raises what *one* worker handles; autoscaling adds *more*
workers. Tune scaling once concurrency is right.

## The five knobs

| Knob | runpodctl flag | Default | What it does | Cost / latency lever |
| --- | --- | --- | --- | --- |
| **Active (min) workers** | `--workers-min` | 0 | Workers kept **warm & always billed** — kills cold starts | ↑ = lower latency, **higher $** (billed idle). Keep **0** for scale-to-zero. |
| **Max workers** | `--workers-max` | 3 | Hard **ceiling** on concurrent workers (also a cost cap) | ↑ = more throughput headroom, higher potential $. Set ~20 % over expected peak. |
| **Scaler type** | `--scale-by requests\|delay` | queue delay | How aggressively new workers are added (see below) | `requests` = responsive; `delay` = cheaper/higher-utilization |
| **Scaler value / threshold** | `--scale-threshold N` | 4 | requests → jobs-per-worker target; delay → seconds of wait before adding | lower = more aggressive |
| **Idle timeout** | `--idle-timeout` | 5 s | How long a worker stays warm (billed) after finishing before scaling down | ↑ = fewer cold starts on bursty traffic, **more idle $** |

> **Execution timeout** (`--execution-timeout`, default **600 s**) and **Job TTL**
> (24 h) aren't scaling knobs but bound each job — see
> [endpoint settings](https://docs.runpod.io/serverless/endpoints/endpoint-configurations)
> and the workspace notes on TTL vs execution timeout.

## The two scaler types

Both are set the same way; the difference is *when* a worker gets added.

| | **Request Count** (`--scale-by requests`) | **Queue Delay** (`--scale-by delay`) |
| --- | --- | --- |
| Rule | `workers = ceil((inQueue + inProgress) / value)` | add a worker when a request has **waited > threshold** (default 4 s) |
| `value` meaning | jobs-per-worker; **1 = most responsive** (a worker per pending job) | seconds of tolerated queue wait |
| Behavior | **aggressive** — provisions ahead of the backlog | **lazy** — tolerates a small queue for higher utilization |
| Pick it for | LLM / short, bursty, latency-sensitive requests | steady or batch traffic where a few seconds' delay is fine |

**How the runpodctl flags map to the stored config** (verified via `GET /v1/endpoints/<id>`):

| Flag | `scalerType` | `scalerValue` |
| --- | --- | --- |
| `--scale-by requests --scale-threshold 1` | `REQUEST_COUNT` | `1` |
| `--scale-by delay --scale-threshold 4` | `QUEUE_DELAY` | `4` |

> runpodctl **v2.3** removed the older `--scaler-type REQUEST_COUNT / --scaler-value`
> flags — use `--scale-by` + `--scale-threshold`. (In **v1** REST and GraphQL the stored
> fields are still named `scalerType`/`scalerValue`.)

**On v2 REST the same two knobs are shaped differently.** `GET /v2/serverless/<id>` returns
a scaler-specific object instead of a shared `value`, and the idle timeout sits under
`workers`:

| Meaning | v1 REST / GraphQL | v2 REST |
| --- | --- | --- |
| aggressive, on in-flight requests | `scalerType: REQUEST_COUNT`, `scalerValue: 1` | `scaling: {type: "REQUEST_COUNT", requestCount: 1}` |
| lazy, on queue wait | `scalerType: QUEUE_DELAY`, `scalerValue: 4` | `scaling: {type: "QUEUE_DELAY", queueDelay: 4}` |
| idle scale-down | `idleTimeout: 5` | `workers: {…, idleTimeout: 5}` |

`queueDelay` is seconds and accepts fractions (min `0.5`); `requestCount` is an integer
(min `1`); `idleTimeout` is `1`–`3600` and on a queue-based endpoint scaling on
`requestCount` it is **rejected on create and update** — not silently ignored.

You only need the right-hand column when calling **v2 REST by hand**. Neither CLI makes you
write it, but for different reasons, and the distinction matters:

- **runpodctl** never talks to v2 REST at all — `serverless create` goes through GraphQL
  `saveEndpoint` and `serverless update` through v1 REST, both of which take the flat
  `scalerType`/`scalerValue`/`idleTimeout` natively. Note `--scale-threshold` is an integer
  with a floor of 1, so runpodctl **cannot express a fractional `queueDelay`** like `0.5`;
  use v2 REST or the Console for that.
- **The Runpod MCP server** keeps the flat `scalerType`/`scalerValue` parameters and maps them
  onto the nested v2 body for you. A server old enough to predate the reshape sends the flat
  shape straight through and gets a 422 on both `create-endpoint` and `update-endpoint`; the
  tell is a `create-endpoint` with no `endpointType` parameter.

## Walkthrough (verified commands)

### 1. A tiny handler that sleeps (so a burst actually queues)
The whole point is to make jobs *last* long enough to watch the queue build and workers
appear. `python:3.11-slim` + `runpod`, ~8 s/job:
```python
# handler.py
import runpod, time, os, socket
SLEEP = float(os.environ.get("SLEEP_SECONDS", "8"))
def handler(job):
    s = float(job.get("input", {}).get("sleep", SLEEP))
    start = time.time(); time.sleep(s)
    return {"worker": socket.gethostname(), "slept": s, "elapsed": round(time.time()-start, 3)}
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
Build (amd64 always), test locally, push:
```bash
docker build --platform=linux/amd64 -t <your-registry>/gp13-scale:v1 .
echo '{ "input": { "sleep": 1 } }' > test_input.json
docker run --rm --platform=linux/amd64 -v "$PWD/test_input.json:/test_input.json" <your-registry>/gp13-scale:v1
# → Handler output: {'worker': ..., 'slept': 1.0, 'elapsed': 1.001}   ✅
docker push <your-registry>/gp13-scale:v1
```

### 2. Deploy: scale-to-zero, max 3, Request Count value 1
Two-step (template → endpoint), exactly like [05](05-model-to-endpoint-pipeline.md):
```bash
runpodctl template create --name gp13-tpl --serverless \
  --image <your-registry>/gp13-scale:v1 --container-disk-in-gb 10        # → template id <template-id>

runpodctl serverless create --template-id <template-id> --name gp13-reqcount \
  --compute-type CPU --workers-min 0 --workers-max 3 \
  --scale-by requests --scale-threshold 1 --idle-timeout 5 \
  --data-center-ids EU-RO-1                                            # → endpoint id <endpoint-id>
```
✅ The create response echoes the stored config — proving the flag→field mapping:
```json
{ "id": "<endpoint-id>", "scalerType": "REQUEST_COUNT", "scalerValue": 1,
  "idleTimeout": 5, "workersMax": 3, "flashboot": true }
```

> ⚠️ **Don't translate this exact config to v2 REST.** It works here because runpodctl creates
> through GraphQL, which accepts `REQUEST_COUNT` alongside `idleTimeout` on a queue endpoint.
> v2 REST **rejects** that pair — `idleTimeout` is "not applicable to queue-based endpoints
> scaling on `requestCount`". On v2, either scale a queue endpoint on `queueDelay` and keep
> `idleTimeout`, or scale on `requestCount` and drop it.

### 3. Fire a burst and WATCH `/health`
```bash
EP=<endpoint-id>
for i in $(seq 1 6); do
  curl -s "https://api.runpod.ai/v2/$EP/run" -H "Authorization: Bearer $RUNPOD_API_KEY" \
    -H "Content-Type: application/json" -d '{"input":{"sleep":8}}' >/dev/null
done
# then poll repeatedly:
curl -s "https://api.runpod.ai/v2/$EP/health" -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Verify it works (the actual scale-up, observed)

### Request Count (value 1), from **cold** — 6 jobs, 8 s each
The worker count climbs as the backlog persists (`init` → `running`, one then two):
```
t+2s   inQueue=6 inProgress=0 | ready=0 running=0                 # cold: all queued, 0 workers
t+8s   inQueue=5 inProgress=1 | ready=0 running=0                 # first job dispatched
t+12s  inQueue=5 inProgress=1 | initializing=1 running=1          # worker #1 up + worker #2 spinning
t+18s  inQueue=4 inProgress=1 | ready=1 running=1  idle=1         # 2 workers
t+32s  inQueue=3 inProgress=1 | running=2                         # scaled to 2 concurrently
t+52s  inQueue=0 completed=6   | ready=1 running=1                # 6/6 done, draining back down
```
✅ **0 → 1 → 2 running**: Request Count provisioned workers as fast as it could get them.

### Request Count (value 1), reaching **max** — 9 jobs, 3 workers already warm
With 3 workers warm (`ready=3`) the scaler put **all three to work**:
```
t+2s   inQueue=7 inProgress=2 | ready=3 running=0 idle=3
t+16s  inQueue=6 inProgress=3 | running=3                         # running = max (3)
t+34s  inQueue=1 inProgress=3 | running=3                         # held at the ceiling, draining 3-at-a-time
```
✅ **running = 3 = `workersMax`** — the cap is what stops it, exactly as intended.

### Queue Delay (4 s) — same 6-job burst
Reconfigured live, no redeploy:
```bash
runpodctl serverless update $EP --scale-by delay --scale-threshold 4
# → scalerType QUEUE_DELAY  scalerValue 4
```
With ~2 workers warm, Queue Delay **stayed at 2 running** and let the queue drain instead
of racing to add workers — the whole burst cleared 2-at-a-time:
```
t+2s   inQueue=6 inProgress=0 | ready=2 running=0 idle=2
t+8s   inQueue=4 inProgress=2 | running≈2                         # tolerates the queue, no aggressive add
t+24s  inQueue=1 inProgress=1 | running=2
t+34s  inQueue=0 completed=24 | draining                          # cleared with 2 workers
```
✅ **Contrast, proven:** same burst, same endpoint — Request Count reaches for workers per
pending job; Queue Delay tolerates a few seconds of wait and holds steady. Request Count =
lower latency, more workers spun; Queue Delay = higher utilization, fewer workers.

A warm `/runsync` confirms jobs complete cleanly throughout:
```json
{ "delayTime": 1001, "executionTime": 2146, "status": "COMPLETED",
  "output": { "elapsed": 2, "slept": 2, "worker": "935cb63f5219" } }
```

## Gotchas
- **runpodctl v2.3 flags changed.** Use `--scale-by requests|delay` + `--scale-threshold N`
  on both `serverless create` and `serverless update`. The old
  `--scaler-type REQUEST_COUNT` / `--scaler-value` flags were removed; passing the enum
  values won't work. (Stored fields are still `scalerType`/`scalerValue` in **v1** REST and
  GraphQL; v2 REST nests them per scaler — see the mapping table above.)
- **Reconfigure without redeploying.** `runpodctl serverless update <id> --scale-by …
  --scale-threshold … --workers-max … --idle-timeout …` changes scaling on a live endpoint;
  no new template/endpoint needed.
- **Max workers is a ceiling, not a guarantee.** When the DC lacks free capacity, extra
  workers show up as **`throttled`** on `/health` (not `running`) and your effective peak
  can sit *below* `workersMax` — e.g. a max-3 endpoint that runs 2 with a 3rd throttled.
  If you consistently can't reach max, widen the DC list (drop `--data-center-ids` or add
  regions, per [10](10-multi-region-ha-serverless.md)) or add GPU/compute fallbacks.
- **`/health` counts are a live gauge, poll them.** `initializing` = booting, `running` =
  processing, `idle`/`ready` = warm & billed (during idle timeout), `throttled` =
  wanted-but-no-capacity. Watch these to *see* your knobs working before trusting them.
- **Tiny jobs can drain before the scaler ramps.** If jobs finish faster than workers boot,
  the backlog clears and you never reach max — that's correct behavior, not a bug. Use a
  deeper burst / longer jobs (as here) if you want to *observe* the climb.
- **Idle timeout is a cost knob.** Higher = fewer cold starts on bursty traffic but you pay
  for the warm gap; lower (or 0 active) = cheapest but every lull risks a cold start.
- **`--compute-type CPU`** avoids GPU scarcity for CPU-only work (default is GPU).

## Cost & cleanup
```bash
runpodctl serverless delete <endpoint-id>        # the endpoint
runpodctl template   delete <template-id>            # the template
runpodctl serverless list && runpodctl network-volume list && runpodctl pod list  # confirm clean
```
✅ On the live run the endpoint + template were deleted and the lists came back with no
`gp13-*` resources. Scale-to-zero (`--workers-min 0`) means ~$0 idle, but delete anyway.
The pushed image **`<your-registry>/gp13-scale:v1`** (a ~150 MB `python:3.11-slim` + `runpod`
sleep handler) was **left public** so this doc references a real, pullable tag; it costs
nothing. No volume or pod is created by this path.

## Relation to other paths & skill gaps
- **18 (concurrent handler)** is the *other half* of scaling: raise per-worker throughput
  (async concurrency modifier) **before** you add workers here. Concurrency changes *when
  you even need to scale out*; this path tunes *how* you scale out. Tune concurrency first,
  autoscaling second.
- **10 (multi-region HA)** is the fix when you **can't reach max** because one DC is
  capacity-constrained (throttled workers) — spread across DCs for a bigger pool.
- **05 (custom model → endpoint)** is the template→endpoint deploy this path reuses.
- **Skill gap folded back:** the v2.3 autoscaler flags (`--scale-by`/`--scale-threshold`)
  and their `scalerType`/`scalerValue` mapping, plus the `throttled`-workers ceiling caveat,
  are worth reinforcing in
  [`../../runpod-usage/reference/endpoint-workflows.md`](../../runpod-usage/reference/endpoint-workflows.md)
  (the existing autoscale eval already asserts the new flags — this path proves the runtime
  behavior behind them).
