---
concepts: [serverless-endpoint, serverless-handler, endpoint-autoscaling, endpoint-release, model-store, template, runpod-secret, public-endpoint]
---
# Migrate from Baseten to Runpod

Scope: move Baseten Dedicated Inference (Truss models, `docker_server` custom servers, engine
deployments), Model APIs calls, Chains, and Training Jobs to Runpod Serverless (queue and
load-balancing endpoints, vLLM worker), Public Endpoints, Pods, and the Runpod SDK
(`runpod.App`). Baseten builds images from a Truss; Runpod runs an image you build, or an SDK
app with no image build. Sources: Baseten docs
([Truss configuration](https://docs.baseten.co/reference/truss-configuration),
[Model class](https://docs.baseten.co/development/model/model-class),
[custom servers](https://docs.baseten.co/development/model/custom-server),
[autoscaling](https://docs.baseten.co/deployment/autoscaling/overview),
[call your model](https://docs.baseten.co/inference/calling-your-model),
[async inference](https://docs.baseten.co/inference/async),
[Model APIs](https://docs.baseten.co/inference/model-apis/overview),
[Baseten CLI](https://docs.baseten.co/reference/cli/baseten/model),
[Terraform provider](https://registry.terraform.io/providers/basetenlabs/baseten/latest/docs)),
checked 2026-11-14.

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `config.yaml` with top-level `model_name:` next to `model/model.py` | Truss model with a `Model` class | Queue endpoint + handler, or `@app.queue` |
| `class Model:` with `def load(self)` and `def predict(self` | Truss `Model` class | `handler.py` |
| `docker_server:` in `config.yaml` | Custom HTTP server | Load-balancing endpoint (vLLM: vLLM worker) |
| `base_image:` with `vllm/vllm-openai` | vLLM custom server | vLLM worker |
| `trt_llm:` in `config.yaml` | Engine builder (TensorRT-LLM, BEI) | Gap: ask the user |
| `weights:` or `model_cache:` in `config.yaml` | Weights cached by Baseten (BDN) | Cached model (`hf://`) or network volume |
| `bdn:` with `mounts:` in `config.yaml` | BDN volume mount | Network volume |
| `import truss_chains` or `chains.ChainletBase` | Chain | One endpoint per Chainlet + CPU orchestrator |
| `truss push`, `baseten model push`, `baseten truss` | Deploy step in CI or scripts | Image build + endpoint update, or `rp flash deploy` |
| `truss train`, `baseten train push`, `baseten loops` | Training Jobs or Loops | Pod or `@app.task` (Loops: gap) |
| `model-[a-z0-9]+\.api\.baseten\.co` | Dedicated inference call | `api.runpod.ai/v2/ENDPOINT_ID` |
| `/async_predict`, `/async_request/` | Async inference | `/run` + `/status` |
| `chain-[a-z0-9]+\.api\.baseten\.co`, `run_remote` | Chain call | Orchestrator endpoint |
| `inference.baseten.co` | Model APIs (OpenAI-compatible) | Public Endpoint or vLLM endpoint |
| `api.baseten.co/v1` | Management API automation | REST v2 (`api.runpod.io/v2`) |
| `BASETEN_API_KEY`, `Authorization: Api-Key` | Baseten auth | `RUNPOD_API_KEY`, `Authorization: Bearer` |
| `X-BASETEN-SIGNATURE`, `async_predict_completed` | Baseten webhook receiver | Rewrite for the Runpod job payload |
| `BT_MODEL_ID`, `BT_MODEL_DEPLOYMENT_ID`, `/secrets/` reads | Baseten runtime contract in server code | See the env map below |
| `source = "basetenlabs/baseten"`, `resource "baseten_model"` | Terraform | `runpod_serverless_endpoint` |
| `.trussrc` | Local Truss credentials | `rp login` |

## Product map

| Baseten | Runpod | Note |
| --- | --- | --- |
| Truss model (`/predict`) | Queue endpoint with `handler(job)` | Body is `{"input": ...}`; output is under `output` |
| Truss generator `predict` | Streaming handler (`yield`) + `/stream/JOB_ID` | HTTP streaming needs a load-balancing endpoint |
| Truss `chat_completions` / `/v1` methods | Load-balancing endpoint or vLLM worker | |
| `docker_server` | Load-balancing endpoint | Paths pass through unchanged; health path is `/ping` or `HEALTH_CHECK_PATH` |
| vLLM server | vLLM worker (Hub) | OpenAI route `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1` |
| Model APIs | Public Endpoint | OpenAI-compatible text endpoints: `gpt-oss-120b`, `qwen3-32b-awq` |
| Chains | Endpoints + CPU orchestrator | You write the calls between steps |
| Training Jobs | Pod, `@app.task` | Multi-node: Instant Cluster |
| Deployment / environment / promotion | Endpoint release / one endpoint per environment / image update | SDK apps: `rp flash deploy --env NAME` |
| Replica, min / max replicas | Worker, `workers.min` / `workers.max` | |
| Baseten secret | Runpod secret, env value `{{ RUNPOD_SECRET_name }}` | Secret names starting with `runpod` are rejected |
| Region | Data center | |
| BDN volume (immutable, read-only mount) | Network volume (writable, one data center) | Mounts at `/runpod-volume` on Serverless |
| Per-minute billing per replica | Per-second billing per running worker | Quote Runpod prices only from Runpod pricing |

## Field map

`config.yaml` to Runpod:

| Baseten field | REST v2 (`POST /v2/serverless`) | `runpodctl` | Runpod SDK decorator |
| --- | --- | --- | --- |
| `model_name` | `name` | `--name` | `runpod.App("...")`, function name |
| `python_version` | base image | base image | `rp flash deploy --python-version` |
| `requirements`, `requirements_file` | in the image | in the image | `dependencies=[...]`, `requirements.txt` |
| `system_packages` | in the image (`apt-get`) | in the image | `system_dependencies=[...]` |
| `build_commands` | Dockerfile `RUN` | Dockerfile `RUN` | custom `image=` |
| `base_image.image` | `image` (or `FROM`) | `template create --image` | `image=` |
| `base_image.docker_auth` | `registry` (credential ID from `/v2/registries`) | `registry create`, `template create --registry-auth-id` | `registry_auth=` |
| `docker_server.start_command` | `cmd` / `entrypoint` | `template create --docker-start-cmd` | n/a |
| `docker_server.server_port` | `ports: ["PORT/http"]`, env `PORT`, `PORT_HEALTH` | `template create --ports`, `--env` | n/a |
| `docker_server.readiness_endpoint` | env `HEALTH_CHECK_PATH` | `--env` | `@runpod.get` health route |
| `resources.accelerator` | `gpu.pools` | `--gpu-id POOL` | `gpu=` |
| `resources.accelerator: X:N` | `gpu.count` | `--gpu-count` | `gpu_count=` |
| `resources.cpu` / `memory` (CPU-only) | `cpu: [{id, vcpuCount}]` | `--compute-type CPU --instance-id` | `cpu="cpu3g-4-16"` |
| `resources.node_count` | `/v2/clusters` | n/a | n/a |
| `secrets` | `env` value `{{ RUNPOD_SECRET_name }}` | `template create --env` JSON | `env={"K": runpod.Secret("name")}` |
| `environment_variables` | `env` | `template create --env` JSON | `env={...}` |
| `runtime.predict_concurrency` | handler `concurrency_modifier` | same | `max_concurrency=` |
| `runtime.health_checks.startup_threshold_seconds` | env `RUNPOD_INIT_TIMEOUT` (default 420 s) | `--env` | `env=` |
| `weights` / `model_cache` (Hugging Face) | console **Model** field | `serverless create --model-reference URL` | `model=runpod.Model("org/name")` |
| `weights` (S3, GCS, R2, Azure), `bdn.mounts` | `mounts.network: [{volumeId}]` | `--network-volume-id` | `mounts={"/runpod-volume": NetworkVolume(...)}` |
| `data/`, `packages/`, `external_data` | in the image (`COPY`, `RUN wget`) | in the image | project files |
| `trt_llm` | gap | gap | gap |

Autoscaling (`baseten model push` and `baseten model deployment update-autoscaling` flags):

| Baseten | REST v2 | `runpodctl serverless create` | SDK |
| --- | --- | --- | --- |
| `--min-replica` (default 0) | `workers.min` | `--workers-min` | `workers=(min, max)` |
| `--max-replica` (default 1) | `workers.max` (default 3) | `--workers-max` | `workers=(min, max)` |
| `--scale-down-delay` (default 900 s) | `workers.idleTimeout` (1 to 3600 s, REST default 10) | `--idle-timeout` | `idle_timeout=` (default 60) |
| `--concurrency-target` | `scaling: {type: REQUEST_COUNT, requestCount: N}` | `--scale-by requests --scale-threshold N` | `scaler_type="REQUEST_COUNT", scaler_value=N` |
| `--target-utilization-percentage`, `--autoscaling-window`, `--max-scale-down-rate` | approximate with a lower `requestCount` | approximate with a lower `--scale-threshold` | approximate with a lower `scaler_value` |
| `--instance-type` | `gpu.pools` / `cpu` | `--gpu-id` / `--instance-id` | `gpu=` / `cpu=` |
| `--region` | `dataCenterIds` | `--data-center-ids` | `datacenter=` |

Rules: `name`, `type` (`QUEUE` or `LOAD_BALANCER`) and `scaling` are required on create.
`LOAD_BALANCER` endpoints take `REQUEST_COUNT` scaling. A `QUEUE` endpoint scaled by
`REQUEST_COUNT` rejects `idleTimeout`; use `QUEUE_DELAY` (`queueDelay`, default 4 s) when a
long idle timeout matters. REST v2 defaults `flashboot` to `OFF` and `timeout` to 300000 ms.
`runpodctl serverless create` makes queue endpoints; create load-balancing endpoints with REST
v2 or the MCP server. Each Serverless template binds to one endpoint. For exact flags check
`runpodctl serverless create --help` and `runpodctl template create --help`.

GPU pools by VRAM: `T4` to `AMPERE_16`; `L4`, `A10G` to `AMPERE_24` (or `ADA_24`);
`H100_40GB`, `L40S` to `ADA_48_PRO` or `AMPERE_48`; `A100` to `AMPERE_80`; `H100` to
`ADA_80_PRO`; `RTX_PRO_6000` to `BLACKWELL_96`; `H200` to `HOPPER_141`; `B200` to
`BLACKWELL_180`. CPU `4x16` to `cpu3g-4-16`. Check live stock (`runpodctl gpu list`,
`GET /v2/catalog/gpus`) before choosing. See
[gpu-selection](../../runpod-usage/reference/gpu-selection.md).

## Code translation

Truss `Model` class to a handler. `__init__` + `load()` become module scope, `predict(model_input)`
becomes `handler(job)` reading `job["input"]`, secrets become env vars.

```python
# Baseten: model/model.py
import os
from transformers import pipeline

class Model:
    def __init__(self, **kwargs):
        self._secrets = kwargs["secrets"]
        self._pipe = None

    def load(self):
        self._pipe = pipeline("text-generation", model=os.environ["MODEL_ID"],
                              token=self._secrets["hf_access_token"], device_map="auto")

    def predict(self, model_input):
        out = self._pipe(model_input["prompt"], max_new_tokens=256, return_full_text=False)
        return {"output": out[0]["generated_text"]}
```

```python
# Runpod: handler.py
import os
import runpod
from transformers import pipeline

pipe = pipeline("text-generation", model=os.environ["MODEL_ID"],
                token=os.environ.get("HF_TOKEN"), device_map="auto")

def handler(job):
    model_input = job["input"]
    out = pipe(model_input["prompt"], max_new_tokens=256, return_full_text=False)
    return {"output": out[0]["generated_text"]}

runpod.serverless.start({"handler": handler})
```

```dockerfile
# Runpod: Dockerfile (requirements.txt lists runpod plus the Truss requirements)
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
WORKDIR /
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY handler.py .
CMD ["python3", "-u", "/handler.py"]
```

Other contracts:

| Truss | Runpod handler |
| --- | --- |
| `preprocess` / `postprocess` | Call in order inside `handler` |
| `predict` returns a generator | `handler` yields; add `"return_aggregate_stream": True` to `runpod.serverless.start` |
| `async def predict` + `predict_concurrency: N` | `async def handler` + `"concurrency_modifier": lambda current: N` |
| Raise an exception | Job status `FAILED`; or return `{"error": "..."}` |
| `kwargs["environment"]["name"]` | Env var set per endpoint |
| `kwargs["data_dir"]` | Path copied into the image |
| `request.headers["x-baseten-request-id"]` | `job["id"]` |

SDK alternative (no Dockerfile). `@runpod.init` is the documented once-per-worker hook on
`@app.api` classes and mirrors `load()`; for `@app.queue`, verify in `rp flash dev` that
module-level state survives between calls. Details: [runpod-flash](../../runpod-flash/SKILL.md).

```python
import runpod

app = runpod.App("text-generator")
weights = runpod.Model("HuggingFaceTB/SmolLM2-1.7B-Instruct")

@app.api(gpu="AMPERE_24", workers=(0, 3), idle_timeout=300, model=weights,
         dependencies=["transformers", "accelerate"],
         env={"HF_TOKEN": runpod.Secret("hf_access_token")})
class TextGenerator:
    @runpod.init
    def setup(self):
        from transformers import pipeline
        self.pipe = pipeline("text-generation", model=str(weights.path), device_map="auto")

    @runpod.post("/predict")
    async def predict(self, body: dict):
        out = self.pipe(body["prompt"], max_new_tokens=256, return_full_text=False)
        return {"output": out[0]["generated_text"]}
```

`docker_server` to a load-balancing endpoint: same image; `start_command` to `cmd`;
`server_port` to `ports` plus env `PORT` and `PORT_HEALTH` (both default `80`, set both);
`readiness_endpoint` to env `HEALTH_CHECK_PATH`; secrets from `/secrets/NAME` to env vars.
Health codes: `200` healthy, `204` initializing. Limits: 5.5 min processing per request,
30 MB payload. Walkthrough:
[golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md). vLLM:
[runpod-vllm](../../runpod-vllm/SKILL.md).

Chain to endpoints: each `ChainletBase` becomes an endpoint; the `@chains.mark_entrypoint`
Chainlet becomes a CPU queue endpoint whose handler calls the others with
`POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` (or `/run` + `/status` for long steps),
using an API key passed as an env var from a secret.

## Data

| Baseten source | Runpod target | How |
| --- | --- | --- |
| `weights` `hf://org/name@rev`, `model_cache` `repo_id` | Cached model | `--model-reference https://huggingface.co/org/name:rev`; path `/runpod-volume/huggingface-cache/hub/models--org--name/snapshots/HASH/`; one per endpoint |
| `weights` `s3://`, `gs://`, `r2://`, `azure://` | Network volume | `runpodctl network-volume create`, then `aws s3 sync` to `s3://VOLUME_ID/` with `--endpoint-url https://s3api-DC.runpod.io/ --region DC` |
| BDN volume | Network volume | `baseten volume pull bdn:NS/VOL ./dir`, then upload as above |
| Truss `data/` | Image layer | `COPY data/ /data/` |
| Private artifacts, no data center pin | Model Repository | `runpodctl model --help`; see [model-caching](../../runpodctl/reference/model-caching.md) |
| Training checkpoints | Network volume | Download from Baseten before shutdown |

A network volume pins the endpoint to its data center; pick one that stocks the GPU pool.
See [storage](../../runpod-usage/reference/storage.md) and
[secrets](../../runpod-usage/reference/secrets.md).

## Client and API call map

| Baseten | Runpod |
| --- | --- |
| `POST https://model-ID.api.baseten.co/environments/production/predict`, body = input | `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync`, body `{"input": ...}` |
| Response = model output | Job object: `id`, `status`, `output`, `delayTime`, `executionTime` |
| `POST .../async_predict` `{"model_input", "webhook_endpoint", "priority", "max_time_in_queue_seconds"}` | `POST .../run` `{"input", "webhook", "policy": {"lowPriority", "ttl", "executionTimeout"}}` |
| `GET https://model-ID.api.baseten.co/async_request/REQUEST_ID` (status only) | `GET .../status/JOB_ID` (status and output, kept 30 min) |
| Cancel (only `QUEUED`) | `POST .../cancel/JOB_ID` (queued or running) |
| Streamed `/predict` body | `GET .../stream/JOB_ID` |
| `.../environments/production/sync/PATH` | `https://ENDPOINT_ID.api.runpod.ai/PATH` |
| OpenAI base `.../sync/v1` | `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1` (vLLM worker) |
| OpenAI base `https://inference.baseten.co/v1` | `https://api.runpod.ai/v2/gpt-oss-120b/openai/v1` or `.../qwen3-32b-awq/openai/v1` |
| `Authorization: Api-Key KEY` (legacy) or `Bearer KEY` | `Authorization: Bearer RUNPOD_API_KEY` |
| Webhook body `{request_id, data, errors, ...}` + `X-BASETEN-SIGNATURE` | Webhook body = job object; return `200`; up to 2 retries |
| `GET /v1/models`, `PATCH .../autoscaling_settings`, `POST .../promote`, `DELETE /v1/models/ID` | `GET /v2/serverless`, `PATCH /v2/serverless/ID` (`workers`, `scaling`, `image`), `DELETE /v2/serverless/ID` |
| `POST /v1/secrets` | `POST /v2/account/secrets` |

Status: `QUEUED` to `IN_QUEUE`; `IN_PROGRESS` to `IN_PROGRESS`; `SUCCEEDED` to `COMPLETED`;
`FAILED` to `FAILED`; `EXPIRED` to `TIMED_OUT`; `CANCELED` to `CANCELLED`; `WEBHOOK_FAILED` to
`COMPLETED` (fetch from `/status`).

Timing and size: `/runsync` waits 90 s by default (`?wait=` up to 300000 ms); Baseten sync
predict defaults to 1200 s. Use `/run` for long jobs and cold starts. Payload limits: 10 MB
`/run`, 20 MB `/runsync`. Runtime env: `BT_MODEL_ID` to `RUNPOD_ENDPOINT_ID`; replica identity
to `RUNPOD_POD_ID`; `PORT=8080` (reserved on Baseten) to `PORT` and `PORT_HEALTH` set by you.
Patterns: [endpoint-workflows](../../runpod-usage/reference/endpoint-workflows.md),
[webhooks](../../runpod/golden-paths/16-serverless-webhooks.md),
[streaming](../../runpod/golden-paths/12-serverless-streaming.md).

A new image tag goes on the endpoint itself (`PATCH /v2/serverless/ID` with `image`), which
creates a release. An endpoint created through REST v2 with `templateId` resolves the template
once at create time, so patch the endpoint, not the template. See
[endpoint-builds-and-releases](../../runpod-usage/reference/endpoint-builds-and-releases.md).

## Gaps: stop and ask the user

| Gap | Options |
| --- | --- |
| `trt_llm`, BEI, BIS-LLM engines | (a) vLLM worker with the same Hugging Face checkpoint; (b) the user's own TensorRT-LLM or embeddings server image on a load-balancing endpoint. Either changes the serving stack: ask for a benchmark and quality check |
| Chains | (a) endpoints + CPU orchestrator; (b) collapse steps into one handler when they share hardware |
| Loops | Run the training script on a Pod or `@app.task`; ask which framework and checkpoints to keep |
| Environments and promotion | (a) one endpoint per environment; (b) `rp flash deploy --env` for SDK apps. Ask how clients select an environment |
| Rolling deployment controls (pause, percentages) | Two endpoints with traffic split in the client or gateway |
| Sync requests longer than 5 minutes | Move the client to `/run` + `/status` or a webhook |
| Webhook signature verification | Token in the webhook URL plus a `/status` check; ask if this meets the user's security bar |
| Async `priority` levels | `policy.lowPriority` (two levels); or separate endpoints per tier |
| Target utilization, autoscaling window, schedules | Lower scaler value, higher `workers.min`; schedules need the user's own cron calling `PATCH /v2/serverless/ID` |
| gRPC or WebSocket transport | Worker with exposed ports, or a Pod; ask which clients depend on it |
| Regional environments, compliance policy | `dataCenterIds`; ask for the residency requirement |
| Single-tenant, self-hosted, hybrid hosting | Ask the user; Runpod workloads run in Runpod data centers |
| Model APIs model with no Public Endpoint | Deploy on a vLLM endpoint; ask for GPU budget and expected traffic |
| Responses or Anthropic Messages protocol on Model APIs | Move to chat completions, or serve the protocol from a custom server |
| Secret values | Baseten returns names only; ask the user for values |
| Idle timeout: Baseten default 900 s | Ask before copying it; a waiting worker is billed |

## Verify

1. `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` shows workers and no failed jobs.
2. Send one real input to `/runsync` (short) or `/run` + `/status`; require `status` `COMPLETED`.
3. Compare `output` with the Baseten response for the same input and sampling settings.
4. Send a second request; compare `executionTime` with Baseten latency and read `delayTime` for cold start.
5. Streaming: confirm chunks arrive from `/stream/JOB_ID`. Webhooks: confirm the receiver parses the job payload.
6. Load-balancing: `GET https://ENDPOINT_ID.api.runpod.ai/ping` (or the custom health path) returns `200`.
7. Confirm `workers.max` and the execution timeout are set as a cost guard, and that
   `workers.min` is 0 unless the user asked for warm capacity.

## Shut down Baseten

Run only after explicit user approval of each destructive step. Deactivate first; it is reversible.

```bash
baseten model list --output json
baseten model deployment deactivate --model-id MODEL_ID --deployment-id DEPLOYMENT_ID --yes
baseten train job list --status running
baseten train job stop --job-id JOB_ID --yes

# Irreversible: confirm each one
baseten model delete --model-id MODEL_ID --yes
curl -X DELETE https://api.baseten.co/v1/chains/CHAIN_ID -H "Authorization: Bearer $BASETEN_API_KEY"
baseten volume rm --recursive --yes bdn:NAMESPACE/VOLUME

baseten org billing usage
baseten org api-key list
```

A scaled-to-zero deployment still accepts requests and starts a replica, so deactivate
instead. Leave Baseten API key deletion and secret cleanup to the user.
