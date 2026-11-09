---
name: runpod-serverless-deploy
description: 'Bring any source (a HuggingFace repo, a ComfyUI workflow, a Hub release, a custom container
  image, a GGUF repo, a Civitai asset, or a community template) to a proven Runpod Serverless endpoint:
  pick the engine for the modality and model format, size the GPU from the model''s real metadata, provision,
  warm, prove it with one real job, and hand back the URL with what it bills. Deploys an existing source
  through the Runpod MCP tools; code-first Python deploys (the Flash dev loop) are out of scope. Use when
  the user wants a model or worker served on Runpod Serverless, whatever the modality: text generation,
  speech-to-text or text-to-speech, image or video generation, embeddings, document processing, or their
  own handler image. For an LLM served with vLLM (Hub worker-vllm, a vllm/vllm-openai image, or a vLLM Pod),
  defer to runpod-vllm.'
metadata:
  author: runpod
  version: "2.0.0" # x-release-please-version
  concepts: [serverless-endpoint, serverless-handler, worker, job, gpu-pool, gpu-availability, hub-repo, template, network-volume, endpoint-release, flashboot, registry-credential, volume-cache]
license: Apache-2.0
---

# Serverless deploy

Turn *any* deployable source into a queue-backed Serverless endpoint proven with one real job; the user leaves knowing what exists and what it bills. Steps: read the source, decide engine and hardware, provision, warm, smoke-test one real job, hand back the URL and a `curl`, state what is billing. Tear down only when the user framed the deploy as a throwaway test or asks for cleanup.

Two decisions are yours, unprompted: the **engine family** (the right worker image for this modality and model format) and the **provisioning path** (bake weights in, download-on-start, or a network volume; each costs a different cold start). Size hardware from the model's real metadata, never a guess. Among suitable workers prefer the smallest, most-proven image for a smoke-able deploy (a giant image makes the first job a many-minute cold start; the smoke test proves the journey, not maximal quality), and name the trade-off if the request implies a heavier engine. Creating an endpoint bills: state the GPU class's hourly cost before creating; the smoke job costs money too.

For code-first Python (writing endpoint functions in a project and iterating with the Runpod SDK's `rp flash dev` loop), this MCP-only bundle has no path. Say so instead of improvising one. This skill deploys an existing source (Hub repo, container image, ComfyUI workflow, Hub release) to an endpoint through the MCP tools.

## Tool binding

Read the catalog before creating; create only what the user asked to deploy. A tool named here missing from the session: say so and use the nearest read; never invent a result.

| Capability | Tool |
|---|---|
| GPU catalog, price, stock (the sizing math is `runpod-discovery`'s); per-DC stock (`dataCenters[]`); CUDA versions with capacity (`cudaVersions`) | `list-gpu-types` / `get-gpu-type` (`include:["AVAILABILITY"]`, `product:["SERVERLESS"]`); `list-data-centers` (`include:["GPU_AVAILABILITY"]`), `get-data-center`; `get-capacity` for the CUDA matrix |
| Hub / community catalog with the release config (hardware, env schema); deploy a release in one call; pin a release / read history | `list-hub-repos` (`includeConfig:true`); `deploy-hub-repo`; `list-endpoint-releases` |
| Template (image, disk, ports, env, registry, mounts); endpoint (GPU pools or CPU flavors, worker min/max, scaler, data centers, network volumes, `timeout`); network volume for large weights in a GPU-co-located DC | `create-template`; `create-endpoint`; `create-network-volume` |
| Multi-GPU / pin to one card (`gpu.count`, pool plus `excludedTypes`) | `set-endpoint-gpus` (`pools`, `excludeGpuTypeIds`, `gpuCount`; builds the exclusion list, preserves other settings), or `update-endpoint` with `gpu.pools` and `gpu.excludedTypes` together |
| Health / warmup; per-worker detail (a crash-looping container can still report RUNNING or INITIALIZING) | `endpoint-health`; `list-endpoint-workers` |
| Smoke test, blocking to terminal | `run-endpoint`, then `get-job-status` (`wait:300000`); `runsync-endpoint` only for a warm endpoint and a fast job (its result is kept for one minute) |
| Worker logs (model-load / crash evidence) | `stream-worker-logs` (`source=system` for the container lifecycle). Without it, `endpoint-health` + `list-endpoint-workers` narrow the cause but cannot settle a crash loop |
| Private-image registry credential; inspect; teardown | `create-registry`, `get-registry`; `get-endpoint`, `get-template`; `delete-endpoint`, `delete-template`, `delete-network-volume` |

## Phase 0 — identify the source and pick the engine (unprompted decision)

Read and classify the source you were given: the engine follows the modality and model format, not a default. Never serve a non-text-generation task on a vLLM or ComfyUI worker; transcription, TTS, OCR and embeddings are not chat-worker jobs.

| Source / modality | Engine family → worker image |
|---|---|
| Text-generation LLM, `safetensors` weights | vLLM or SGLang → `runpod/worker-v1-vllm` (or an SGLang worker); for a vLLM deploy follow [runpod-vllm](../runpod-vllm/SKILL.md) |
| Text-generation LLM, `GGUF` quantized weights | llama.cpp / Ollama → a GGUF-capable worker, **not** vLLM |
| Image/diffusion `workflow.json` | ComfyUI → `runpod/worker-comfyui` ([reference/comfyui-serverless.md](reference/comfyui-serverless.md)) |
| Speech-to-text (transcription) | a Whisper-family model → a speech-to-text worker, not an LLM worker |
| Text-to-speech / voice cloning | a TTS model → a TTS worker |
| Speaker diarization | a diarization pipeline → a diarization worker from the Hub or public catalog |
| OCR / document extraction | a classic OCR engine → an OCR worker, not a VLM chat worker |
| Text embeddings | an embeddings server (e.g. text-embeddings-inference) → an embeddings worker |
| A custom handler you were given | your own image → a custom container image |

- **Format detection.** Inspect the repo's files first: `*.safetensors` / `*.bin` → vLLM/SGLang; `*.gguf` → llama.cpp/Ollama. GGUF on worker-vllm is a common wrong-engine mistake: vLLM will not load it. State the detected format and the engine it implies in the final message.
- **OCR sizing.** For an OCR smoke deploy, default to a classic lightweight OCR worker (16–24 GB). A VLM-based OCR (7B+ params) is a big-model deploy: size it like one (48 GB class) or don't pick it for a smoke test.
- **Community-template source.** When the modality has no first-party Runpod worker, browse the Hub / public catalog for a **community (non-Runpod)** template. Name the repo and its owner from the listing, never from memory. Once one fits, **deploy it and run one real job**: don't stop at "I found X", and don't block on a credential the config makes optional (phase 2's runtime-optional-token rule); request the capability through the job input the config documents. Only if nothing fits, say "none found" and stop.
- **Custom image.** The user's image *is* the engine: deploy exactly the image named, never a substitute. Missing required env → phase 2's model-default rule, not a question back; the observed worker states are the report. After the deploy read the worker states (`list-endpoint-workers` or `endpoint-health`): for a custom image the workers' health IS the deliverable, and one completed job hides a crash-looping sibling, so report a crash-looping custom image as failing. A private registry needs a registry credential (create/reference it; see `runpod-lifecycle-crud`); never echo the registry password. For a **load-balancer** (custom-HTTP) endpoint, read [reference/scenarios.md](reference/scenarios.md#load-balancer-endpoint) (guide id `runpod-serverless-deploy/scenarios`) before the create: the worker must pass the HTTP health check or the endpoint sits at zero ready workers, and the type cannot be changed later.

## Phase 1 — size the hardware (read the catalog, cite `runpod-discovery`)

`runpod-discovery` owns the params×precision + KV/overhead VRAM math; apply its result to a real GPU pick.

- Read the model's real metadata (parameter count, precision; for diffusion the checkpoint/LoRA/VAE sizes), not the repo name alone when the config is readable. **Big-model sizing is shown arithmetic, never a bare total:** the parameter count and where you read it, the bytes per parameter at the chosen precision, the weights total, the KV-cache/overhead allowance, and the GPU decision they add up to.
- Pick the smallest GPU class whose VRAM fits, then confirm live stock: `include:["AVAILABILITY"]` goes with `product:["SERVERLESS"]` (stock differs by product), and the same read gives per-data-center stock and, in `cudaVersions`, which CUDA versions have capacity. Pin the CUDA floor on the create: `gpu.minCudaVersion` at the image's CUDA line (12.8 for a CUDA 12 image; 13.0 only for an image built on CUDA 13), or `gpu.allowedCudaVersions` for an exact set. They are mutually exclusive (400 if both are sent), and the floor must have stock in `cudaVersions`. Never create into a GPU class with no stock: a scale-to-zero endpoint that can never acquire a worker looks deployed but never runs.
- **Pinning to one card** (the user wants an exact GPU): select the pool that contains the card and list the pool's other GPU types in `gpu.excludedTypes` (`gpu.pools` takes pool ids, not GPU type ids; at least one type must remain), on the create or with `set-endpoint-gpus` afterwards. The read-back quotes pools and exclusions, and every other setting is confirmed unchanged from the read.
- **Multi-GPU when one card can't hold the model** (required VRAM > the largest single card with stock): GPUs-per-worker > 1 plus tensor parallelism in the worker env (e.g. vLLM's tensor-parallel setting = GPU count). Say you are going multi-GPU and why, that it costs proportionally more per hour, and quote the largest in-stock single card (VRAM, live stock, $/hr) against the multi-GPU pick before committing.
- **Pin the pool on Hub deploys.** `deploy-hub-repo` inherits the release's GPU pool list when `gpuIds` is omitted, which can silently acquire a top-tier card for a task a 24 GB card serves, at several times the hourly rate. Pass `gpuIds` from YOUR sizing on every Hub deploy unless the release config pins exactly the pool you chose.
- **CPU serverless.** `create-endpoint` takes one hardware choice: the `gpu` object (pools and count) or the `cpu` array of CPU flavors sized from `list-cpu-types`. For a CPU workload send `cpu` and no `gpu` (never force a GPU pool onto it), and quote the CPU flavor's hourly price.
- **Set the values you mean.** A REST create defaults to FlashBoot `OFF`, `workers.max` 3 and `workers.idleTimeout` 10 s: set `flashboot` and the worker bounds explicitly. **Always send `timeout`** (per-request execution limit, in ms) sized to the slowest real job: a v2 create without it comes back `"timeout": 0` (live-verified 2026-10-29; [why it matters](../runpod-usage/reference/gotchas.md#endpoint-timeout-comes-back-0)). On a Hub deploy, read `timeout` back and set it with `update-endpoint` if it is 0. The sum of `workers.max` across the account is capped by a balance-tiered quota (5 to start), checked at create, so a second endpoint at the default of 3 can be refused.
- **State the cost.** Quote the chosen GPU's hourly rate (×GPU count) from the catalog read before creating. Creating the endpoint and running the smoke test both bill.

## Phase 2 — provision

- **Hub release.** Deploy its listed release directly (one call). Read the release config first (hardware + env schema) so you pass only env keys it accepts and know its GPU/disk defaults. To reproduce a known-good build, pin the exact release, not "latest".
- **Everything else.** Create a template naming the engine image, disk size, exposed ports and env (model id, engine settings, tokens), then the endpoint referencing it. Start scale-to-zero (min workers 0) unless the user asked for warm capacity; never set a nonzero minimum silently: it is an always-on worker that bills around the clock. An image on `registry.runpod.net` is a Hub build: deploy it through `deploy-hub-repo` (the release carries the registry auth); a plain template with that image loops on a registry-auth failure.
- **Provisioning path and cold start.** Bake = fastest cold start, biggest image. Download-on-start = small image, slow first request per new worker. **Network volume** = weights staged once in a GPU-co-located data center and mounted by every worker (writable: coordinate concurrent writes), so new workers skip the download; a prebuilt worker loads from the mount, and your own handler can wrap its load in `VolumeCache` (Runpod Python SDK `runpod>=1.12.0`) to copy weights to local disk at each cold start (`runpodctl/reference/model-caching.md`). Choose a volume when weights are large (roughly > 30 GB) or shared; size it to the real asset total with headroom, create it once, in a data center where the Phase 1 stock read shows the GPU in stock, place the endpoint in that data center (`runpod-lifecycle-crud`), and say which path you took and its cold-start consequence.
- **Weights too large to bake:** stage them on a network volume in a data center that has the target GPU, keep minimum workers 0, and prove the wiring with read-backs (for a storage-setup ask those read-backs are the proof; a job on a large model waits for the user's ask); no staging pod the user did not ask for. State both facts plainly: the first worker downloads the weights to the volume once and later cold starts mount that cache, and a volume outside the GPUs' data center cannot mount. Full rule, and the `VolumeCache` variant for the user's own handler: [reference/scenarios.md](reference/scenarios.md#weights-too-large-to-bake-into-the-image).
- **Multi-region / HA (no auto-sync).** Attach one network volume per data center. They do **not** auto-sync: replicate the data yourself (e.g. `aws s3` sync between the volumes' S3 endpoints), or regions serve stale or missing weights.
- **Required env, gated weights, runtime-optional tokens.** Read the release/worker config (`includeConfig: true`) and SET every required env key with no default before deploying (e.g. an embeddings worker's `MODEL_NAMES`): without its model env a worker loads nothing and 400s every job. When the user named no model for a text-generation worker (a vLLM image with no `MODEL_NAME`), use the worker's documented default model if its config has one, else the smallest instruct model that fits the card (a 1–2B instruct model on a 16 GB class); state the choice and deploy, don't ask which model. A gated HuggingFace repo whose *weights* 403 without a token: pass the token in env; if the user gave none, say the download will 403 and ask; never deploy a build that cannot fetch its weights. A token needed only for an **optional runtime capability** (config default empty) branches on one check you make FIRST: did the user provide a token (pasted, set in the environment, or named as available)?
  - **Token provided → using it is the job.** Set it as the worker's documented env var at create, say you configured it (by env-var name, never the value), and expect the gated capability to work. Never deploy without wiring a credential the user handed you.
  - **No token → deploy anyway.** The deploy is NOT conditional on it: deploy, run the job, report what the endpoint returned, then name the token as the unlock.
- Never print or echo a token (HF, Civitai, registry); reference it as an env var.

## Phase 3 — warm and smoke-test one real job

A create call that returned an id is not a working endpoint: prove it with one real job first. Block with server-side holds, not a poll loop handed to the user; report once terminal, or with the evidenced report when waiting stops being informative. Silently stopping mid-wait is not an answer.

- **Submit, then wait server-side.** Fire one small job (the smallest real input for the modality) with `run-endpoint`, then hold with `get-job-status` `wait: 300000` (the maximum hold). A cold first job outlives `runsync`'s hold, whose result is kept only a minute, so `runsync-endpoint` is for a warm endpoint and a fast job. The job proves the worker boots with the real asset set and returns the right output shape.
- **A cold start of 1–5+ minutes on the first job is normal** (image pull + model load), not a failure. If the job outlives a hold, hold again on the same job id; do **not** re-submit (that starts a new job). Between holds check `list-endpoint-workers`: `unhealthy` workers, a job queued beside ready workers, or zero capacity → stop waiting, read the logs. **At most three holds per smoke job** (`get-job-status` `wait: 300000`, same id); after the third, no fourth hold and no tight poll: the evidenced report (endpoint created correctly, job submitted, worker never became ready, what the worker states show) is the complete answer; an endless grind is not.
- **Diagnose a stuck job from the reads you always have:** `endpoint-health`, `list-endpoint-workers`, and the `workerHealth` block `get-job-status` attaches on `IN_QUEUE`.
  - `initializing` on the first job = the cold start may still be running → keep waiting, but read the worker logs (`source=system`) before the next hold: a container crash-looping on an image pull or a CUDA mismatch can still report `INITIALIZING` or `RUNNING` while the job sits in `IN_QUEUE`.
  - `unhealthy` workers, or repeated container starts with no handler output in the logs = a crash loop (a real failure, not slow warmup) → switch the worker image or GPU pool; don't wait it out.
  - `total: 0` for more than a couple of minutes, or `throttled` above 0 = no capacity in the selected pools and data centers → widen them. Prefer a broad, in-stock GPU pool over a scarce high-VRAM tier (e.g. the 48 GB cards) so the endpoint can acquire a worker.
  - A job that never left `IN_QUEUE` was never parsed: no worker read its payload, so NEVER speculate the input was malformed from queue-stuck evidence; report the queue/cold-start fact with the worker states quoted. Never present a cause as "conclusive" that your own reads contradict or don't show: ready workers beside a queued job with nothing in progress point to a broken image; say so from the logs, not from the status alone.
- **Work with the tools you were granted.** In an MCP-only session don't reach for a web-fetch tool, shell or browser you don't have to read a worker's input schema or README; it can't be called and the deploy stalls. Take the input shape from `list-hub-repos` `includeConfig: true` and the endpoint's returned error, fix the payload, re-run. Without `stream-worker-logs`, diagnose from `endpoint-health` / `list-endpoint-workers`; never let an unfinished job hinge on a tool you may not have.
- **On a failure, quote; don't guess.** Read the log and quote it; never retry blindly or assert a cause you did not read. A terminal `FAILED` job: report its decisive detail (missing file, gated 403, OOM, wrong-format load error) as written, not what it probably says; fixes are under Error handling below. A terminal job's `output`/`error` IS worker-level evidence: quote it verbatim when explaining a failure (a gated-model rejection, a load error); never claim you can't quote evidence while holding a terminal result (no log-stream tool doesn't excuse it). Empty or missing output on COMPLETED jobs from a gated-capability worker is quotable evidence: pair it with the config fact (the documented token env was not set) and state the gate.

## Phase 4 — hand back

- **Read back what was asked.** When the user asked for specific behavior settings (warm/minimum workers, idle timeout, FlashBoot, a GPU pin), read the endpoint back after the create/update and confirm those exact fields landed, plus `timeout`: an unread write is an unverified write, and the write call's own response is not a read. The REST PATCH is sparse (omitted fields are left untouched) except for the GPU selection: `gpu.pools` sent without `gpu.excludedTypes` clears the exclusions, so send both, and after a pin confirm the scaling fields too. The read-back result goes in the final answer.
- **The hand-back** is a complete final summary the user never scrolls back from: endpoint name and id; worker image or Hub repo, why that engine, and the read it came from; GPU pool and hourly price; smoke job id and terminal outcome with proof (output reference, quoted failure, or, if the wait ended without a terminal job, the evidenced report: job id, submitted payload, worker states observed, recommended next step); current worker state; sync and async URLs; kept (and what now bills) or deleted (read-back confirmed); a ready-to-run `curl` using `$RUNPOD_API_KEY` (never the literal key); the sizing arithmetic, format finding, and caching/placement facts.
- **Cleanup.** Default to KEEP what the user asked for: say exactly what is now billing (the endpoint, any min-worker, any network volume) and how to delete it later. Tear down (endpoint, its template, any network volume, each confirmed gone by a read-back) only when the user framed the journey as a throwaway test or asks for cleanup.

## Hard rules

- Deploy only the source the user named. Never create an endpoint they did not ask for, and never touch or delete another endpoint, template, or volume.
- Never invent a model URL, a community template repo, or a Docker image. If the source can't be resolved from what the user gave plus the catalog, ask once or say "none found" and stop.
- Also binding: every rule in phases 0–4 above.
- **Cold-start asks on a new endpoint** (an existing endpoint is runpod-endpoint-ops'): read [reference/scenarios.md](reference/scenarios.md#cold-start-levers-on-a-new-endpoint) first. Create with the levers that add no standing charge, and set a minimum worker only when asked or accepted: it bills around the clock.

## Error handling

- Gated / `403` → say so and ask for the token; don't auto-recreate. OOM → up one GPU class (quote the new hourly cost); still failing after one step-up → re-examine the engine choice (switch image in-turn), not more GPU or waiting.
- Payload `400` → fix the payload or the missing env from the release config and re-run; don't stop to ask. Create `409` (name collision) → fresh short suffix, retry once, then surface it and stop. A `204` delete with no body is success; confirm with a read-back.

The full failure → action table (also a stuck queue past a hold, token-gated empty output, GGUF on vLLM, an empty catalog) is in [reference/error-handling.md](reference/error-handling.md) (guide id `runpod-serverless-deploy/error-handling`). Read it when a create or the smoke job fails, before you retry or report a cause.

## Contract

The cross-journey answer contract (definite facts from reads, commit-don't-hedge, mutations bind to this conversation's creations, a standalone final message, honest failure, granted tools only) is defined in the `runpod-mcp` skill and applies to every reply from this journey. If the `runpod-mcp` skill has not been loaded in this conversation, load it now, before the next tool call: its rules on which resources you may change, when a request is the go, and when to stop for the user are not repeated here.
