---
concepts: [serverless-endpoint, model-store, serverless-handler, endpoint-autoscaling, worker, runpod-secret, public-endpoint, exposed-port]
---
# Migrate from Hugging Face Inference Endpoints to Runpod

Scope: Hugging Face compute only. Inference Endpoints (vLLM, TGI, SGLang, TEI, llama.cpp, Inference Toolkit with `handler.py`, custom containers), Inference Providers calls through `router.huggingface.co`, GPU Spaces, ZeroGPU Spaces, and Jobs. Models, datasets, and tokens stay on the Hugging Face Hub: Runpod pulls weights from the Hub by repo ID (cached models, Hub workers, `hf download` onto a network volume). Never propose moving repositories off the Hub.

Sources: Hugging Face docs ([Inference Endpoints](https://huggingface.co/docs/inference-endpoints/index), [autoscaling](https://huggingface.co/docs/inference-endpoints/guides/autoscaling), [configuration](https://huggingface.co/docs/inference-endpoints/guides/configuration), [Inference Toolkit and custom handlers](https://huggingface.co/docs/inference-endpoints/engines/toolkit), [custom containers](https://huggingface.co/docs/inference-endpoints/engines/custom_container), [pricing](https://huggingface.co/docs/inference-endpoints/support/pricing), [`huggingface_hub` endpoints guide](https://huggingface.co/docs/huggingface_hub/guides/inference_endpoints), [`hf` CLI](https://huggingface.co/docs/huggingface_hub/guides/cli), [API spec](https://api.endpoints.huggingface.cloud/), [Inference Providers](https://huggingface.co/docs/inference-providers/index), [GPU Spaces](https://huggingface.co/docs/hub/spaces-gpus), [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu), [Jobs](https://huggingface.co/docs/hub/jobs), [TEI](https://huggingface.co/docs/text-embeddings-inference/quick_tour), [TGI](https://huggingface.co/docs/text-generation-inference/basic_tutorials/consuming_tgi)), checked 2026-11-14.

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `\.endpoints\.huggingface\.cloud` | Request to a dedicated Inference Endpoint | Serverless endpoint URL (queue, `/openai/v1`, or load balancing) |
| `endpoints\.huggingface\.cloud/v1` | OpenAI-compatible call to an endpoint (vLLM, TGI, SGLang, llama.cpp, TEI) | `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1` (vLLM worker) or `https://ENDPOINT_ID.api.runpod.ai/v1` (load balancing) |
| `endpoints\.huggingface\.cloud/generate(_stream)?` | TGI native route | `/openai/v1/completions` on a vLLM worker |
| `router\.huggingface\.co` | Inference Providers router | Public Endpoint if the model is listed, else vLLM worker |
| `api\.endpoints\.huggingface\.cloud/v2/endpoint` | Inference Endpoints management API | REST v2 `https://api.runpod.io/v2/serverless` |
| `(create\|get\|list\|update\|delete\|pause\|resume\|scale_to_zero)_inference_endpoint` | `huggingface_hub` endpoint management | `runpodctl serverless ...` or REST v2 |
| `create_inference_endpoint_from_catalog`, `list_inference_catalog` | Model Catalog deploy | `runpodctl hub search` + `serverless create --hub-id` |
| `\.scale_to_zero\(\)`, `\.pause\(\)`, `\.resume\(\)`, `\.wait\(` on an `InferenceEndpoint` | Lifecycle automation | Worker counts (`--workers-min`, `--workers-max`), `/health` polling |
| `hf endpoints `, `hf inference-endpoints ` | CLI in scripts or CI | `runpodctl serverless ...` |
| `InferenceClient\(`, `AsyncInferenceClient\(` | Client: check for `base_url=`, `model="https://...`, or `provider=` | Depends on the target (see Client and API call map) |
| `X-Scale-Up-Timeout` | Client holds requests during scale from zero | Remove on queue-based endpoints |
| `class EndpointHandler` in `handler.py` | Inference Toolkit custom handler | Queue-based endpoint handler, or `@app.queue` |
| `"/repository"` | Code that loads the mounted model | Cached model snapshot path |
| `ghcr\.io/huggingface/text-generation-inference` | TGI image | vLLM worker |
| `ghcr\.io/huggingface/text-embeddings-inference` | TEI image | Load balancing endpoint running the same image |
| `hf jobs (run\|uv run\|scheduled)`, `run_job\(` | Hugging Face Jobs | `@app.task` or a Pod |
| `import spaces`, `@spaces\.GPU` | ZeroGPU Space | Gap: ask the user |
| `\.hf\.space`, `sdk: (gradio\|docker\|streamlit)` in a README front matter | Space app | Pod with an exposed HTTP port, only if it runs on paid GPU hardware |
| `request_space_hardware`, `set_space_sleep_time`, `pause_space` | Space hardware automation | `runpodctl pod create\|stop\|start` |
| `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN`, token prefix `hf_` | Hub credential | Keep. Store as a Runpod secret for gated and private repos. Client auth changes to `RUNPOD_API_KEY`. |

Leave these alone: `from_pretrained(`, `hf_hub_download(`, `snapshot_download(`, `load_dataset(`, `hf download`, `hf upload`. They read from or write to the Hub and work the same from Runpod.

## Product map

| Hugging Face | Runpod | Notes |
| --- | --- | --- |
| Inference Endpoint, engine vLLM, TGI, or SGLang | Serverless vLLM worker (queue-based) | Same repo ID. See [runpod-vllm](../../runpod-vllm/SKILL.md) and golden path [20](../../runpod/golden-paths/20-model-caching-endpoint.md). |
| Inference Endpoint, Inference Toolkit + `handler.py` | Queue-based endpoint with `handler(job)`, or `@app.queue` | See [runpod-serverless-deploy](../../runpod-serverless-deploy/SKILL.md) and [runpod-flash](../../runpod-flash/SKILL.md). |
| Inference Endpoint, engine TEI | Load balancing endpoint running the TEI image | Or a Hub embeddings worker: search the Hub and read its config first. |
| Inference Endpoint, engine llama.cpp (GGUF) | Load balancing endpoint with a llama.cpp server image | `HEALTH_CHECK_PATH=/health`. |
| Inference Endpoint, custom container | Load balancing endpoint | Golden path [14](../../runpod/golden-paths/14-load-balancing-endpoint.md). |
| Model Catalog | Runpod Hub | `runpodctl hub search`, `runpodctl hub get`. |
| Inference Providers | Public Endpoint (listed models), else vLLM worker | Golden path [11](../../runpod/golden-paths/11-public-endpoints.md). |
| GPU Space (Gradio, Streamlit, Docker) | Pod with `PORT/http` exposed | Proxy URL is public and unauthenticated. |
| ZeroGPU Space | UI host + queue-based endpoint | Gap. |
| Jobs | `@app.task`, or a Pod | Scheduled Jobs need an external scheduler. |
| Min and max replicas | `workers.min` (active) and `workers.max` | |
| Scale-to-zero timeout, minutes | Idle timeout, seconds, 1 to 3600 | |
| Default Env, Secret Env | `env`, `{{ RUNPOD_SECRET_name }}` | See [secrets](../../runpod-usage/reference/secrets.md). |
| Model at `/repository` | Cached model at `/runpod-volume/huggingface-cache/hub/models--ORG--NAME/snapshots/HASH/` | See [model-caching](../../runpodctl/reference/model-caching.md). |
| Per-minute billing per replica while initializing and running | Per-second billing while a worker runs | Cached model download time is not billed. |

GPU map (match VRAM, then confirm the model fits):

| Inference Endpoints `instance_type` | Runpod pool | Runpod GPUs |
| --- | --- | --- |
| `nvidia-t4` | `AMPERE_16` | A4000, A4500, RTX 4000, RTX 2000 |
| `nvidia-l4`, `nvidia-a10g` | `AMPERE_24`, `ADA_24` | L4, A5000, 3090, 4090 |
| `nvidia-l40s` | `ADA_48_PRO` | L40, L40S, 6000 Ada |
| `nvidia-a100` | `AMPERE_80` | A100 |
| `nvidia-h100` | `ADA_80_PRO` | H100 |
| `nvidia-h200` | `HOPPER_141` | H200 |
| `nvidia-b200` | `BLACKWELL_180` | B200 |
| `intel-spr`, `intel-xeon` | CPU endpoint (`--compute-type CPU`) | |
| `inf2` | None | Redeploy the standard model on a GPU pool |

`instance_size` `xN` is the GPU count per replica: use `--gpu-count N`. Check live stock with `runpodctl gpu list` or `GET /v2/catalog/gpus?include=AVAILABILITY&product=SERVERLESS`. See [gpu-selection](../../runpod-usage/reference/gpu-selection.md).

## Field map

| `create_inference_endpoint` / API field | `runpodctl` | REST v2 |
| --- | --- | --- |
| `name` | `--name` | `name` |
| `repository` | `--model-reference https://huggingface.co/ORG/NAME:REF`, `--env MODEL_NAME=ORG/NAME` | `env.MODEL_NAME` |
| `revision` | The `:REF` in `--model-reference`, `MODEL_REVISION` | `env.MODEL_REVISION` |
| `accelerator` | `--compute-type GPU\|CPU` | `gpu` or `cpu` |
| `instance_type` | `--gpu-id POOL_OR_TYPE` | `gpu.pools` |
| `instance_size` | `--gpu-count` | `gpu.count` |
| `vendor`, `region` | `--data-center-ids` | `dataCenterIds` |
| `min_replica` (`scaling.minReplica`) | `--workers-min` | `workers.min` |
| `max_replica` (`scaling.maxReplica`) | `--workers-max` | `workers.max` |
| `scale_to_zero_timeout` (minutes) | `--idle-timeout` (seconds) | `workers.idleTimeout` |
| `scaling_metric="pendingRequests"`, `scaling_threshold` | `--scale-by requests --scale-threshold N` | `scaling: {"type": "REQUEST_COUNT", "requestCount": N}` |
| `scaling_metric="hardwareUsage"` | `--scale-by delay --scale-threshold SECONDS` | `scaling: {"type": "QUEUE_DELAY", "queueDelay": SECONDS}` |
| `custom_image.url` | `template create --image` | `image` |
| `custom_image.port` | `template create --ports PORT/http` | `ports`, `env.PORT`, `env.PORT_HEALTH` |
| `custom_image.healthRoute` | Template env | `env.HEALTH_CHECK_PATH` |
| `container_command`, `container_args` | `template create --docker-entrypoint`, `--docker-start-cmd` | `entrypoint`, `cmd` |
| `container_registry_username`, `container_registry_password` | `runpodctl registry create`, then `--registry-auth-id` | `registry` |
| `env` | `--env KEY=VALUE` (Hub deploys), `template create --env '{...}'` | `env` |
| `secrets` | Env value `{{ RUNPOD_SECRET_name }}` | `env` |
| `type` (`public`, `authenticated`, `private`) | None | None. Requests carry a Runpod API key. |
| `task`, `framework` | None | None. The worker image decides. |
| None | `--execution-timeout` (seconds) | `timeout` (milliseconds) |
| None | `--min-cuda-version` | `gpu.minCudaVersion` |

REST v2 create requires `name`, `type` (`QUEUE` or `LOAD_BALANCER`), `scaling`, and `image` or `templateId`. A `LOAD_BALANCER` endpoint takes `REQUEST_COUNT` scaling. `workers.idleTimeout` is rejected on a queue-based endpoint that scales on `REQUEST_COUNT`. REST v2 defaults: `flashboot` `OFF`, `workers.idleTimeout` 10. Set `timeout` explicitly on every create. With `--template-id`, env comes from the template and `--env` on `serverless create` is ignored. For exact flags, check `runpodctl serverless create --help` and `runpodctl template create --help`.

Engine settings to vLLM worker env:

| Inference Endpoints | vLLM worker env |
| --- | --- |
| TGI `MAX_TOTAL_TOKENS` (Max Number of Tokens) | `MAX_MODEL_LEN` |
| TGI Quantization | `QUANTIZATION` |
| vLLM Max Number of Sequences | `MAX_NUM_SEQS` |
| vLLM Max Number of Batched Tokens | `MAX_NUM_BATCHED_TOKENS` |
| vLLM KV Cache DType | `KV_CACHE_DTYPE` |
| vLLM `tensorParallelSize` | `TENSOR_PARALLEL_SIZE` (auto-set to the worker's GPU count) |
| Container args (`vllm serve` flags) | Upper snake case env per flag, or `VLLM_EXTRA_ARGS` |
| Endpoint name sent as `model` | `OPENAI_SERVED_MODEL_NAME_OVERRIDE` |

See [serving-flags](../../runpod-vllm/reference/serving-flags.md).

## Code translation

Inference Toolkit handler to a Runpod handler. Before:

```python
from typing import Any, Dict, List
from transformers import pipeline

class EndpointHandler:
    def __init__(self, path=""):
        self.pipeline = pipeline("text-classification", model=path, device=0)

    def __call__(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        inputs = data.pop("inputs", data)
        parameters = data.pop("parameters", None) or {}
        return self.pipeline(inputs, **parameters)
```

After:

```python
import os
import runpod
from transformers import pipeline

MODEL_ID = os.environ["MODEL_ID"]  # same Hugging Face repo ID, for example "org/name"
HF_CACHE_ROOT = "/runpod-volume/huggingface-cache/hub"

def resolve_snapshot_path(model_id: str) -> str:
    org, name = model_id.split("/", 1)
    root = os.path.join(HF_CACHE_ROOT, f"models--{org}--{name}")
    with open(os.path.join(root, "refs", "main")) as f:
        return os.path.join(root, "snapshots", f.read().strip())

classifier = pipeline("text-classification", model=resolve_snapshot_path(MODEL_ID), device=0)

def handler(job):
    data = job["input"]
    inputs = data.get("inputs")
    if inputs is None:
        return {"error": "Missing 'inputs'."}
    return classifier(inputs, **(data.get("parameters") or {}))

runpod.serverless.start({"handler": handler})
```

- `__init__(path)` becomes module-level code. `path` becomes the cached snapshot directory.
- `__call__(data)` becomes `handler(job)`. `data` is `job["input"]`. Keep the `inputs` and `parameters` keys so clients only add the `input` wrapper.
- Lowest-change option: ship the old file as `hf_handler.py`, build `EndpointHandler(path=resolve_snapshot_path(MODEL_ID))` at module level, and return `endpoint_handler(job["input"])`.
- A generator handler streams through `/stream`. Add `"return_aggregate_stream": True` to expose the aggregate on `/run` and `/runsync`.
- Dockerfile: CUDA base image, `pip install runpod` plus the repo's `requirements.txt`, `CMD ["python", "-u", "/handler.py"]`. Build with `--platform linux/amd64`. See [building-images](../../runpod-usage/reference/building-images.md).

Same handler with the Runpod SDK, no Dockerfile:

```python
import runpod

app = runpod.App("sentiment")
model = runpod.Model("distilbert/distilbert-base-uncased-finetuned-sst-2-english")

@app.queue(gpu="4090", workers=(0, 3), dependencies=["transformers"], model=model)
def classify(inputs: str, parameters: dict | None = None):
    from transformers import pipeline
    classifier = pipeline("text-classification", model=str(model.path), device=0)
    return classifier(inputs, **(parameters or {}))
```

Gated model: add `env={"HF_TOKEN": runpod.Secret("hf_token")}`. Develop with `rp flash dev main.py`, deploy with `rp flash deploy`. To load once per worker, use an `@app.api` class with `@runpod.init`. See [api](../../runpod-flash/reference/api.md).

Custom container to a load balancing endpoint (no code change needed when the server reads its port from the environment):

| Inference Endpoints | Runpod env |
| --- | --- |
| Container port | `PORT`, and `PORT_HEALTH` set to the same value |
| Health route (for example `/health`) | `HEALTH_CHECK_PATH` (default `/ping`; `200` healthy, `204` initializing) |
| `MODEL_ID = "/repository"` | Cached snapshot path, or a repo ID with `HF_TOKEN` |

TEI: image `ghcr.io/huggingface/text-embeddings-inference:cuda-1.9` (tag from the TEI docs: confirm the current one), env `MODEL_ID`, `HF_TOKEN`, `PORT`, health route `/health`, routes `/embed`, `/rerank`, `/predict`, `/v1/embeddings`.

Job to task: `hf jobs run --flavor F IMAGE CMD` becomes an `@app.task(gpu=..., dependencies=[...], mounts={...}, env={...})` function, called with `.remote()` or `.spawn()`.

## Data

- Default: nothing to copy. Attach the Hub repo as a cached model: `--model-reference https://huggingface.co/ORG/NAME:REF` (GPU endpoints) or the console **Model** field. One cached model per endpoint. A repo with several quantization variants downloads all of them.
- Gated or private repo: `HF_TOKEN` env set to `{{ RUNPOD_SECRET_hf_token }}`. Create the secret with `rp secret add hf_token`, the console, or `POST /v2/account/secrets`. Secret names cannot start with `runpod`.
- Pinned revision: carry the commit hash into the `:REF` and `MODEL_REVISION`.
- Several models, non-Hub files, or predictable load times: network volume in the serving data center, filled with `hf download ORG/NAME --local-dir /workspace/models/NAME` from a Pod. The volume mounts at `/runpod-volume` on Serverless. Golden path [07](../../runpod/golden-paths/07-network-volume-handoff.md). See [storage](../../runpod-usage/reference/storage.md).
- Weights that exist only on a replica or in a Space: push them to a Hub repo with `hf upload` first.

## Client and API call map

| Hugging Face | Runpod |
| --- | --- |
| `OpenAI(base_url="https://NAME.REGION.VENDOR.endpoints.huggingface.cloud/v1/", api_key=HF_TOKEN)` | `OpenAI(base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", api_key=RUNPOD_API_KEY)` |
| `model="ENDPOINT_NAME"` | `model="ORG/NAME"`, or the `OPENAI_SERVED_MODEL_NAME_OVERRIDE` value |
| `InferenceClient(base_url=".../v1/")` + `chat.completions.create` | `InferenceClient(base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", api_key=RUNPOD_API_KEY)` |
| `InferenceClient(model=ENDPOINT_URL).text_generation(...)`, `endpoint.client.text_generation(...)` | `chat.completions.create` or `completions.create` on `/openai/v1` |
| `POST ENDPOINT_URL/generate` `{"inputs": ..., "parameters": {"max_new_tokens": N}}` | `POST .../openai/v1/completions` `{"model": ..., "prompt": ..., "max_tokens": N}` |
| `POST ENDPOINT_URL/generate_stream` | `.../openai/v1/completions` with `"stream": true` |
| `POST ENDPOINT_URL` `{"inputs": ..., "parameters": ...}` (toolkit, handler) | `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` `{"input": {"inputs": ..., "parameters": ...}}`, result in `output` |
| Long request held open | `POST .../run`, then `GET .../status/JOB_ID`, or a `webhook` field |
| `POST ENDPOINT_URL/v1/embeddings`, `/embed`, `/rerank` (TEI) | Same path on `https://ENDPOINT_ID.api.runpod.ai` |
| Custom container route `ENDPOINT_URL/PATH` | `https://ENDPOINT_ID.api.runpod.ai/PATH` |
| `OpenAI(base_url="https://router.huggingface.co/v1")`, `model="ORG/NAME:fastest"` | Public Endpoint `https://api.runpod.ai/v2/PUBLIC_ENDPOINT_ID/openai/v1`, model name without a provider suffix |
| `Authorization: Bearer hf_...` | `Authorization: Bearer RUNPOD_API_KEY` |
| `X-Scale-Up-Timeout: N` | Remove. Queue-based endpoints hold the request in the queue. |
| Retry on `503` while scaled to zero | Queue-based: remove. Load balancing: retry on `no workers available`, 3 or more tries, 5 to 10 seconds apart. |

Control plane:

| Hugging Face | Runpod |
| --- | --- |
| `create_inference_endpoint`, `hf endpoints deploy`, `POST /v2/endpoint/{namespace}` | `runpodctl serverless create`, `POST /v2/serverless` |
| `create_inference_endpoint_from_catalog`, `hf endpoints catalog deploy` | `runpodctl serverless create --hub-id HUB_ID` |
| `list_inference_endpoints`, `hf endpoints ls`, `GET /v2/endpoint/{namespace}` | `runpodctl serverless list`, `GET /v2/serverless` |
| `get_inference_endpoint`, `hf endpoints describe` | `runpodctl serverless get ENDPOINT_ID --include-template --include-workers`, `GET /v2/serverless/{id}` |
| `endpoint.update(...)`, `hf endpoints update`, `PUT /v2/endpoint/{namespace}/{name}` | `runpodctl serverless update`, `PATCH /v2/serverless/{id}` |
| `endpoint.wait()` | Poll `GET https://api.runpod.ai/v2/ENDPOINT_ID/health`, or submit to `/run` |
| `endpoint.scale_to_zero()` | `--workers-min 0` |
| `endpoint.pause()` | `--workers-min 0 --workers-max 0` |
| `endpoint.resume()` | `--workers-max N` |
| `endpoint.delete()`, `hf endpoints delete NAME --yes` | `runpodctl serverless delete ENDPOINT_ID` |
| `list_inference_endpoints_hardware`, `hf endpoints hardware`, `GET /v2/provider` | `runpodctl gpu list`, `GET /v2/catalog/gpus`, `GET /v2/catalog/datacenters` |
| `GET .../logs`, `.../replica`, `.../open-metrics` | `runpodctl serverless logs ENDPOINT_ID` (check `--help`), `GET /v2/serverless/{id}/workers`, `/workers/{workerId}/logs`, `/metrics/requests\|cold-starts\|workers` |

Status map:

| Inference Endpoint state | Runpod |
| --- | --- |
| `pending`, `initializing` | Worker `INITIALIZING`, then `RUNNING` during cold start. Jobs `IN_QUEUE`. |
| `running` | Worker `RUNNING` or `IDLE` (ready to start) |
| `scaledToZero` | All workers `IDLE`, not billed |
| `paused` | `workers.max` 0 |
| `updating` | New release rolling out, old workers marked Outdated |
| `failed`, `updateFailed` | Worker `UNHEALTHY` |
| None | Worker `THROTTLED` (host GPUs busy) |

Job states: `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`. See [endpoint-workflows](../../runpod-usage/reference/endpoint-workflows.md).

## Gaps: stop and ask the user

| Gap | Options |
| --- | --- |
| Endpoint type `public` (no auth) | (a) Proxy through the user's backend with the key server-side. (b) Keep that endpoint on Hugging Face. |
| Endpoint uses AWS PrivateLink or must run in a specific cloud vendor | (a) Confirm public HTTPS with an API key is acceptable. (b) User contacts Runpod about private networking. (c) Leave it on Hugging Face. |
| Queue-based or load balancing for a custom handler or container | Queue: requests wait, async jobs, retries. Load balancing: own routes, lower latency, 5.5 minute processing limit, 30 MB payloads, no queue. |
| Callers of TGI `/generate` that depend on TGI-specific parameters or response fields | (a) Port to `/completions` and adapt parsing. (b) Run the TGI image on a load balancing endpoint to keep the routes. |
| Clients send the endpoint name as `model` | (a) Set `OPENAI_SERVED_MODEL_NAME_OVERRIDE`. (b) Change clients to the repo ID. |
| TEI endpoint | (a) TEI image on a load balancing endpoint. (b) A Hub embeddings worker: list candidates with `runpodctl hub search embedding --type SERVERLESS`, read required env with `runpodctl hub get`, and confirm the request shape before switching clients. |
| Cold start longer than the sync wait (large model, scale from zero) | (a) One active worker (billed continuously). (b) Longer idle timeout. (c) Clients use `/run` + `/status`. State the cost of (a) before choosing. |
| Daily autoscaling schedule | Scheduler that runs `runpodctl serverless update ENDPOINT_ID --workers-min N`. Confirm who owns the scheduler. |
| `dataParallelSize` above 1 on a multi-GPU instance | Single-GPU workers with a higher `workers.max`, or keep multi-GPU with one model copy. |
| `inf2` (Inferentia2) endpoint | Redeploy the standard model on a GPU pool. Confirm the model variant. |
| Inference Providers model not in the Public Endpoints reference, or a different variant is listed | (a) Own vLLM endpoint. (b) Accept the listed variant after comparing outputs. (c) Keep that call on Inference Providers. |
| ZeroGPU Space | (a) UI anywhere + queue-based endpoint for the `@spaces.GPU` function. (b) Keep it on ZeroGPU. |
| Space on a Pod | Proxy URL is public: confirm how the app authenticates users. The Pod bills while running: confirm who stops it. |
| Scheduled Jobs | External scheduler or CI that calls the task. |
| Network volume or cached model | Cached model: no data-center pin, load time varies by host. Network volume: predictable, pins the endpoint to one data center. |

## Verify

1. `runpodctl serverless get ENDPOINT_ID --include-template --include-workers`: image, env keys, worker limits, and timeout match the plan. `timeout` is not 0.
2. `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` with the API key: `workers.idle` or `workers.running` is above 0.
3. First request through `/run`, then `/status/JOB_ID` until `COMPLETED`. A cold worker can exceed the sync wait.
4. vLLM worker: `GET .../openai/v1/models` lists the expected model name, then a chat completion returns text.
5. Custom handler: the same payload sent to Hugging Face, wrapped in `input`, returns the same `output`.
6. Load balancing: the health route returns `200` through `https://ENDPOINT_ID.api.runpod.ai`, then one real route call succeeds.
7. Worker logs show the model loading from `/runpod-volume/huggingface-cache/hub/` (cache hit) and no `401` or `403` from the Hub.
8. Compare outputs and latency with the Hugging Face endpoint on a fixed request set, cold and warm.
9. If a job stays `IN_QUEUE`, read worker logs before changing code. See golden path [15](../../runpod/golden-paths/15-monitor-and-debug.md) and [gotchas](../../runpod-usage/reference/gotchas.md).

## Shut down Hugging Face

Only after explicit user approval, and only for the workload that passed Verify. Pause first, delete later.

```bash
# Inference Endpoints: paused endpoints are not billed and keep their configuration
hf endpoints pause ENDPOINT_NAME --namespace NAMESPACE
hf endpoints describe ENDPOINT_NAME --namespace NAMESPACE   # status: paused

# After the rollback window. Permanent: removes configuration, logs, and metrics.
hf endpoints delete ENDPOINT_NAME --namespace NAMESPACE --yes

# Spaces: paused time is not billed
hf spaces pause NAMESPACE/SPACE_NAME

# Jobs
hf jobs cancel JOB_ID
hf jobs scheduled delete SCHEDULED_JOB_ID
```

Do not delete model or dataset repositories. Do not revoke the token that Runpod uses to read gated or private repos. An endpoint in `scaledToZero` still restarts on the next request, so a scaled-to-zero endpoint is not shut down: pause or delete it.
