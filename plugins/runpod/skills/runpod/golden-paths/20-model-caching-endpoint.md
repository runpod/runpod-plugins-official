# Golden path 20 — serverless endpoint with a host-cached HF model (`--model-reference`)

**Goal:** deploy a serverless LLM endpoint whose weights are **not baked into the image
and not on a network volume** — instead attach a HuggingFace model with
`runpodctl serverless create --model-reference …` so Runpod caches it host-side and the
worker loads it straight from the standard HF cache. Prove it end to end with a **tiny
model** (`Qwen/Qwen2.5-0.5B-Instruct`) so it provisions in seconds and costs a fraction of
a cent, then swap only the model URL for a real one.
**Status:** ✅ COVERED — live-verified 2026-07-15 (runpodctl v2.7.1, diagnosed via the
Runpod MCP worker logs). `serverless create --hub-id <worker-vllm> --model-reference …:main`
deployed with **no baked image and no network volume**; Runpod pinned `:main` to commit
`7ae557604adf…`. An async `/run` job returned **`COMPLETED`** with real output
(`"Hello. That's all there is to it."`, `usage {input:7, output:10}`), `delayTime` ~105s
(first-job pickup + vLLM boot), `executionTime` ~1.5s. **Cache-hit confirmed in the worker
logs:** vLLM loaded the 0.92 GiB checkpoint in **0.55s** ("Time spent downloading weights …
0.55 seconds") at the pinned revision — i.e. the model was already present via
`--model-reference`, not freshly pulled. Earlier same-day attempts failed only on infra
timing, not the feature: a first-ever ~10 GB image pull (>20 min) and a sync `/openai` call
that hit a Cloudflare **524** (>100s edge timeout on cold load) — both avoided by using
async `/run` + patience. Total spend across all runs ≈ $0.69.
**Lane(s):** `runpodctl serverless` (`--model-reference`, **v2.4.0+**) + a vLLM worker
(Hub `--hub-id` or a serverless template) + the OpenAI-compatible invoke route.

## When to use this

| You want… | Use |
| --- | --- |
| A model **already on HuggingFace** served without image bloat or a DC-pinned volume | **HF model cache (this path)** — `--model-reference`, fastest cold starts |
| **Your own** artifact (not on HF) served, managed + versioned | Model Repository — `runpodctl model add` (see [`reference/model-caching.md`](../../runpodctl/reference/model-caching.md)) |
| A **large** model, or a latency-sensitive endpoint that can't absorb a first-request stall | Network volume — golden path [07](07-network-volume-handoff.md) |
| A **fully reproducible** image / system libs baked in | Bake into image — golden path [05](05-model-to-endpoint-pipeline.md) |
| Output from a model **Runpod already hosts**, zero infra | Public Endpoint — golden path [11](11-public-endpoints.md) |

Full comparison of all four delivery methods: [`reference/model-caching.md`](../../runpodctl/reference/model-caching.md).

## Prerequisites
- `RUNPOD_API_KEY` resolvable. Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://rest.runpod.io/v1/endpoints -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`.
- **runpodctl ≥ v2.4.0** — `--model-reference` does not exist on older builds. Check
  `runpodctl version`; if behind, install from
  [GitHub releases](https://github.com/runpod/runpodctl/releases) (the Homebrew tap can lag).
- Account with credits (a GPU worker bills per second while running).
- A tiny public model needs no HF token. For gated/private models set an `HF_TOKEN`
  endpoint env var.

## Walkthrough

### 1. Confirm the CLI supports the flag
```bash
runpodctl version                       # must be >= 2.4.0
runpodctl serverless create --help | grep -A1 model-reference
```

### 2. Deploy a vLLM endpoint with the cached model
`--model-reference` takes the full HF URL with a `:ref`. Deploy from the Hub vLLM worker
so we don't build an image; attach the tiny model and a small GPU:
```bash
runpodctl serverless create \
  --name gp20-model-cache \
  --hub-id runpod-workers/worker-vllm \
  --gpu-id "NVIDIA GeForce RTX 4090" \
  --model-reference https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct:main
# capture the endpoint id it prints -> <endpoint-id>
```
(Equivalent with a serverless template: `--template-id <id>` instead of `--hub-id`. The
flag is repeatable to attach multiple models. GPU only — no `--compute-type CPU`.)

### 3. Wait until a worker is actually ready
"Created" ≠ "ready". Poll health until a worker is up:
```bash
runpodctl serverless get <endpoint-id>
curl -s "https://api.runpod.ai/v2/<endpoint-id>/health" \
  -H "Authorization: Bearer $RUNPOD_API_KEY"     # workers.ready >= 1
```

### 4. Call it — use the ASYNC route for the first (cold) call
The **synchronous** `/openai/...` and `/runsync` routes are behind a ~100 s edge timeout;
on a cold worker the first-request model load exceeds it and you get a Cloudflare **524**
(observed 2026-07-14). Submit with async `/run` and poll `/status` instead:
```bash
JOB=$(curl -s -X POST "https://api.runpod.ai/v2/<endpoint-id>/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"prompt":"Say hello in one word.","sampling_params":{"max_tokens":10,"temperature":0}}}' | jq -r .id)
curl -s "https://api.runpod.ai/v2/<endpoint-id>/status/$JOB" -H "Authorization: Bearer $RUNPOD_API_KEY"
# poll until "COMPLETED"
```
Once a worker is **warm**, the sync OpenAI route is fine for chat:
```bash
curl -s -X POST "https://api.runpod.ai/v2/<endpoint-id>/openai/v1/chat/completions" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-0.5B-Instruct",
       "messages":[{"role":"user","content":"Say hello in one word."}],
       "max_tokens":10,"temperature":0}'
```

## Verify it works
Results from the 2026-07-15 live run (worker logs read via the Runpod MCP `stream-worker-logs`):
1. ✅ `runpodctl version` 2.7.1 and `--model-reference` present in `create --help`.
2. ✅ `serverless create … --model-reference …` returned an endpoint id **without** a baked
   image or a network volume, and resolved `:main` to a pinned commit (`…7ae557604adf…`).
3. ✅ Async `/run` job → **`COMPLETED`** with real output (`"Hello. That's all there is to
   it."`), `delayTime` ~105s, `executionTime` ~1.5s — the worker served the cached model.
4. ✅ **Cache-hit confirmed:** the vLLM worker logged `Starting to load model
   Qwen/Qwen2.5-0.5B-Instruct … revision=7ae557604adf…` then `Time spent downloading
   weights … 0.55 seconds` for a 0.92 GiB checkpoint — a fast local cache hit, not a fresh
   HF download. (The literal on-host dir `/runpod-volume/huggingface-cache/hub/` is Runpod's
   documented location and is consistent with this; the logs proved the cache-hit behavior
   but did not print the absolute path.)
5. ✅ Cold pickup ~105s, inference ~1.5s; total spend across all test runs ≈ $0.69; endpoint
   torn down.

## Gotchas to watch
- **v2.3.0 and older don't have `--model-reference`** — the create call will reject the
  flag. Upgrade first (this was the state on the authoring machine).
- **GPU only.** `--model-reference` is rejected with `--compute-type CPU`.
- **The `:ref` matters** — `…Instruct:main` pins the branch/tag/revision; omitting it can
  fail to resolve.
- **Readiness, not fire-and-forget** — a fresh endpoint reports created before any worker
  is ready; poll `/health` before calling (see [15 — monitor & debug](15-monitor-and-debug.md)).
- **A cache miss costs latency, not money.** You are not billed for download time
  either way; on a miss, Runpod holds the worker start until the model lands, so the
  **job sits in the queue** and the endpoint looks idle or stuck when it is really
  downloading. If the project is latency-sensitive, pre-load a **network volume**
  instead (golden path [07](07-network-volume-handoff.md)). If it isn't, the cache is
  the cheaper default — and the two are worth timing against each other on your model.
  See [`reference/model-caching.md` → Cache or network
  volume](../../runpodctl/reference/model-caching.md#cache-or-network-volume--it-is-a-latency-call-not-a-cost-call).
- **One cached model per endpoint** (platform limit, docs → Current limitations) even
  though `--model-reference` is a repeatable flag. A repo with several quantizations
  currently downloads **all** of them.
- **Cache capacity is per machine.** The host tier is a share of each machine's own
  disk, so the same model can fit one host and not another — two workers on one endpoint
  can cold-start at very different speeds, and there is no cache-size number to look up.
- **A tier that can't serve you fails quietly.** If the shared per-data-center copy is
  unusable, there's no error — you just fall back to per-host downloads and it feels
  slower. Don't chase it as a bug.
- **No published list of model-cache regions.** Don't tell a user which regions support
  it. Check which data centers offer network volumes (`list-data-centers` →
  `networkVolumeTypes`) as the list to check, then deploy and measure.
- **Measure your own endpoint.** This is beta and doesn't behave identically for every
  account or host — someone else's benchmark says little about yours.
- **First cold start can be very long.** Run 1 (2026-07-14): worker-vLLM sat
  `initializing` >20 min on a fresh RTX 4090 host (first-ever ~10 GB image pull) and never
  readied. Run 2: readied in **162 s** once the image was warm on the pool. Budget
  generously for the first deploy, keep `--workers-min 0` so you don't pay while it churns.
- **Sync routes 524 on cold load.** `/openai/...` and `/runsync` sit behind a ~100 s edge
  timeout; the first-request model load blew past it → Cloudflare **524**. Use async
  `/run` + `/status` for the first call (see step 4).
- **A new endpoint is slow to pick up its first job — be patient, don't call it broken.**
  `/health` can report `workers.ready:1` while the worker is *still booting vLLM* (CUDA
  init + engine + model load ≈ 30s+ after the container starts), so a job sits `IN_QUEUE`
  for a minute or two before `inProgress`. On the verified run the job completed ~105s
  after submit. **Read the worker logs to tell "slow boot" from "actually broken"** — the
  Runpod MCP `stream-worker-logs` (with `list-endpoint-workers` for the worker id) shows the
  vLLM startup live; look for `Starting to load model …` → `init engine … took` →
  `fitness checks passed` → `Jobs in progress`. Only treat it as a broken/mis-dispatching
  image (per the runpodctl skill) if the logs show a crash or a real stall, not just slow startup.

## Cost & cleanup
- A 0.5B model on an RTX 4090 scaled to zero (`--workers-min 0`, the default) bills only
  per request-second — a couple of test calls should be **well under a cent**.
- **Delete the endpoint when done:**
  ```bash
  runpodctl serverless delete <endpoint-id>
  ```

## Skill gaps folded back
- This path exercises `reference/model-caching.md` end to end and is the worked example
  linked from the runpodctl **Serverless → model cache** note and the **Models (Model
  Repository)** section.
- A live run should confirm whether the cached model is visible at
  `/runpod-volume/huggingface-cache/hub/` from inside the worker, closing the one
  unconfirmed mechanic noted in `reference/model-caching.md`.
