---
concepts: [serverless-endpoint, public-endpoint, model-store, hub-repo, gpu-pool, endpoint-autoscaling, worker, network-volume]
---
# Migrate from Fireworks AI to Runpod

Fireworks AI is a model platform: the user sends a model ID and Fireworks runs the inference stack. Its products are Serverless inference (shared, per token), on-demand deployments (dedicated GPUs, per GPU-second), custom models and LoRA addons, a Training API, and a paused Batch API. On Runpod each workload lands in one of three places: a Public Endpoint (Runpod hosts the model), a Serverless endpoint running vLLM (the user's own OpenAI-compatible endpoint, the general answer), or a Pod (training). Fireworks runs no user containers, so there are no images to port and no runtime env vars to map.

Sources: Fireworks docs, checked 2026-11-14: [index](https://docs.fireworks.ai/llms.txt), [OpenAI compatibility](https://docs.fireworks.ai/tools-sdks/openai-compatibility), [deployments](https://docs.fireworks.ai/guides/ondemand-deployments), [autoscaling](https://docs.fireworks.ai/deployments/autoscaling), [regions](https://docs.fireworks.ai/deployments/regions), [custom models](https://docs.fireworks.ai/models/uploading-custom-models), [deploying LoRAs and downloading weights](https://docs.fireworks.ai/fine-tuning/deploying-loras), [Batch API](https://docs.fireworks.ai/guides/batch-inference), [`firectl deployment create`](https://docs.fireworks.ai/tools-sdks/firectl/commands/deployment-create), [Python SDK](https://github.com/fw-ai-external/python-sdk).

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `api.fireworks.ai/inference/v1` | OpenAI-compatible inference base URL | Public Endpoint or vLLM endpoint |
| `accounts/fireworks/models/[a-z0-9.-]+` | Fireworks-hosted model (serverless, or base of a deployment) | Public Endpoint if Runpod hosts it, else vLLM endpoint |
| `accounts/fireworks/routers/` | Serverless Fast, Ultra-fast or US-only variant | vLLM endpoint (latency comes from GPU choice and active workers) |
| `accounts/[a-z0-9-]+/deployments/` | On-demand deployment called by name | vLLM endpoint |
| `accounts/(?!fireworks/)[a-z0-9-]+/models/` | Custom model or LoRA adapter in the user's account | vLLM endpoint with weights from Hugging Face or a network volume |
| `#` inside a `model` string (`MODEL#DEPLOYMENT`) | Request routed to one deployment or to a LoRA on a multi-LoRA deployment | vLLM endpoint, `LORA_MODULES` for adapters |
| `FIREWORKS_API_KEY` | Fireworks credential | `RUNPOD_API_KEY` |
| `from fireworks import`, `AsyncFireworks`, `fireworks-ai` in requirements | Fireworks Python SDK | OpenAI SDK for inference, runpodctl or REST v2 for automation |
| `@ai-sdk/fireworks`, `fireworks_ai/` (LiteLLM prefix), `langchain_fireworks` | Third-party client pointed at Fireworks | Same client's OpenAI-compatible provider with the Runpod base URL |
| `firectl ` in scripts or CI | Control-plane automation | runpodctl |
| `api.fireworks.ai/v1/accounts/` | REST control plane (deployments, models, metrics, datasets) | REST v2 (`https://api.runpod.io/v2`) |
| `/inference/v1/embeddings`, `/inference/v1/rerank` | Embedding or reranking calls | Gap: see below |
| `/inference/v1/responses`, `client.responses.create` | Responses API | Gap: see below |
| `ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference` | Anthropic-compatible Messages API | Gap: see below |
| `service_tier`, `context_length_exceeded_behavior`, `perf_metrics_in_response`, `x-session-affinity` | Fireworks request extensions | Remove on Runpod |
| `reasoning_content` | Client reads Fireworks reasoning field | Read `reasoning` as well |
| `~/.fireworks/auth.ini` | firectl credentials on the machine | Inventory can call firectl |

## Product map

| Fireworks | Runpod | Notes |
| --- | --- | --- |
| Serverless inference, model hosted by Runpod | Public Endpoint | Catalog is smaller than Fireworks'. Read the live list with `list-public-endpoints` (MCP) or the docs model reference. |
| Serverless inference, any other open model | Queue endpoint from Hub `runpod-workers/worker-vllm` with a cached model | Procedure: [runpod-vllm](../../runpod-vllm/SKILL.md). |
| On-demand deployment | Same queue endpoint | Closest match: workers min and max, scale to zero. |
| Deployment needing a newer vLLM, or direct HTTP | Load-balancing endpoint on `vllm/vllm-openai:TAG` | [lb-endpoint.md](../../runpod-vllm/reference/lb-endpoint.md). |
| Deployment shape | GPU pool, GPU count, vLLM env vars | The agent sizes the GPU. |
| Custom base model | Hugging Face repo plus `--model-reference`, or a network volume path in `MODEL_NAME` | |
| LoRA addon, live merge | Merge with PEFT and serve as a base model | |
| LoRA addon, multi-LoRA | `ENABLE_LORA=true`, `LORA_MODULES` | Client `model` becomes the adapter name. |
| Training API (SFT, DPO, RL) | Pod plus network volume, user's trainer | [Golden path 04](../../runpod/golden-paths/04-finetune-pod.md), [08](../../runpod/golden-paths/08-finetune-to-serverless.md). |
| Batch API (paused per Fireworks docs) | Queue endpoint `/run` plus webhook, or `/batch` | [Golden path 16](../../runpod/golden-paths/16-serverless-webhooks.md). |
| Image model on a deployment (for example FLUX.1 [dev]) | Public Endpoint if listed, else a Hub worker | Native `{"input": ...}` format, not OpenAI. |
| Speech-to-text | Hub worker | [Golden path 03](../../runpod/golden-paths/03-whisper-endpoint/README.md). |
| Secrets | Runpod secrets, `{{ RUNPOD_SECRET_name }}` | [secrets.md](../../runpod-usage/reference/secrets.md). |
| Reserved capacity | Active workers | Runpod gives no capacity guarantee. |

Public Endpoint text models with an OpenAI route in the Runpod docs: `qwen3-32b-awq` (model `Qwen/Qwen3-32B-AWQ`), `moonshot-kimi` (models `kimi-k2.6`, `kimi-k2.7-code`, `kimi-k3`, `kimi-k3.1-pro`, `kimi-k3.1-pro-highspeed`), `gpt-oss-120b`, `cogito-671b-v2-1-fp8-dynamic`. `granite-4-0-h-small` documents the native route. Confirm each against the live catalog and `GET .../openai/v1/models` before mapping a call site to it. Walkthrough: [golden path 11](../../runpod/golden-paths/11-public-endpoints.md).

## Field map

| `firectl deployment create` | runpodctl `serverless create` | REST v2 `POST /v2/serverless` |
| --- | --- | --- |
| model argument | `--model-reference https://huggingface.co/ORG/MODEL:REF`, `--env MODEL_NAME=ORG/MODEL` | `env.MODEL_NAME` |
| `--deployment-shape`, `--accelerator-type` | `--gpu-id POOL_OR_TYPE` | `gpu.pools` |
| `--accelerator-count` | `--gpu-count` | `gpu.count` (vLLM: `TENSOR_PARALLEL_SIZE` matches it) |
| `--min-replica-count` | `--workers-min` | `workers.min` |
| `--max-replica-count` | `--workers-max` | `workers.max` |
| `--scale-to-zero-window` (default 1h, min 5m), `--scale-down-window` | `--idle-timeout` seconds (1 to 3600) | `workers.idleTimeout` |
| `--scale-up-window`, `--load-targets` | `--scale-by delay\|requests`, `--scale-threshold` | `scaling.type`, `scaling.queueDelay` or `scaling.requestCount`; REST v2 rejects `workers.idleTimeout` on a queue endpoint that scales on request count, so keep a long idle timeout with queue delay |
| `--region` | `--data-center-ids` | `dataCenterIds` |
| `--max-context-length` | `--env MAX_MODEL_LEN=` | `env.MAX_MODEL_LEN` |
| `--precision` | Choose a repo at that quantization | same |
| `--enable-addons` | `--env ENABLE_LORA=true`, `--env LORA_MODULES=...` | `env` |
| `--draft-model`, `--draft-token-count` | `--env SPECULATIVE_MODEL=`, `--env NUM_SPECULATIVE_TOKENS=` | `env` |
| `--display-name` | `--name` | `name` |
| `--wait` | Poll `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` | same |
| (decided by Fireworks) tool calling | `--env ENABLE_AUTO_TOOL_CHOICE=true`, `--env TOOL_CALL_PARSER=PARSER` | `env` |
| (decided by Fireworks) reasoning | `--env REASONING_PARSER=PARSER` | `env` |

`--env` applies only with `--hub-id`. Always pass `--gpu-id`. For exact flags, check `runpodctl serverless create --help`.

GPU map: `NVIDIA_A100_80GB` → pool `AMPERE_80`; `NVIDIA_H100_80GB` → `ADA_80_PRO`; `NVIDIA_H200_141GB` → `HOPPER_141`; `NVIDIA_B200_180GB` and `NVIDIA_B300_288GB` → read the pool from `GET /v2/catalog/gpus`; `AMD_MI325X_256GB` and `AMD_MI350X_288GB` → an NVIDIA GPU with enough VRAM (vLLM images are CUDA builds). Size from the model, not from the Fireworks shape: [gpu-selection.md](../../runpod-usage/reference/gpu-selection.md). Read live stock before choosing.

## Code translation

Deploy, before:

```bash
firectl deployment create accounts/fireworks/models/llama-v3p1-8b-instruct \
  --deployment-shape default --min-replica-count 0 --max-replica-count 3 --scale-to-zero-window 10m
```

Deploy, after ([golden path 20](../../runpod/golden-paths/20-model-caching-endpoint.md)):

```bash
runpodctl hub search vllm
runpodctl serverless create --name llama-31-8b --hub-id HUB_ID --gpu-id AMPERE_24 \
  --workers-min 0 --workers-max 3 --idle-timeout 600 --scale-by delay --scale-threshold 4 \
  --model-reference https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct:main \
  --env MODEL_NAME=meta-llama/Llama-3.1-8B-Instruct --env MAX_MODEL_LEN=8192 \
  --env ENABLE_AUTO_TOOL_CHOICE=true --env TOOL_CALL_PARSER=llama3_json \
  --env HF_TOKEN='{{ RUNPOD_SECRET_hf_token }}'
```

With the Runpod MCP tools, use `deploy-hub-repo` as in [queue-endpoint.md](../../runpod-vllm/reference/queue-endpoint.md).

Client, before:

```python
import os
from openai import OpenAI  # or: from fireworks import Fireworks; client = Fireworks()

client = OpenAI(base_url="https://api.fireworks.ai/inference/v1", api_key=os.environ["FIREWORKS_API_KEY"])
r = client.chat.completions.create(
    model="accounts/fireworks/models/llama-v3p1-8b-instruct",
    messages=[{"role": "user", "content": "Say hello in one word."}],
)
```

Client, after (vLLM queue endpoint):

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=f"https://api.runpod.ai/v2/{os.environ['RUNPOD_ENDPOINT_ID']}/openai/v1",
    api_key=os.environ["RUNPOD_API_KEY"],
)
r = client.chat.completions.create(
    model="meta-llama/Llama-3.1-8B-Instruct",
    messages=[{"role": "user", "content": "Say hello in one word."}],
    max_tokens=64,
)
```

Other base URLs: Public Endpoint `https://api.runpod.ai/v2/SLUG/openai/v1`; load-balancing endpoint `https://ENDPOINT_ID.api.runpod.ai/v1`. TypeScript and curl change the same three values. Set `max_tokens` on every request. Put the base URL and model behind config so rollback is one setting.

Fireworks batch line → Runpod job:

```text
{"custom_id": "r1", "body": {"messages": [...], "max_tokens": 100}}
POST https://api.runpod.ai/v2/ENDPOINT_ID/run
{"input": {"messages": [...], "sampling_params": {"max_tokens": 100}}, "webhook": "https://..."}
```

Keep the `custom_id` to job `id` mapping client-side. Async results are retained 30 minutes.

## Data

| Fireworks asset | Export | Runpod home |
| --- | --- | --- |
| Fireworks-hosted base model | Nothing to move | Matching Hugging Face repo via `--model-reference` |
| Custom base model | `firectl model download MODEL_ID DIR` | Private Hugging Face repo (`hf repos create REPO --private`, then `hf upload REPO DIR`), or a network volume (S3-compatible API, mounts at `/runpod-volume`) |
| LoRA adapter (`firectl model list --kind HF_PEFT_ADDON`) | `firectl model download MODEL_ID DIR` | Hugging Face repo for `LORA_MODULES`, or merged with PEFT `merge_and_unload()` |
| Dataset | `firectl dataset download DATASET_ID --output-dir DIR` | Network volume or the user's object storage |
| Batch inputs and outputs | Download now: Fireworks states they will be deleted | Same |

Fireworks states an adapter pairs with the exact base it was trained on, which can differ from the public Hugging Face weights. A network volume pins the endpoint to one data center. Storage rules: [storage.md](../../runpod-usage/reference/storage.md). Cached model rules: [model-caching.md](../../runpodctl/reference/model-caching.md).

## Client and API call map

| Fireworks | Runpod |
| --- | --- |
| `POST /inference/v1/chat/completions` | `POST https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1/chat/completions` |
| `POST /inference/v1/completions` | `POST .../openai/v1/completions` |
| `GET` models list | `GET .../openai/v1/models` |
| `firectl deployment list\|get\|update\|delete` | `runpodctl serverless list\|get\|update\|delete` |
| `firectl deployment scale ID --replica-count=N` | `runpodctl serverless update ID --workers-min N` with `--workers-max` at or above N; for `--replica-count=0` use `--workers-min 0` (scales to zero when idle) |
| `POST /v1/accounts/ACCOUNT_ID/deployments` | `POST https://api.runpod.io/v2/serverless` |
| `GET /v1/accounts/ACCOUNT_ID/metrics` (Prometheus) | `GET /v2/serverless/ENDPOINT_ID/metrics/requests\|cold-starts\|workers` |
| `firectl billing get-usage` | `runpodctl billing serverless`, `GET /v2/billing/serverless` |
| `firectl quota list` | `runpodctl gpu list` |
| `firectl secret create` | Runpod secret, referenced as `{{ RUNPOD_SECRET_name }}` |
| Scale-from-zero `503 DEPLOYMENT_SCALING_UP` retry loop | Queue holds the request. First cold call: `/run` plus `/status` (sync routes time out at about 100 s) |
| `reasoning_content` in the response | `reasoning` on vLLM v0.32.0 |
| `usage` in the last stream chunk by default | Test on the target endpoint |

Deployment states `CREATING`, `READY`, `UPDATING`, `FAILED` correspond to worker states Initializing, Idle or Running, Outdated (during a release), Unhealthy. Job states on a queue endpoint: `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.

## Gaps: stop and ask the user

| Gap | Options |
| --- | --- |
| Model is absent from Public Endpoints | (a) Own vLLM endpoint, billed per second of worker time. (b) Keep that model on Fireworks. |
| Which Hugging Face repo matches the Fireworks model (checkpoint, quantization) | User confirms the repo. Outputs can differ at another precision. |
| Embeddings or reranking call sites | (a) Embedding server on a load-balancing endpoint or a custom queue worker. (b) Keep on Fireworks. The worker-vllm docs list the chat, completions and models routes. |
| Responses API with stored state or server-run MCP tools | (a) Rewrite to chat completions with client-side state. (b) Keep on Fireworks. |
| Anthropic-compatible Messages API clients | (a) Switch the client to the OpenAI format. (b) Add a translation gateway. (c) Keep on Fireworks. |
| `response_format` JSON schema or grammar mode | Runpod docs leave this unspecified for the vLLM worker. Test the user's schemas on the endpoint before cutover. |
| Priority, Fast, Ultra-fast, Spot tiers | Active workers or a larger GPU for latency. Ask for the latency target. |
| Per-token to per-second billing | Ask for request volume and traffic shape, then propose idle timeout and active workers with an hourly bound. |
| Reserved capacity or capacity guarantee | Active workers plus a sales conversation. Never promise capacity. |
| Managed training jobs (SFT, DPO, RL) | User supplies or approves a training script for a Pod. |
| Data residency (`US`, `EUROPE` placement, US-only serverless) | Ask which data centers are acceptable, then set `--data-center-ids`. |
| Fine-tune base checkpoint is a vendor build | User confirms the base with Fireworks, or downloads it with `firectl model download`. |
| Custom weights that cannot go to Hugging Face | Network volume (pins a data center) or bake into an image. `runpodctl model add` uploads to the Model Repository; confirm the runtime load path with live help before proposing it. |
| PrivateLink or Private Service Connect direct routes | Ask the user to raise it with Runpod sales. |

## Verify

1. `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` shows a ready worker.
2. First request through `/run` and `/status` reaches `COMPLETED`.
3. [`test_endpoint.py`](../../runpod-vllm/scripts/test_endpoint.py) passes against the OpenAI base URL: chat, streaming, and a tool call when the code uses tools.
4. Replay a sample of real prompts on both platforms. Compare output, tool-call arguments, JSON validity, time to first token.
5. Report what is running, its hourly price, and what bills while idle.

## Shut down Fireworks AI

Run these only after explicit user approval that names each resource. Download weights and datasets first.

```bash
firectl deployment list
firectl deployment scale DEPLOYMENT_ID --replica-count=0   # reversible
firectl deployment delete DEPLOYMENT_ID
firectl model delete MODEL_ID
firectl dataset delete DATASET_ID
firectl reservation list     # reservations bill until they end; the user contacts Fireworks
firectl api-key list         # user revokes keys; check `firectl api-key delete --help`
```

Serverless inference stops billing when requests stop. Deployments bill per GPU-second while replicas run.
