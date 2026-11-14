---
concepts: [serverless-endpoint, public-endpoint, hub-repo, model-store, worker, endpoint-autoscaling, serverless-billing, instant-cluster]
---
# Migrate from Together AI to Runpod

Scope: Together AI serverless models (chat, completions, images, video, audio), dedicated
model inference (DMI, v2 and remaining v1 endpoints), dedicated container inference (Jig
CLI, Sprocket SDK, queue API), fine-tuning, the batch API, GPU clusters, and code sandbox.
Together is a hosted model API; Runpod is a GPU cloud. Three landing spots: a Runpod
Public Endpoint when Runpod hosts the model family, a Serverless endpoint running the Hub
vLLM worker for any other open LLM, and a custom Serverless endpoint or Pod for everything
else. Together's serverless catalog is much larger than the Public Endpoints catalog, so
the default answer for an open model is the vLLM endpoint.

Sources: Together AI docs, checked 2026-11-14:
[index](https://docs.together.ai/llms.txt),
[OpenAI compatibility](https://docs.together.ai/docs/inference/openai-compatibility),
[serverless models](https://docs.together.ai/docs/serverless/models),
[dedicated endpoints concepts](https://docs.together.ai/docs/dedicated-endpoints/concepts),
[manage](https://docs.together.ai/docs/dedicated-endpoints/manage),
[scaling](https://docs.together.ai/docs/dedicated-endpoints/scaling),
[pricing](https://docs.together.ai/docs/dedicated-endpoints/pricing),
[migrate from v1](https://docs.together.ai/docs/dedicated-endpoints/migrate-from-v1),
[containers quickstart](https://docs.together.ai/docs/containers-quickstart),
[queue API](https://docs.together.ai/docs/deployments-queue),
[deploy a fine-tuned model](https://docs.together.ai/docs/fine-tuning/deployment),
[batch](https://docs.together.ai/docs/inference/batch/overview),
[GPU clusters](https://docs.together.ai/docs/gpu-clusters-overview),
[CLI](https://docs.together.ai/reference/cli/getting-started).
Together publishes no Runpod migration guide, and no Together Terraform provider is on
the Terraform Registry under `together-ai/together` or `togethercomputer/together`.

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `from together import` or `import together` | Together Python SDK | OpenAI SDK with a Runpod base URL |
| `together-ai` in `package.json`, `from "together-ai"` | Together TypeScript SDK | OpenAI SDK, or `@runpod/ai-sdk-provider` |
| `TOGETHER_API_KEY` | Together key in env or CI secrets | `RUNPOD_API_KEY` |
| `TOGETHER_PROJECT_ID` | Project scope for CLI and SDK | No equivalent; the key selects the account |
| `api.together.ai/v1` | Serverless inference or management API | Public Endpoint or vLLM endpoint |
| `api-inference.together.ai` | Dedicated model inference (and SDK 3 chat default) | vLLM endpoint with active workers |
| `us-api.together.ai` | US-only inference | Endpoint with `dataCenterIds` set |
| `api.together.xyz` | Possible legacy hostname; not in current Together docs | Same as `api.together.ai` |
| regex `model\s*[=:]\s*["'][\w.-]+/[\w.-]+["']` near a Together client | Model string or endpoint string (`PROJECT_SLUG/ENDPOINT_NAME`) | Model map, then endpoint ID + served model name |
| `client.images.generate`, `/v1/images/generations` | Image generation | Public Endpoint (native API) or Hub ComfyUI worker |
| `client.videos.create`, `client.videos.retrieve` | Video generation | Public Endpoint `/run` + `/status` |
| `client.audio.transcriptions`, `/v1/audio/transcriptions` | Speech-to-text | Hub Whisper worker |
| `client.audio.speech`, `/v1/audio/speech` | Text-to-speech | Public Endpoint (different models) or custom handler |
| `client.rerank.create`, `/v1/rerank`, `/v1/embeddings` | Dedicated-only rerank or embeddings | Gap: see Gaps |
| `client.batches`, `tg batches`, `purpose="batch-api"` | Batch API | Serverless batch jobs (`/batch`) |
| `client.fine_tuning`, `tg fine-tuning`, `tg ft ` | Fine-tuning job | Pod training run |
| `tg endpoints`, `client.endpoints`, `ep_`/`dep_`/`cr_`/`ml_` IDs | Dedicated model inference | vLLM endpoint |
| `tg beta jig`, `[tool.jig.` in `pyproject.toml` | Dedicated container inference | Custom queue-based or load balancing endpoint |
| `import sprocket`, `sprocket.Sprocket`, `emit_info` | Sprocket worker | `runpod.serverless.start` handler |
| `/v1/queue/submit`, `/v1/queue/status`, `client.beta.jig.queue` | Container queue API | `/run`, `/status/JOB_ID` |
| `tg clusters`, `client.beta.clusters`, `--cluster-type SLURM` or `KUBERNETES` | GPU cluster | Instant Cluster |
| `together_sandbox`, `together-sandbox` | Code sandbox | Pod (gap) |

## Product map

| Together AI | Runpod | Notes |
| --- | --- | --- |
| Serverless chat model hosted by Runpod too | Public Endpoint, `https://api.runpod.ai/v2/SLUG/openai/v1` | See model map |
| Any other open LLM | Hub `runpod-workers/worker-vllm` on a queue endpoint | `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1` |
| DMI endpoint + deployment + replicas | Same vLLM endpoint, `workers.min` = old `minReplicas` | One Runpod endpoint per model |
| Fine-tuned or uploaded model | vLLM endpoint with `MODEL_NAME` = HF repo or `/runpod-volume/PATH` | |
| LoRA adapter | vLLM endpoint with `ENABLE_LORA`, `LORA_MODULES` (adapter on Hugging Face) | |
| Sprocket queue worker | Queue endpoint with a handler | |
| Sprocket HTTP mode, custom vLLM image | Load balancing endpoint (`/ping` health) | See [runpod-vllm](../../runpod-vllm/SKILL.md) |
| Batch API | `POST /v2/ENDPOINT_ID/batch` on a queue endpoint, or `/run` + `webhook` | |
| Fine-tuning job | GPU Pod + network volume, or `@app.task` | Golden paths [04](../../runpod/golden-paths/04-finetune-pod.md), [08](../../runpod/golden-paths/08-finetune-to-serverless.md) |
| GPU cluster (Slurm) | Instant Cluster, type `SLURM` | Never promise stock |
| GPU cluster (Kubernetes) | Instant Cluster `TRAINING` or `RAY`, or Serverless for serving | Gap |
| Cluster shared volume, Jig volume | Network volume | Pinned to one data center |
| Code sandbox | Pod | Gap |

Model map (Together string to Public Endpoint slug; same family, verify version and params):

| Together | Runpod slug | `model` |
| --- | --- | --- |
| `moonshotai/Kimi-K3` | `moonshot-kimi` | `kimi-k3` |
| `moonshotai/Kimi-K3.1-Pro` | `moonshot-kimi` | `kimi-k3.1-pro` |
| `openai/gpt-oss-120b` | `gpt-oss-120b` | read `client.models.list()` |
| `Qwen/Qwen3...` chat | `qwen3-32b-awq` (different Qwen3 model) | `Qwen/Qwen3-32B-AWQ` |
| `ByteDance-Seed/Seedream-4.0` | `seedream-v4-t2i`, `seedream-v4-edit` | native API |
| `Qwen/Qwen-Image` | `qwen-image-t2i` | native API |
| `Wan-AI/Wan2.6-image` | `wan-2-6-t2i` | native API |
| `google/flash-image-3.1` | `google-nano-banana-2-edit` (edit) | native API |
| `google/gemini-3-pro-image` | `nano-banana-pro-edit` (edit) | native API |
| `ByteDance/Seedance-2.5` | Seedance 2.5 T2V and I2V (read the URL from the model page) | native API |
| `vidu/vidu-q3` | `vidu-q3-t2v`, `vidu-q3-i2v` | native API |

The live list comes from the MCP `list-public-endpoints` tool or the docs model reference.
Golden path: [11](../../runpod/golden-paths/11-public-endpoints.md).

GPU map:

| Together | Runpod GPU type ID | Serverless pool |
| --- | --- | --- |
| `1xnvidia-h100-80gb`, `h100-80gb`, `H100_SXM` | `NVIDIA H100 80GB HBM3` | `ADA_80_PRO` |
| `1xnvidia-h200-140gb`, `H200_SXM` | `NVIDIA H200` | `HOPPER_141` |
| `1xnvidia-b200-180gb`, `b200-192gb`, `B200_SXM` | `NVIDIA B200` | use the type ID |
| `1xnvidia-b300-280gb`, `B300_SXM` | `NVIDIA B300 SXM6 AC` | use the type ID |
| `L40_PCIE` | `NVIDIA L40` | `ADA_48_PRO` |
| `gpu_type = "none"` | CPU endpoint | `--compute-type CPU` |

Size by the model, not by Together's hardware: see
[gpu-selection](../../runpod-usage/reference/gpu-selection.md). Read live stock before
choosing (`runpodctl gpu list`, MCP `get-capacity`).

## Field map

| Together | Runpod |
| --- | --- |
| `MODEL` argument, `ml_...` | env `MODEL_NAME` + `--model-reference https://huggingface.co/ORG/NAME:main` |
| `--endpoint NAME` | `--name` (`name`); requests use the endpoint ID |
| `--config cr_...`, Jig `gpu_type` | `--gpu-id POOL_OR_TYPE` (`gpu.pools`) |
| Config GPU count, Jig `gpu_count` | `--gpu-count` (`gpu.count`); vLLM sets tensor parallelism from visible GPUs |
| `--min-replicas`, `minReplicas`, `min_replicas` | `--workers-min` (`workers.min`) |
| `--max-replicas`, `maxReplicas`, `max_replicas` | `--workers-max` (`workers.max`) |
| `--scaling-metric`, `--scaling-target` | `--scale-by delay\|requests` + `--scale-threshold` on create; `--scaler-type QUEUE_DELAY\|REQUEST_COUNT` + `--scaler-value` on update (`scaling`) |
| `--scale-down-window` | `--idle-timeout` seconds (`workers.idleTimeout`); REST v2 rejects it on a queue endpoint that scales on request count |
| `--inactive-timeout` minutes | Drop it; `workers.min: 0` scales to zero and restarts on the next request |
| `--max-concurrent-requests-per-replica` | env `MAX_CONCURRENCY` on the vLLM worker |
| `--placement.regions` | `--data-center-ids` (`dataCenterIds`) |
| `vllm serve --flag-name V` | env `FLAG_NAME=V`, or `VLLM_EXTRA_ARGS` |
| Function calling on a model | env `ENABLE_AUTO_TOOL_CHOICE=true`, `TOOL_CALL_PARSER=...` |
| Jig `cmd` | image `CMD`, or template `--docker-start-cmd` |
| Jig `storage` | template `--container-disk-in-gb` |
| Jig `environment_variables` | template `--env` (`env`) |
| Jig secrets | Runpod secrets ([secrets](../../runpod-usage/reference/secrets.md)) |
| Jig `volume_mounts` | `--network-volume-id` (`mounts.network`), path `/runpod-volume` |
| `TOGETHER_DEPLOYMENT_NAME` in a worker | `RUNPOD_ENDPOINT_ID` |

For exact flags, check `runpodctl serverless create --help` and
`runpodctl template create --help`. REST v2 create requires `name`, `type`, and `scaling`.

## Code translation

Deploy the vLLM worker (golden path [20](../../runpod/golden-paths/20-model-caching-endpoint.md),
procedure in [runpod-vllm queue reference](../../runpod-vllm/reference/queue-endpoint.md)):

```bash
runpodctl hub get runpod-workers/worker-vllm        # read the listing ID
runpodctl serverless create --hub-id HUB_ID --name qwen3-8b --gpu-id AMPERE_24 \
  --workers-min 0 --workers-max 3 \
  --model-reference https://huggingface.co/Qwen/Qwen3-8B:main \
  --env MODEL_NAME=Qwen/Qwen3-8B --env MAX_MODEL_LEN=8192 \
  --env ENABLE_AUTO_TOOL_CHOICE=true --env TOOL_CALL_PARSER=hermes
```

Always pass `--gpu-id`. `--model-reference` requires a GPU endpoint and one cached model
per endpoint. Gated or private model: add `HF_TOKEN`. When the Hub release's vLLM version
is older than the model needs, use a load balancing endpoint with `vllm/vllm-openai`
(golden path [27](../../runpod/golden-paths/27-vllm-pod-to-endpoint.md)).

OpenAI client (Python; TypeScript is the same three fields):

```python
# before
client = OpenAI(api_key=os.environ["TOGETHER_API_KEY"], base_url="https://api.together.ai/v1")
client.chat.completions.create(model="Qwen/Qwen3.5-9B", messages=msgs)
# after
client = OpenAI(api_key=os.environ["RUNPOD_API_KEY"],
                base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", timeout=300)
client.chat.completions.create(model="Qwen/Qwen3-8B", messages=msgs, max_tokens=512)
```

`together` SDK: replace `Together()` and `Together(base_url="https://api-inference.together.ai")`
with the OpenAI client above. Chat and completions method names and response shapes match.
Always set `max_tokens`; the vLLM worker default is 16. To keep old model strings, set
`OPENAI_SERVED_MODEL_NAME_OVERRIDE`.

Sprocket worker to handler:

```python
# before
class W(sprocket.Sprocket):
    def setup(self): self.model = load()
    def predict(self, args: dict) -> dict: return {"out": self.model(args["x"])}
sprocket.run(W(), os.environ.get("TOGETHER_DEPLOYMENT_NAME", "w"))
# after
import runpod
model = load()                                   # module level = setup()
def handler(job): return {"out": model(job["input"]["x"])}
runpod.serverless.start({"handler": handler})
```

`emit_info(d)` becomes `runpod.serverless.progress_update(job, d)`. Sprocket downloads
HTTPS URLs in the payload to local paths; a Runpod handler downloads them itself. Build
`linux/amd64`, push, `runpodctl template create --serverless`, then
`runpodctl serverless create --template-id`. See
[building-images](../../runpod-usage/reference/building-images.md) and
[endpoint-workflows](../../runpod-usage/reference/endpoint-workflows.md).

Queue API:

| Together | Runpod |
| --- | --- |
| `POST /v1/queue/submit` `{"model", "payload", "priority"}` | `POST /v2/ENDPOINT_ID/run` `{"input"}` |
| `GET /v1/queue/status?model=&request_id=` | `GET /v2/ENDPOINT_ID/status/JOB_ID` |
| `request_id`, `outputs`, `info` | `id`, `output`, progress in status |
| `pending`, `running`, `done`, `failed`, `canceled` | `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED` |

Batch: Together JSONL lines `{"custom_id", "body"}` become a JSON array of `{"input": {...}}`
posted to `https://api.runpod.ai/v2/ENDPOINT_ID/batch`, then `POST .../batch/BATCH_ID/finalize`,
`GET .../batch/BATCH_ID`, `GET .../batch/BATCH_ID/requests`. The vLLM worker's native input
is `messages` or `prompt` plus `sampling_params`. Carry the old `custom_id` inside `input`
or map by returned request ID.

Images and video: Together `client.images.generate(...)` returns `data[0].url`; a Runpod
Public Endpoint takes `{"input": {...}}` on `/runsync` and returns a URL under `output`
(`image_url` on most image models, `result` on Qwen Image, `video_url`, `audio_url`), which
expires after 7 days. Input and output field names are per model: read the model page.

## Data

| Together asset | Export | Runpod destination |
| --- | --- | --- |
| Stock model | None | Hugging Face repo via `--model-reference` |
| Fine-tune, merged | `tg fine-tuning download FT_ID --output-dir DIR` (`.tar.zst`; `zstd -d`, `tar -xvf`) | Private HF repo (`hf repos create REPO --private`, then `hf upload REPO DIR`), or network volume |
| Fine-tune, adapter | `tg fine-tuning download FT_ID --checkpoint-type adapter` | HF repo, served with `LORA_MODULES` |
| Uploaded model | `tg models download ml_... DIR` | Same as merged |
| Training files | `tg files retrieve-content FILE_ID --output DIR` | Network volume on the training Pod |
| Batch results | `tg batches download BATCH_ID --output DIR` (kept 7 days) | Local or object storage |
| Cluster shared volume (`/data` on Slurm) | `aws s3 sync` from a node | Network volume S3 API `https://s3api-DC.runpod.io/`, bucket = volume ID |

Network volume mounts at `/workspace` on Pods and `/runpod-volume` on Serverless. For a
volume-hosted model set `MODEL_NAME=/runpod-volume/PATH`. The S3 API is available in
selected data centers and uses its own access key. Runpod Model Repository
(`runpodctl model add`) stores private artifacts; how a worker loads one at runtime is
not publicly documented, so prefer Hugging Face or a network volume here. Details:
[storage](../../runpod-usage/reference/storage.md),
[model-caching](../../runpodctl/reference/model-caching.md).

## Client and API call map

| Together | Runpod |
| --- | --- |
| `POST api.together.ai/v1/chat/completions` | `POST api.runpod.ai/v2/ENDPOINT_ID/openai/v1/chat/completions` |
| `/v1/completions`, `/v1/models` | `/openai/v1/completions`, `/openai/v1/models` |
| `/v1/images/generations`, `/v1/audio/speech` | `POST api.runpod.ai/v2/SLUG/runsync` |
| Video create + retrieve | `/run` + `/status/JOB_ID` |
| `tg endpoints deploy` | `runpodctl serverless create --hub-id` (MCP `deploy-hub-repo`) |
| `tg endpoints ls`, `get` | `runpodctl serverless list`, `get --include-workers` |
| `tg endpoints update dep_... --min-replicas N --max-replicas M` | `runpodctl serverless update ENDPOINT_ID --workers-min N --workers-max M`; `PATCH /v2/serverless/ENDPOINT_ID` `{"workers": {"min": N, "max": M}}` |
| `tg endpoints rm` | `runpodctl serverless delete` |
| `tg endpoints events`, analytics | `GET /v2/serverless/ENDPOINT_ID/metrics/requests`, `/metrics/workers`, `/metrics/cold-starts`; `runpodctl serverless logs` |
| `tg models configs`, instance types | `runpodctl gpu list`, `GET /v2/catalog/gpus` |
| `tg clusters create`, `list`, `delete` | `POST`, `GET`, `DELETE /v2/clusters`; Terraform `runpod_cluster` |
| `tg clusters storage create` | `runpodctl network-volume create` |
| `GET /v1/billing/usage` | `GET /v2/billing`, `/v2/billing/serverless` |

Feature parity on the OpenAI route:

| Feature | vLLM endpoint | Public Endpoints |
| --- | --- | --- |
| Chat, completions, models | Documented | Chat documented for Qwen3 32B AWQ, Kimi, GPT-OSS 120B, Cogito 671B |
| Streaming | Documented | Documented |
| Tools | Per model, needs parser env vars | Documented for GPT-OSS 120B; check the model |
| `response_format` | Not listed in worker docs; test | See model page |
| Vision, logprobs | Per model; test | Check the model |
| Embeddings, rerank, Responses API, Messages API | Not among documented routes | None listed |

## Gaps: stop and ask the user

| Gap | Options |
| --- | --- |
| Billing unit changes from tokens to worker seconds on self-hosted endpoints | (a) Public Endpoint if the model is listed; (b) scale to zero and accept cold starts; (c) active workers for steady traffic. Show an estimate from the user's traffic and get approval. |
| Cold starts on scale-to-zero endpoints; a sync call on a cold worker can return 524 | (a) `workers.min >= 1`; (b) longer idle timeout with queue delay scaling; (c) async `/run` for non-interactive calls |
| Model is proprietary or resold by Together and not on Hugging Face | (a) Public Endpoint if listed; (b) choose a replacement open model; (c) keep that call on Together |
| Quantization or version differs from Together's build | Run the user's eval set on both; user decides whether quality matches |
| Embeddings or rerank (`/v1/embeddings`, `/v1/rerank`) | (a) Embedding server on a load balancing endpoint; (b) Hub embedding worker; (c) keep on Together |
| Traffic split, A/B test, shadow experiment, metric-gated rollout | (a) Two endpoints and client-side routing; (b) drop the feature |
| Kubernetes GPU cluster | (a) Convert jobs to Slurm on an Instant Cluster; (b) self-managed Kubernetes on Pods or cluster nodes; (c) Serverless for serving workloads |
| Reserved or preemptible cluster capacity | Instant Clusters are on-demand; route commitment questions to Runpod sales. Never state that stock is guaranteed. |
| Managed fine-tuning job API | (a) Training script on a Pod; (b) fine-tuning Pod (Axolotl); user supplies hyperparameters |
| Queue job `priority` | Separate endpoint per priority tier (`lowPriority` in a job's `policy` only keeps the job from triggering scaling) |
| Code sandbox | Pod per session, deleted after use |
| Geo-restricted inference (`us-api.together.ai`) | Set `dataCenterIds`; confirm compliance needs with the user |
| Responses API or Anthropic Messages API clients | Rewrite to chat completions |

## Verify

1. `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` shows a ready worker.
2. First call through `/run` + `/status`; then a chat completion on `/openai/v1` with the
   user's real prompt, from outside Runpod.
3. Exercise each inventoried feature: streaming, tools, `response_format`, image input.
4. Compare output and latency with Together for the same prompts; report warm and cold timings.
5. Read back the endpoint (`runpodctl serverless get ENDPOINT_ID --include-workers`):
   GPU pool, `workers.min`/`max`, env.
6. List every Runpod resource created and its idle cost. See
   [gotchas](../../runpod-usage/reference/gotchas.md).

## Shut down Together AI

Only after explicit user approval, per resource. Deletion is permanent.

```bash
tg endpoints update DEPLOYMENT_ID --min-replicas 0 --max-replicas 0   # stop billing, keep config
tg endpoints rm ENDPOINT_ID --force                                   # delete endpoint + deployments
tg beta jig destroy                                                   # from the Jig project directory
tg clusters delete CLUSTER_ID
tg clusters storage delete VOLUME_ID                                  # volumes bill after cluster delete
tg fine-tuning cancel FT_ID
curl -s -X PATCH "https://api.together.ai/v1/endpoints/ENDPOINT_ID" \
  -H "Authorization: Bearer $TOGETHER_API_KEY" -H "Content-Type: application/json" \
  -d '{"state": "STOPPED"}'                                            # v1 endpoints; a stopped one stays stopped
```

Confirm with `tg endpoints ls`, `tg clusters list`, `tg clusters storage list`. Serverless
usage ends when calls stop. The user revokes Together API keys and turns off auto-recharge
in the Together console.
