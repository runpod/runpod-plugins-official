---
concepts: [public-endpoint, serverless-endpoint, serverless-handler, job, endpoint-autoscaling, flashboot, model-store, hub-repo]
---
# Migrate from Replicate to Runpod

Scope: calls to Replicate models (official, community, private), Replicate deployments, Cog models (`cog.yaml` + `predict.py`), trainings, and the client code around them (sync, polling, streaming, webhooks, file inputs and outputs). Targets on Runpod: Public Endpoints, Hub repos, Serverless queue-based endpoints with a native handler, `runpod.App` with `@app.queue`, and Pods or `@app.task` for training.

Sources: Replicate docs ([HTTP API](https://replicate.com/docs/reference/http), [deployments](https://replicate.com/docs/topics/deployments), [official models](https://replicate.com/docs/topics/models/official-models), [billing](https://replicate.com/docs/topics/billing), [output files](https://replicate.com/docs/topics/predictions/output-files), [input files](https://replicate.com/docs/topics/predictions/input-files), [prediction lifecycle](https://replicate.com/docs/topics/predictions/lifecycle), [data retention](https://replicate.com/docs/topics/predictions/data-retention), [streaming](https://replicate.com/docs/topics/predictions/streaming), [webhooks](https://replicate.com/docs/topics/webhooks/receive-webhook), [hardware](https://replicate.com/pricing)), Cog docs ([cog.yaml](https://cog.run/yaml/), [Python](https://cog.run/python/), [HTTP](https://cog.run/http/), [environment](https://cog.run/environment/)), [replicate-python](https://github.com/replicate/replicate-python), [replicate-javascript](https://github.com/replicate/replicate-javascript), checked 2026-11-14.

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `import replicate`, `from replicate.client import Client` | Python client calls | Public Endpoint or Serverless endpoint client code |
| `from "replicate"`, `require("replicate")`, `new Replicate(` | Node.js client calls | Same, with `runpod-sdk` or `fetch` |
| `replicate\.run\(` | Run and wait for output | `/runsync`, `runpod.Endpoint(...).run_sync` |
| `replicate\.(async_run\|stream)\(` | Async or streamed run | `/run` + `/stream`, or `/openai/v1` with `stream=True` |
| `predictions\.create\(` | Async prediction, often with polling or a webhook | `/run` + `/status`, `webhook` field |
| `deployments\.predictions\.create\(`, `/v1/deployments/` | Replicate deployment | Serverless queue-based endpoint |
| `trainings\.create\(`, `/trainings` | Fine-tune run | Pod or `@app.task`, weights on a network volume |
| `api\.replicate\.com/v1` | Raw HTTP calls | `api.runpod.ai/v2/ENDPOINT_ID` (jobs), `api.runpod.io/v2` (management) |
| `REPLICATE_API_TOKEN`, token prefix `r8_` | Replicate credentials | `RUNPOD_API_KEY` |
| `replicate\.delivery` | Stored or allow-listed output URLs | Own bucket URLs, or Public Endpoint output URLs |
| `webhook-signature`, `validateWebhook`, `/v1/webhooks/default/secret` | Signed webhook receiver | Own verification (see Gaps) |
| `cog.yaml` | Cog model definition | `Dockerfile`, or `@app.queue` arguments |
| `from cog import`, `BasePredictor`, `BaseRunner` | Cog predictor | `handler.py`, or an `@app.queue` function |
| `cog (push\|build\|predict\|login\|serve)`, `r8\.im/` | Cog CLI in scripts or CI | `docker build` + `docker push`, or `rp flash deploy` |
| `Prefer: wait`, `Cancel-After` | Sync mode or deadline headers | `/runsync?wait=`, `policy.executionTimeout` |

## Product map

| Replicate | Runpod | Notes |
| --- | --- | --- |
| Official model (always on, billed per output) | Public Endpoint | Only models in the Public Endpoints reference. List with MCP `list-public-endpoints`. |
| Community model called by `owner/name:version` | Public Endpoint, Hub repo, or own endpoint | Runpod runs your own copy of anything that is not a Public Endpoint. |
| Private model, deployment | Serverless queue-based endpoint | `min_instances` and `max_instances` map to active and max workers. |
| Cog image on `r8.im` | Worker image in your registry, or cog-worker wrapper | cog-worker keeps a FastAPI layer in the request path and can add a delay. |
| Cog model without a Dockerfile | `runpod.App` + `@app.queue`, deployed with `rp flash deploy` | See [runpod-flash](../../runpod-flash/SKILL.md). |
| Training into a destination model | Pod or `@app.task` writing to a network volume, then an endpoint on the same volume | Golden paths [04](../../runpod/golden-paths/04-finetune-pod.md) and [08](../../runpod/golden-paths/08-finetune-to-serverless.md). |
| Hardware SKU | GPU pool | See the GPU map below. |
| Output files on `replicate.delivery` (1 hour) | Own S3-compatible bucket via `rp_upload`, or base64 | Public Endpoint output URLs last 7 days. |
| `cog.Secret` input | Endpoint env var set to `{{ RUNPOD_SECRET_name }}` | See [secrets](../../runpod-usage/reference/secrets.md). |

Public Endpoint IDs for common families (confirm against the live list before use):

| Family | Endpoint ID | Output |
| --- | --- | --- |
| FLUX.1 schnell | `black-forest-labs-flux-1-schnell` | `output.image_url` |
| FLUX.1 dev | `black-forest-labs-flux-1-dev` | `output.image_url` |
| FLUX.1 Kontext dev | `black-forest-labs-flux-1-kontext-dev` | `output.image_url` |
| Wan 2.5 I2V | `wan-2-5` | `output.result` |
| Wan 2.6 T2V | `wan-2-6-t2v` | check model page |
| Wan 2.2 I2V 720p | `wan-2-2-i2v-720` | check model page |
| Kling v2.6 Motion Control | `kling-v2-6-std-motion-control` | check model page |
| Kling Video O1 R2V | `kling-video-o1-r2v` | `output.result` |
| Seedance 2.5 T2V | `tdq07exynr7zux` | `output.result` |
| Qwen3 32B | `qwen3-32b-awq` | `output[0].choices[0].tokens`, or `/openai/v1` |
| Moonshot Kimi | `moonshot-kimi` | `/openai/v1` |
| Chatterbox Turbo | `chatterbox-turbo` | `output.audio_url` |

Speech-to-text (Whisper) is served from Hub repos: `runpodctl hub search whisper --type SERVERLESS`. Input field names differ per model (for example `width` and `height` on the Runpod FLUX endpoints), so read the Runpod model page and remap inputs.

GPU map (match by VRAM, then test):

| Replicate SKU | Runpod pool |
| --- | --- |
| `gpu-t4` (16 GB) | `AMPERE_16`, or `AMPERE_24` / `ADA_24` for headroom |
| `gpu-l40s` (48 GB) | `ADA_48_PRO` |
| `gpu-a100-large` (80 GB) | `AMPERE_80` |
| `gpu-h100` (80 GB) | `ADA_80_PRO` |
| `gpu-h200` | `HOPPER_141` |
| `-2x`, `-4x`, `-8x` SKUs | Same pool with GPUs per worker set to the count |
| `cpu`, `cpu-small` | CPU endpoint (`--compute-type CPU`) |

Give an endpoint two or three pools in priority order when the model fits. Check live stock with `runpodctl datacenter list` or MCP `get-capacity`. See [gpu-selection](../../runpod-usage/reference/gpu-selection.md).

## Field map

| Replicate or Cog | REST v2 (`POST /v2/serverless`) | runpodctl | SDK (`@app.queue`) |
| --- | --- | --- | --- |
| Deployment `name` | `name` | `--name` | function name or `name=` |
| `model` + `version` | `image` or `templateId` | `template create --image`, `--template-id` | built by `rp flash deploy` |
| `hardware` | `gpu.pools` | `--gpu-id` | `gpu=` |
| Multi-GPU SKU | `gpu.count` | `--gpu-count` | `gpu_count=` |
| `min_instances` | `workers.min` | `--workers-min` | `workers=(min, max)` |
| `max_instances` | `workers.max` | `--workers-max` | `workers=(min, max)` |
| Setup timeout | env `RUNPOD_INIT_TIMEOUT` | template `--env` | `env=` |
| 30 minute prediction timeout | `timeout` (ms) | `--execution-timeout` (s) | `execution_timeout_ms=` |
| `cog.yaml` `build.python_requirements` | in image | in image | `dependencies=[...]`, `requirements.txt` |
| `cog.yaml` `build.system_packages` | in image | in image | `system_dependencies=[...]` |
| `cog.yaml` `build.cuda` | `gpu.minCudaVersion` | `--min-cuda-version` | `min_cuda_version=` |
| `concurrency.max`, `@cog.concurrent(max=N)` | concurrent handler | concurrent handler | `max_concurrency=` |
| Weights from Hugging Face | cached model | `--model-reference` | `model=runpod.Model(...)` |

REST v2 requires `type` (`QUEUE`) and `scaling`. REST v2 defaults: `flashboot` `OFF`, `timeout` 300000 ms, `workers.idleTimeout` 10 s. Set `flashboot` to `FLASHBOOT` explicitly. For exact flags, check `runpodctl serverless create --help` and `runpodctl template create --help`.

## Code translation

Contract: `setup()` becomes module-level code, `predict()` (or `run()` on `BaseRunner`) becomes `handler(job)`, `Input(...)` constraints become a validation schema, a returned `Path` becomes an uploaded URL or base64.

Before:

```python
# predict.py  (cog.yaml: predict: "predict.py:Predictor")
from cog import BasePredictor, Input, Path

class Predictor(BasePredictor):
    def setup(self):
        self.model = load_model()

    def predict(
        self,
        prompt: str = Input(description="Prompt"),
        steps: int = Input(default=4, ge=1, le=8),
    ) -> Path:
        out = "/tmp/out.png"
        self.model(prompt, steps).save(out)
        return Path(out)
```

After (native handler):

```python
# handler.py  (Dockerfile: CMD ["python", "-u", "/handler.py"])
import base64
import os

import runpod
from runpod.serverless.utils import rp_upload
from runpod.serverless.utils.rp_validator import validate

model = load_model()  # once per worker

SCHEMA = {
    "prompt": {"type": str, "required": True},
    "steps": {"type": int, "required": False, "default": 4, "constraints": lambda s: 1 <= s <= 8},
}

def handler(job):
    v = validate(job["input"], SCHEMA)
    if "errors" in v:
        return {"error": v["errors"]}
    args = v["validated_input"]
    out = f"/tmp/{job['id']}.png"
    model(args["prompt"], args["steps"]).save(out)
    if os.environ.get("BUCKET_ENDPOINT_URL"):
        return {"image_url": rp_upload.upload_image(job["id"], out)}
    with open(out, "rb") as f:
        return {"image_base64": base64.b64encode(f.read()).decode()}

runpod.serverless.start({"handler": handler})
```

After (Runpod SDK, no Dockerfile):

```python
# main.py  (rp flash dev main.py, then rp flash deploy)
import runpod

app = runpod.App("my-model")
_model = None

@app.queue(gpu=runpod.GpuGroup.ADA_24, workers=(0, 3), dependencies=["diffusers"])
def generate(prompt: str, steps: int = 4) -> dict:
    import base64, io
    global _model
    if _model is None:
        _model = load_model()  # once per worker
    buf = io.BytesIO()
    _model(prompt, steps).save(buf, format="PNG")
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}
```

Rules:

- `rp_upload.upload_image(job_id, path)` reads `BUCKET_ENDPOINT_URL` (must include the bucket name), `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY` from the worker environment.
- Payload limits: 10 MB on `/run`, 20 MB on `/runsync`. Use base64 for small files only.
- A `Path` input arrives as a string (URL). Download it in the handler.
- `Iterator[str]` + `yield` becomes a generator handler. Add `"return_aggregate_stream": True` to `runpod.serverless.start` to expose the collected output on `/status` and `/runsync`. See golden path [12](../../runpod/golden-paths/12-serverless-streaming.md).
- With `@app.queue`, the worker calls the function with `input` keys as keyword arguments. Keys must match parameter names, and `input` must be non-empty.
- Images are `linux/amd64`: `docker build --platform linux/amd64`. Use a version tag or digest, not `:latest`.
- Local test: `python handler.py --test_input '{"input": {"prompt": "hi"}}'`.
- cog-worker shortcut: `docker build --platform linux/amd64 --build-arg COG_REPO=OWNER --build-arg COG_MODEL=MODEL_NAME --build-arg COG_VERSION=VERSION_ID .` in a clone of `runpod-workers/cog-worker`. Send one test job to learn its input and file-output behavior before moving traffic.

## Data

| Replicate | Runpod | How |
| --- | --- | --- |
| Weights baked into the Cog image | Baked into the worker image | `COPY` or download in a `RUN` step |
| Weights pulled from Hugging Face in `setup()` | Cached model | `--model-reference`, console **Model** field, or `model=runpod.Model(...)`. Path: `/runpod-volume/huggingface-cache/hub/`. |
| Fine-tune output (new version on the destination model) | Files on a network volume | Download from Replicate (trained-model **Download weights**, or the training object's `output`), then upload |
| Large or shared weights | Network volume, mounted at `/runpod-volume` on Serverless and `/workspace` on Pods | `runpodctl network-volume create`, then the S3-compatible API (`aws s3 cp --region DC --endpoint-url https://s3api-DC.runpod.io/ ... s3://NETWORK_VOLUME_ID/...`) |
| Output files | Own bucket | `rp_upload`, or return base64 |

A network volume is pinned to one data center, and an endpoint that mounts it runs there. See [storage](../../runpod-usage/reference/storage.md).

## Client and API call map

| Replicate | Runpod |
| --- | --- |
| `Authorization: Bearer $REPLICATE_API_TOKEN` | `Authorization: Bearer $RUNPOD_API_KEY` |
| `POST /v1/predictions`, `/v1/models/{owner}/{name}/predictions`, `/v1/deployments/{owner}/{name}/predictions` | `POST https://api.runpod.ai/v2/ENDPOINT_ID/run` |
| `Prefer: wait` (1 to 60 s) | `POST .../runsync` (default wait 90 s, `?wait=1000..300000` ms) |
| `GET /v1/predictions/{id}` | `GET .../status/JOB_ID` |
| `POST /v1/predictions/{id}/cancel` | `POST .../cancel/JOB_ID` |
| `urls.stream` (SSE) | `GET .../stream/JOB_ID` (poll), or `.../openai/v1` with `stream=True` for LLMs |
| `Cancel-After: 5m` | `"policy": {"executionTimeout": 300000, "ttl": ...}` (ms) |
| `webhook` + `webhook_events_filter` | `"webhook": "URL"` next to `input`, fires on completion, 2 retries 10 s apart |
| `replicate.run(model, input={...})` | `runpod.Endpoint("ENDPOINT_ID").run_sync({...}, timeout=...)` |
| `replicate.predictions.create(...)` + `.wait()` | `job = endpoint.run({...})`, `job.status()`, `job.output(timeout=...)` |
| `replicate.stream(...)` | `for chunk in endpoint.run({...}).stream()` |
| `FileOutput.read()` / `.url` | Read the URL or base64 field your endpoint returns |
| `ModelError` | Job `status` `FAILED` with `error` |
| `POST/GET/PATCH/DELETE /v1/deployments` | `POST/GET/PATCH/DELETE https://api.runpod.io/v2/serverless`, `runpodctl serverless create/list/get/update/delete` |
| `GET /v1/hardware` | `GET /v2/catalog/gpus`, `runpodctl gpu list` |

Status map:

| Replicate | Runpod |
| --- | --- |
| `starting` | `IN_QUEUE` |
| `processing` | `IN_PROGRESS` |
| `succeeded` | `COMPLETED` |
| `failed` | `FAILED` |
| `canceled` (user) | `CANCELLED` |
| `canceled` (deadline), `aborted` | `TIMED_OUT` |

Result retention on Runpod: 30 minutes after an async job completes, 1 minute after a sync job. Replicate keeps API prediction data for 1 hour. Webhooks: golden path [16](../../runpod/golden-paths/16-serverless-webhooks.md). Public Endpoint calls: golden path [11](../../runpod/golden-paths/11-public-endpoints.md).

## Gaps: stop and ask the user

| Difference | Options to offer |
| --- | --- |
| The model is not a Public Endpoint and has closed weights | (a) keep that call on Replicate, (b) switch to an open-weights model on Runpod, (c) pick a different hosted model from the Public Endpoints list |
| The model returns files | (a) user supplies an S3-compatible bucket and credentials for `rp_upload`, (b) base64 in the response for files under the payload limit |
| Callers pass local files to `replicate.run` | (a) upload to the user's bucket and send a URL, (b) base64 for small files |
| Webhook receiver verifies Replicate signatures | (a) unguessable token in the webhook URL path plus a `/status` lookup, (b) switch to polling |
| Receiver uses `start`, `output`, or `logs` webhook events | (a) poll `/stream` or `/status`, (b) emit progress with `runpod.serverless.progress_update` |
| Secrets passed as prediction inputs | Move to endpoint env vars backed by Runpod secrets; confirm secret names with the user |
| Results fetched later than 30 minutes after completion | (a) webhook, (b) write outputs to the user's bucket, (c) fetch sooner |
| Input schema parity (`ge`, `le`, `choices`, `regex`) | Reproduce in `rp_validator` constraints; confirm the list of inputs with the user |
| cog-worker wrapper vs native handler | Wrapper is fastest and keeps the FastAPI layer; native handler is the long-term target |
| Fine-tunes created through Replicate trainers | User chooses a training script and base model; weights move to a network volume |
| Warm capacity (`min_instances` above 0) | Active workers bill continuously; confirm the count before creating the endpoint |
| Network volume data center | Pins the endpoint; confirm a data center that has the chosen GPU pool |

## Verify

1. Deploy with active workers at 0 and max workers at a small number.
2. Send a real request: `curl -s -X POST "https://api.runpod.ai/v2/ENDPOINT_ID/runsync?wait=120000" -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" -d '{"input": {...}}'`.
3. Expect `status` `COMPLETED`. Record `delayTime` and `executionTime` (ms), cold and warm.
4. Run the same input with a fixed seed on Replicate and compare the output and `metrics.predict_time`.
5. Send an invalid input and confirm the error shape. Send one job past the execution timeout and confirm `TIMED_OUT`.
6. Fetch a returned file URL from outside Runpod and confirm it downloads.
7. If the job stays `IN_QUEUE`, read worker logs (MCP `stream-worker-logs`, or the endpoint **Logs** tab) before changing code. See [endpoint-workflows](../../runpod-usage/reference/endpoint-workflows.md).

## Shut down Replicate

Run these only after the user explicitly approves, and only after traffic has moved.

```bash
# Scale a deployment down
curl -s -X PATCH https://api.replicate.com/v1/deployments/OWNER/DEPLOYMENT_NAME \
  -H "Authorization: Bearer $REPLICATE_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"min_instances": 0, "max_instances": 0}'

# Delete it. Replicate requires the deployment to be offline and unused for at least 15 minutes.
curl -s -X DELETE https://api.replicate.com/v1/deployments/OWNER/DEPLOYMENT_NAME \
  -H "Authorization: Bearer $REPLICATE_API_TOKEN"
```

- Replicate's docs do not state whether `max_instances: 0` is accepted. If the PATCH is rejected, ask the user to set instance counts in the deployment's **Settings** tab.
- The Replicate Python and JavaScript clients do not delete deployments. Use the HTTP API.
- Before deleting models, confirm the user has downloaded any fine-tuned weights.
- Ask the user to disable the API tokens at `replicate.com/account/api-tokens`. Do not handle token values.
- Remove `REPLICATE_API_TOKEN` from the project's environment config only after the user confirms no code path still calls Replicate.
