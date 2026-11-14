---
concepts: [public-endpoint, serverless-endpoint, serverless-handler, flash, endpoint-autoscaling, network-volume, runpod-secret, gpu-pool]
---
# Migrate from fal to Runpod

Scope: fal Model APIs (hosted models called by ID) move to Runpod Public Endpoints; fal Serverless
apps (`fal.App`) move to Runpod Serverless (the Runpod SDK `runpod.App`, or a custom image with a
handler); realtime and WebSocket endpoints move to load-balancing endpoints; fal Compute instances
move to Pods or Instant Clusters. This playbook covers code, CLI, and API usage; it has no HCL to
translate.

Sources: fal docs, checked 2026-11-14:
[index](https://fal.ai/docs/llms.txt),
[queue API](https://fal.ai/docs/documentation/model-apis/inference/queue),
[webhooks](https://fal.ai/docs/documentation/model-apis/inference/webhooks),
[realtime](https://fal.ai/docs/documentation/development/realtime),
[scaling reference](https://fal.ai/docs/documentation/deployment/scale-your-application),
[machine types](https://fal.ai/docs/documentation/deployment/machine-types),
[persistent storage](https://fal.ai/docs/documentation/development/use-persistent-storage),
[secrets](https://fal.ai/docs/documentation/development/manage-secrets-securely),
[runner env vars](https://fal.ai/docs/documentation/development/environment-variables),
[Compute](https://fal.ai/docs/documentation/compute),
[fal's Runpod-to-fal guide](https://fal.ai/docs/documentation/development/migrate-from-runpod).

## Detect

| Signal (grep) | What it means | Lands on |
|---|---|---|
| `import fal_client` / `from fal_client` | Python client calling hosted models or the user's own app | Public Endpoint or Serverless endpoint call |
| `@fal-ai/client` | JS client (`fal.subscribe`, `fal.queue.submit`, `fal.run`, `fal.stream`, `fal.realtime.connect`) | Same as above |
| `@ai-sdk/fal` | Vercel AI SDK provider | `@runpod/ai-sdk-provider` |
| `@fal-ai/server-proxy` | Server route that hides `FAL_KEY` from browsers | Keep the route, call Runpod from it |
| `queue\.fal\.run/` | Queue REST calls | `https://api.runpod.ai/v2/ENDPOINT_ID/run` + `/status/JOB_ID` |
| `https://fal\.run/` | Sync or `/stream` REST calls | `/runsync`, or `/run` + `/stream/JOB_ID` |
| `Authorization: Key ` | fal auth header | `Authorization: Bearer` |
| `FAL_KEY` / `FAL_API_KEY` | fal credential env var | `RUNPOD_API_KEY` |
| `["']fal-ai/[a-z0-9./-]+["']` | Hosted model ID | Public Endpoint ID, if listed (see Product map) |
| `["']workflows/[^"']+["']` | fal workflow endpoint | Gap: orchestrate in client code |
| `class \w+\(fal\.App` | fal Serverless app | `runpod.App` (`@app.queue` / `@app.api`) or handler image |
| `@fal\.endpoint\(` | HTTP route on a `fal.App` | Queue function, `@runpod.post` route, or handler |
| `@fal\.realtime\(` / `is_websocket=True` | WebSocket endpoint | Load-balancing endpoint with a WebSocket route |
| `@fal\.function` | One-off remote function | `@app.task` or `@app.queue` |
| `fal\.toolkit` (`Image`, `File`, `Video`, `Audio`) | Output auto-uploaded to fal CDN | `rp_upload` to the user's bucket, or base64 |
| `ContainerImage\.from_dockerfile` | Custom container on fal | Custom image + template |
| `\[tool\.fal\.apps\.` in `pyproject.toml` | App config; `exposed_port` means direct HTTP server mode | Serverless endpoint; `exposed_port` → load-balancing endpoint |
| `fal (deploy\|run\|apps\|secrets\|files\|keys\|runners) ` | fal CLI in scripts or CI | `rp flash ...`, `runpodctl ...` |
| `/data/` paths, `HF_HOME` under `/data` | fal persistent storage | Cached model, network volume, or global volume |
| `fal\.media` / `v3\.fal\.media` | Stored fal CDN URLs | Copy files to the user's storage before shutdown |
| `X-Fal-Webhook-Signature` / `fal_webhook` | Webhook receiver or sender | `webhook` body field; new verification |
| `api\.fal\.ai/v1` | Platform API automation | REST v2 `https://api.runpod.io/v2` |
| `1xH100-SXM` / `8xH100-SXM` | fal Compute instance type | Pod or Instant Cluster |

## Product map

| fal | Runpod | Notes |
|---|---|---|
| Model APIs | Public Endpoints | Map a model only when the Runpod model reference lists it |
| Queue API, `subscribe`, `submit` | `/run`, `/runsync`, `/status/JOB_ID` | Result is in the status response `output` |
| `fal.run` sync | `/runsync` (default wait 90 s, `?wait=` up to 300000 ms) | |
| `/stream` SSE | `/stream/JOB_ID` (queue) or the app's own SSE route (load balancing) | |
| `@fal.realtime` | Load-balancing endpoint, `wss://ENDPOINT_ID.api.runpod.ai/PATH` | fal msgpack protocol does not carry over |
| Workflows | Client-side orchestration | Gap |
| `fal.App` | `@app.queue` (queue), `@app.api` (HTTP class with `@runpod.init`), or image + `handler.py` | |
| ComfyUI `fal.App` | ComfyUI worker (Hub, `runpod/worker-comfyui` images) | Input `{"input": {"workflow": {...}}}`, output base64 in `output.images[0].data` |
| `/data` | Cached models, network volume (`/runpod-volume`), global volume | Network volume pins the endpoint to one data center |
| fal CDN | User's S3-compatible bucket via `rp_upload`, or base64 | Public Endpoint output URLs expire after 7 days |
| `fal secrets` | Runpod secrets | Referenced explicitly per endpoint |
| fal Compute | Pods (container, SSH), Instant Clusters (multi-node) | Check stock; never promise availability |
| Teams, organizations | Organizations | |

Hosted model IDs with a listed Runpod counterpart (verify against
`docs.runpod.io/public-endpoints/reference` or the MCP `list-public-endpoints` tool before use):

| fal model ID | Runpod endpoint ID |
|---|---|
| `fal-ai/flux/dev` | `black-forest-labs-flux-1-dev` |
| `fal-ai/flux/schnell` | `black-forest-labs-flux-1-schnell` |
| `fal-ai/flux-kontext/dev` | `black-forest-labs-flux-1-kontext-dev` |
| `fal-ai/qwen-image` | `qwen-image-t2i` (LoRA: `qwen-image-t2i-lora`) |
| `fal-ai/qwen-image-edit` | `qwen-image-edit` |
| `fal-ai/qwen-image-edit-2511` | `qwen-image-edit-2511` |
| `fal-ai/qwen-image-edit-2511/lora` | `qwen-image-edit-2511-lora` |
| `fal-ai/bytedance/seedream/v4/text-to-image` | `seedream-v4-t2i` |
| `fal-ai/bytedance/seedream/v4/edit` | `seedream-v4-edit` |
| `fal-ai/z-image/turbo` | `z-image-turbo` |
| `fal-ai/nano-banana-2/edit` | `google-nano-banana-2-edit` |
| `fal-ai/nano-banana-pro/edit` | `nano-banana-pro-edit` |
| `wan/v2.6/text-to-image` | `wan-2-6-t2i` |
| `wan/v2.6/text-to-video` | `wan-2-6-t2v` |
| `wan/v2.6/image-to-video` | `wan-2-6-i2v` |
| `fal-ai/wan-25-preview/image-to-video` | `wan-2-5` |
| `fal-ai/wan/v2.2-a14b/image-to-video` | `wan-2-2-i2v-720` |
| `fal-ai/wan/v2.2-a14b/image-to-video/lora` | `wan-2-2-t2v-720-lora` |
| `fal-ai/kling-video/v2.6/standard/motion-control` | `kling-v2-6-std-motion-control` |
| `bytedance/seedance-2.5/text-to-video` | `tdq07exynr7zux` |
| `bytedance/seedance-2.5/image-to-video` | `16jsvx5ncmm24x` |
| `fal-ai/vidu/q3/text-to-video` | `vidu-q3-t2v` |
| `fal-ai/vidu/q3/image-to-video` | `vidu-q3-i2v` |
| `fal-ai/infinitalk` | `infinitetalk` |
| `fal-ai/minimax/speech-02-hd` | `minimax-speech-02-hd` |
| `fal-ai/chatterbox/text-to-speech/turbo` | `chatterbox-turbo` |

Same model family does not mean same output: versions, tiers, and defaults differ. Compare outputs.

GPU map (Serverless selects by pool; confirm pool IDs and stock with `GET /v2/catalog/gpus` or
`runpodctl gpu list`):

| fal `machine_type` | VRAM | Runpod pool |
|---|---|---|
| `GPU-A100` | 40 GB | `AMPERE_48` or `AMPERE_80` (Runpod A100 is 80 GB) |
| `GPU-L40` | 48 GB | `ADA_48_PRO` |
| `GPU-H100` | 80 GB | `ADA_80_PRO` |
| `GPU-RTXPRO6000` | 96 GB | `BLACKWELL_96` |
| `GPU-H200` | 141 GB | `HOPPER_141` |
| `GPU-B200` | 192 GB | `BLACKWELL_180` |
| `XS`..`XL` | CPU | CPU instance ID such as `cpu3c-2-4` |

## Field map

| `fal.App` attribute | Runpod SDK (`@app.queue` / `@app.api`) | runpodctl | REST v2 `POST /v2/serverless` |
|---|---|---|---|
| `app_name` | `runpod.App("NAME")`, `name=` | `--name` | `name` |
| `machine_type` | `gpu=` / `cpu=` | `--gpu-id` (pool or type ID) | `gpu.pools` / `cpu` |
| `num_gpus` | `gpu_count=` | `--gpu-count` | `gpu.count` |
| `min_concurrency` (default 0) | `workers=(MIN, MAX)` | `--workers-min` | `workers.min` |
| `max_concurrency` (default 2) | `workers=(MIN, MAX)`, SDK default `(0, 3)` | `--workers-max` | `workers.max` |
| `keep_alive` (default 60 s) | `idle_timeout=` (SDK default 60) | `--idle-timeout` (1 to 3600) | `workers.idleTimeout` (REST default 10) |
| `max_multiplexing` | `max_concurrency=` (queue only) | concurrent handler in the image | concurrent handler in the image |
| `scaling_delay` | `scaler_type="QUEUE_DELAY"`, `scaler_value=` | `--scale-by delay --scale-threshold` | `scaling: {type: QUEUE_DELAY, queueDelay}` |
| `request_timeout` (default 3600 s) | `execution_timeout_ms=` (default 0, no limit) | `--execution-timeout` (seconds) | `timeout` (ms, default 300000) |
| `startup_timeout` | `env={"RUNPOD_INIT_TIMEOUT": "SECONDS"}` (default 420) | template env | `env` |
| `regions` | `datacenter=` | `--data-center-ids` | `dataCenterIds` |
| `requirements` | `dependencies=`, `system_dependencies=` | in the image | in the image |
| `ContainerImage`, `registries` | `image=`, `registry_auth=` (`rp registry add`) | template `--image`, `--registry-auth-id` | `image`, `registry` |
| `secrets = [...]` | `env={"K": runpod.Secret("NAME")}` | template `--env` with `{{ RUNPOD_SECRET_NAME }}` | `env` with `{{ RUNPOD_SECRET_NAME }}` |
| `/data` HF cache | `model=runpod.Model("ORG/NAME")` | `--model-reference` | see `runpodctl/reference/model-caching.md` |
| `/data` other files | `mounts={"/runpod-volume": runpod.NetworkVolume("NAME")}` | `--network-volume-id` | `mounts.network[].volumeId` |
| `exposed_port` | `@app.api` | template `--ports` + `PORT`, `PORT_HEALTH` env | `type: LOAD_BALANCER`, `ports`, `env`, `scaling: {type: REQUEST_COUNT, requestCount}` |
| `app_auth` | Runpod API key on every request | same | same |
| `concurrency_buffer*` | Gap: use `workers` min and scaler threshold | | |

REST v2 requires `type` (`QUEUE` or `LOAD_BALANCER`) and `scaling`; `flashboot` defaults to `OFF`.
`runpodctl serverless create` creates queue-based endpoints from a template; create load-balancing
endpoints through REST v2 or the MCP `create-endpoint` tool. For exact flags, check
`runpodctl serverless create --help` and `runpodctl template create --help`.

Runner env vars: `FAL_KEY` → a Runpod API key passed as a secret; `FAL_APP_ID` / `FAL_APP_NAME` →
`RUNPOD_ENDPOINT_ID`; `HF_HOME=/data/.cache/huggingface` → set by the user or replaced by cached
models; user secrets → mapped explicitly.

## Code translation

fal app (before):

```python
import fal
from pydantic import BaseModel
from fal.toolkit import Image

class Input(BaseModel):
    prompt: str

class Output(BaseModel):
    image: Image

class MyApp(fal.App):
    machine_type = "GPU-H100"
    keep_alive = 300
    max_concurrency = 5
    requirements = ["diffusers[torch]==0.32.2", "transformers", "accelerate"]

    def setup(self):
        import torch
        from diffusers import StableDiffusionXLPipeline
        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16).to("cuda")

    @fal.endpoint("/")
    def run(self, request: Input) -> Output:
        return Output(image=Image.from_pil(self.pipe(request.prompt).images[0]))
```

Runpod SDK, queue endpoint (after). Function keyword arguments are the job `input`:

```python
import runpod

app = runpod.App("my-demo-app")
sdxl = runpod.Model("stabilityai/stable-diffusion-xl-base-1.0")
_PIPE = None

@app.queue(gpu="H100", workers=(0, 5), idle_timeout=300, model=sdxl,
           dependencies=["diffusers==0.32.2", "transformers", "accelerate"])
def generate(prompt: str):
    global _PIPE
    import base64, io, torch
    from diffusers import StableDiffusionXLPipeline
    if _PIPE is None:  # once per deployed worker
        _PIPE = StableDiffusionXLPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16).to("cuda")
    buf = io.BytesIO()
    _PIPE(prompt).images[0].save(buf, format="JPEG")
    return {"image_b64": base64.b64encode(buf.getvalue()).decode(), "content_type": "image/jpeg"}
```

Runpod SDK, HTTP class (after). `@runpod.init` is the `setup()` equivalent; routes take the JSON
body with no `input` wrapper:

```python
@app.api(gpu="H100", workers=(0, 5), idle_timeout=300, model=sdxl,
         dependencies=["diffusers==0.32.2", "transformers", "accelerate"])
class MyApp:
    @runpod.init
    def setup(self):
        import torch
        from diffusers import StableDiffusionXLPipeline
        self.pipe = StableDiffusionXLPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16).to("cuda")

    @runpod.post("/generate")
    async def generate(self, body: dict):
        import base64, io
        buf = io.BytesIO()
        self.pipe(body["prompt"]).images[0].save(buf, format="JPEG")
        return {"image_b64": base64.b64encode(buf.getvalue()).decode()}
```

Custom image handler (after). Module-level load runs once per worker; `rp_upload` reads
`BUCKET_ENDPOINT_URL`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY`:

```python
import runpod, torch
from diffusers import StableDiffusionXLPipeline
from runpod.serverless.utils import rp_upload

pipe = StableDiffusionXLPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16).to("cuda")

def handler(job):
    prompt = job["input"].get("prompt")
    if not prompt:
        return {"error": "Input is missing the 'prompt' key."}
    path = f"/tmp/{job['id']}.png"
    pipe(prompt).images[0].save(path)
    return {"image": {"url": rp_upload.upload_image(job["id"], path)}}

runpod.serverless.start({"handler": handler})
```

Dockerfile: CUDA base image, `pip install runpod` plus dependencies, `COPY handler.py`,
`CMD ["python", "-u", "/handler.py"]`. Build with `docker build --platform linux/amd64`.

Other contracts:

| fal | Runpod |
|---|---|
| `@fal.endpoint("/stream")` + `StreamingResponse` | Generator handler or generator `@app.queue` function, read from `/stream/JOB_ID`; or keep the SSE route on a load-balancing endpoint |
| `@fal.realtime("/realtime")`, `is_websocket=True` | FastAPI `@app.websocket("/ws")` + `GET /ping` in a custom image on a load-balancing endpoint; see [golden path 17](../../runpod/golden-paths/17-serverless-websocket.md) |
| `exposed_port` server | Same image on a load-balancing endpoint; `GET /ping` returns 200 when ready (204 while starting); bind `PORT`; set `PORT_HEALTH` to the same port; see [golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md) |
| `handle_exit()` / `teardown()` | Signal handling in the user's own process |
| Return HTTP 503 to recycle a runner | `return {"refresh_worker": True, ...}` from the handler |

SDK details: [runpod-flash/reference/api.md](../../runpod-flash/reference/api.md) and
[patterns.md](../../runpod-flash/reference/patterns.md).

## Data

| fal source | Runpod target | Transfer |
|---|---|---|
| `/data/.cache/huggingface` | Cached models | Do not copy. `model=runpod.Model(...)` or `--model-reference https://huggingface.co/ORG/NAME:main` |
| `/data` custom weights | Network volume | `fal files download REMOTE LOCAL`, then `aws s3 cp --region DC --endpoint-url https://s3api-DC.runpod.io/ LOCAL s3://VOLUME_ID/PATH` |
| Large or many files | Network volume | Start a Pod with the volume attached and pull from the original source |
| fal CDN outputs the app stores by URL | User's own bucket | Download before fal shutdown; URLs follow fal retention settings |
| Secrets | Runpod secrets | Values cannot be read from fal; `rp secret add NAME` prompts for the value |

Create the volume first: `runpodctl network-volume create --name NAME --size GB --data-center-id DC`.
The S3 API needs a separate S3 API key and exists in the data centers listed in the storage
reference ([storage.md](../../runpod-usage/reference/storage.md)). Load weights from local disk,
not straight off the mount ([model-caching.md](../../runpodctl/reference/model-caching.md)).

## Client and API call map

| fal | Runpod |
|---|---|
| `POST https://queue.fal.run/MODEL_ID` body `{...}` | `POST https://api.runpod.ai/v2/ENDPOINT_ID/run` body `{"input": {...}}` |
| `POST https://fal.run/MODEL_ID` | `POST .../runsync` |
| `GET .../requests/ID/status` then `GET .../requests/ID` | `GET .../status/JOB_ID` (status and `output` together) |
| `PUT .../requests/ID/cancel` | `POST .../cancel/JOB_ID` |
| `?fal_webhook=URL`, `webhook_url=` | Top-level `"webhook": "URL"` beside `input` |
| `Authorization: Key $FAL_KEY` | `Authorization: Bearer $RUNPOD_API_KEY` |
| `request_id` | `id` |
| `images[0].url`, `video.url`, `audio.url` | `output.image_url`, `output.video_url`, `output.audio_url`, or `output.result` (per model page), plus `output.cost` |
| `image_size`, `guidance_scale`, `output_format`, `image_url`, `image_urls` (FLUX and common) | `width` + `height` or `size`, `guidance`, `image_format` or `output_format`, `image`, `images` (per model page) |
| `fal_client.subscribe(ID, arguments=...)` | `runpod.Endpoint(ID).run_sync({...})` or `/runsync` |
| `fal_client.submit(...)`, `handle.get()` | `runpod.Endpoint(ID).run({...})`, `.status()`, `.output()` |
| `fal_client.upload_file(path)` | Upload to the user's bucket; pass a fetchable URL |
| `fal.image("fal-ai/flux/dev")` (`@ai-sdk/fal`) | `runpod.image("black-forest-labs-flux-1-dev")` (`@runpod/ai-sdk-provider`); `providerOptions.fal` → `providerOptions.runpod` |
| Statuses `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED` (errors are `COMPLETED` + `error`) | `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT` |
| Webhook body `{request_id, status: OK or ERROR, payload}` | Webhook body is the job object (`id`, `status`, `output`) |

Facts that change client behavior:

- Results are retained 30 minutes after a `/run` job completes and 1 minute for `/runsync`; fal keeps request payloads 90 days by default.
- Public Endpoint output URLs expire after 7 days.
- Webhook delivery expects a 200 and retries 2 more times, 10 seconds apart; fal retries for about an hour and signs deliveries.
- Job payload limits: 10 MB on `/run`, 20 MB on `/runsync`. Load-balancing endpoints: 30 MB, 5.5 minute processing timeout, 2 minute wait for a worker, no queue.
- Poll `/status` with a growing interval and treat four statuses as terminal.

## Gaps: stop and ask the user

| Difference | Options to offer |
|---|---|
| Model ID with no listed Public Endpoint (FLUX Pro, Veo, Ideogram, ElevenLabs families, `workflows/...`, and others) | Keep that call on fal; self-host an open model on Serverless; pick a different listed model |
| Same-name model gives different output | Tune parameters per the Runpod model page; keep fal for that model |
| fal workflow endpoints | Chain calls in client code; keep on fal |
| `fal_client.upload_file` inputs | User supplies a bucket for inputs |
| `Image`/`File` outputs auto-hosted on fal CDN | User supplies an S3-compatible bucket for `rp_upload`; or return base64 under the payload limit |
| Signed webhooks | Secret token in the webhook URL plus `/status` confirmation; user accepts or adds their own gateway |
| `@fal.realtime` clients (`fal.realtime.connect`, msgpack) | Rewrite client and server to a plain WebSocket protocol on a load-balancing endpoint; keep realtime on fal |
| `app_auth = "public"` or `"shared"` | User's backend proxies with its API key; publish to the Hub for others to deploy |
| `/data` shared across all apps and regions | One network volume per data center; a global volume (beta, GPU compute); cached models for HF weights |
| `concurrency_buffer`, automatic retry of runner failures | Raise `workers` min; call `/retry/JOB_ID` from the client |
| 90-day request history | Persist results from the webhook receiver |
| fal Compute `8xH100-SXM` or multi-node sectors | Multi-GPU Pod or Instant Cluster, subject to live stock; never state it is available without checking |
| Data center choice | Volume location constrains GPU stock; confirm with the user before creating volumes |

## Verify

1. Public Endpoint: `POST /runsync` with the mapped `input`; expect `status: COMPLETED` and a fetchable `output` URL.
2. Queue endpoint: `POST /run`, poll `/status/JOB_ID` to a terminal status; record `delayTime` and `executionTime` for a cold and a warm request.
3. Load-balancing endpoint: poll `GET https://ENDPOINT_ID.api.runpod.ai/ping` until 200 (bound the client timeout), then call a route; for WebSockets connect with `open_timeout=60` and the Bearer header.
4. Webhook: submit with `webhook` and confirm the receiver gets the job object.
5. Run the same prompt and seed on fal and Runpod and show the user both outputs.
6. Failure path: submit an invalid input and confirm the client handles `FAILED`.
7. Secrets and storage: log (not print values) that expected env vars and volume paths exist on the worker.

## Shut down fal

Run only after explicit user approval, and list the commands first. Deleting is permanent; export
`/data` files and stored CDN outputs before running these.

```bash
fal apps list --json                                   # per environment: add --env NAME
fal apps scale APP_NAME --min-concurrency 0 --concurrency-buffer 0
fal apps delete APP_NAME                               # add --env NAME for other environments
fal runners list                                       # confirm nothing is running
fal files rm REMOTE_PATH
fal secrets unset NAME
fal keys list && fal keys revoke KEY_ID
```

fal Compute instances bill per hour while they exist: delete them in the fal dashboard or with
`DELETE https://api.fal.ai/v1/compute/instances/INSTANCE_ID` (`Authorization: Key`). Model API
billing stops when the code stops calling fal. Repeat per team (`fal account set TEAM_NAME`).
