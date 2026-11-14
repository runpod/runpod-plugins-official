---
concepts: [flash, serverless-endpoint, serverless-handler, worker, network-volume, global-volume, runpod-secret, gpu-pool]
---
# Migrate from Modal to Runpod

Scope: move Modal Apps (Functions, Clses, Web Functions, Servers, schedules, Volumes, Secrets,
Dicts, Queues) to the Runpod Python SDK (`runpod.App` with `@app.queue`, `@app.task`,
`@app.api`), or to a custom Docker image on a queue-based or load-balancing Serverless
endpoint. The translation is mostly Python-to-Python. Write Runpod code next to the Modal code
and keep the Modal App deployed until the user approves shutdown.

Sources: Modal docs, checked 2026-11-14:
[App reference](https://modal.com/docs/sdk/py/latest/App),
[GPU guide](https://modal.com/docs/guide/gpu),
[lifecycle hooks](https://modal.com/docs/guide/lifecycle-functions),
[Web Functions](https://modal.com/docs/guide/webhooks),
[Servers](https://modal.com/docs/guide/servers),
[invocation methods](https://modal.com/docs/guide/function-invocation-methods),
[deployed Function lookups](https://modal.com/docs/guide/trigger-deployed-functions),
[Volumes](https://modal.com/docs/guide/volumes),
[Secrets](https://modal.com/docs/guide/secrets),
[1.0 migration guide](https://modal.com/docs/guide/modal-1-0-migration),
[CLI reference](https://modal.com/docs/cli/latest/intro).
Runpod side: [runpod-flash](../../runpod-flash/SKILL.md),
[SDK API](../../runpod-flash/reference/api.md),
[SDK patterns](../../runpod-flash/reference/patterns.md).

## Detect

| Signal (grep) | What it means | Lands on |
|---|---|---|
| `import modal` or `from modal import` | Modal Python SDK in use | Translate the file |
| `modal\.(App\|Stub)\(` | App definition (`Stub` is the old name) | `runpod.App("name")` |
| `@app\.function\(` | Function | `@app.queue`, or `@app.task` for long jobs |
| `@app\.cls\(` with `@modal\.(enter\|method\|exit)` | Class with lifecycle hooks | `@app.queue` + module-level cache, or `@app.api` + `@runpod.init` |
| `@modal\.(fastapi_endpoint\|web_endpoint)` | Single-route web endpoint (`web_endpoint` is the old name) | `@app.api` |
| `@modal\.(asgi_app\|wsgi_app\|web_server)` | Full web app or raw server | `@app.api`, or load-balancing endpoint with a custom image |
| `@app\.server\(` | Modal Server (HTTP process on a port) | Load-balancing endpoint |
| `schedule=modal\.(Cron\|Period)` | Scheduled Function | External scheduler calling the endpoint (gap) |
| `modal\.Image\.` | Image builder chain | `dependencies=`, `system_dependencies=`, `image=`, or a Dockerfile |
| `modal\.Volume\.from_name` or `volumes=\{` | Volume mount | `runpod.NetworkVolume` + `mounts=` |
| `modal\.CloudBucketMount` | Bucket mounted as a directory | SDK calls in code, or copy to a network volume (gap) |
| `modal\.Secret\.(from_name\|from_dict\|from_dotenv)` | Secrets as env vars | `env={"KEY": runpod.Secret("name")}` |
| `modal\.(Dict\|Queue)\.from_name` | Distributed state | External store (gap) |
| `modal\.Sandbox\.create` | Sandboxed exec | Pod (gap) |
| `\.(map\|starmap\|for_each\|spawn_map)\(` on a Modal function | Fan-out | `.spawn()` loop (gap) |
| `@modal\.batched` | Dynamic batching | List inputs or in-worker batching (gap) |
| `@modal\.concurrent\(` or `allow_concurrent_inputs=` | Input concurrency | `max_concurrency=` (queue only) |
| `keep_warm=\|concurrency_limit=\|container_idle_timeout=` | Pre-1.0 autoscaler names | `workers=(min, max)`, `idle_timeout=` |
| `modal\.(Function\|Cls)\.(from_name\|lookup)\(` | Caller of a deployed App | `runpod.Queue` / `runpod.Api` / `runpod.Endpoint` |
| `[a-z0-9-]+--[a-z0-9-]+\.modal\.run` | HTTP caller of a Web Function | Runpod endpoint URL + Bearer key |
| `Modal-Key` or `Modal-Secret` header | Proxy Token auth | `Authorization: Bearer RUNPOD_API_KEY` |
| `MODAL_TOKEN_ID\|MODAL_TOKEN_SECRET` | Credentials in env or CI | `RUNPOD_API_KEY` |
| `modal (run\|serve\|deploy\|shell\|volume\|secret\|app) ` in scripts or CI | CLI automation | `rp flash ...`, `rp secret ...`, `runpodctl ...` |
| `\.modal\.toml` | Local Modal config | `~/.runpod/config.toml` (`rp login`) |

Live inventory when the `modal` CLI is authenticated (read-only): `modal app list --json`,
`modal app info APP`, `modal volume list --json`, `modal secret list --json`, `modal dict list`,
`modal queue list`, `modal endpoint list`, `modal environment list`. Add `--env NAME` per
Environment. `modal secret list` returns names only; the user supplies values.

## Product map

| Modal | Runpod | Decide by |
|---|---|---|
| Function or Cls called with `.remote()` / `.spawn()` | `@app.queue` | Default for request and response work |
| Function with long `timeout`, training, fine-tuning | `@app.task` | One Pod per call, no execution limit |
| `fastapi_endpoint`, small `asgi_app` with JSON routes | `@app.api` | Routes are GET (no args) and POST (JSON body) |
| Full FastAPI/Flask/Django app, streaming responses, `web_server`, `@app.server` | Load-balancing endpoint, custom image | App needs path params, middleware, Pydantic models, or its own server |
| App with a long `modal.Image` chain or `from_dockerfile` | Custom image + `runpod.serverless.start` handler | Dependencies exceed the SDK artifact (1,500 MB) or need a specific base |
| Modal Shared Endpoint (per-token LLM) | Public Endpoint | Hosted model |
| Modal Dedicated Endpoint, vLLM Server | vLLM worker endpoint (use the runpod-vllm skill) | OpenAI-compatible route |
| Sandbox, `modal shell`, tunnels (`modal.forward`) | Pod | Long-lived container with ports and SSH |
| `@modal.clustered` | Instant Cluster | Multi-node |
| Volume | Network volume (one data center) or global volume (GPU only, object-backed) | Write-heavy or CPU: network. Multi-region read-mostly: global |
| Secret (multi-key) | One Runpod secret per value | |
| Environment | App environment (`rp flash deploy --env`) | Secrets and volumes are account-scoped on Runpod |

## Field map

| Modal decorator argument | Runpod SDK argument | `runpodctl serverless create` | REST v2 (`POST /v2/serverless`) |
|---|---|---|---|
| `gpu="H100"` | `gpu="H100"` | `--gpu-id` (pool or device ID) | `gpu.pools` |
| `gpu="H100:4"` | `gpu="H100", gpu_count=4` | `--gpu-count` | `gpu.count` |
| `gpu=["H100", "A100-80GB"]` | `gpu=["H100", GpuGroup.AMPERE_80]` | | `gpu.pools` (list) |
| `cpu=`, `memory=` (CPU Function) | `cpu="cpu3c-2-4"` | `--compute-type CPU --instance-id` | `cpu[].id`, `cpu[].vcpuCount` |
| `ephemeral_disk` (MiB) | `container_disk_gb` (GB) | template `--container-disk-in-gb` | `disk` |
| `min_containers` (`keep_warm`) | `workers=(min, max)` | `--workers-min` | `workers.min` |
| `max_containers` (`concurrency_limit`) | `workers=(min, max)` | `--workers-max` | `workers.max` |
| `scaledown_window` (`container_idle_timeout`), seconds | `idle_timeout`, seconds | `--idle-timeout` | `workers.idleTimeout` |
| `timeout`, seconds | `execution_timeout_ms`, **milliseconds** (queue, API) | `--execution-timeout`, seconds | `timeout`, milliseconds |
| `@modal.concurrent(max_inputs=N)` | `max_concurrency=N` (queue) | handler `concurrency_modifier` | |
| `region=` | `datacenter="US-KS-2"` | `--data-center-ids` | `dataCenterIds` |
| `volumes={"/p": vol}` | `mounts={"/runpod-volume": vol}` (queue, API); any path on tasks | `--network-volume-id` | `mounts.network`, `mounts.global` |
| `secrets=[Secret.from_name("x")]` | `env={"KEY": runpod.Secret("x")}` | template `--env '{"KEY":"{{ RUNPOD_SECRET_x }}"}'` | `env` |
| `image=` | `dependencies`, `system_dependencies`, `image`, `registry_auth` | template `--image`, `--registry-auth-id` | `image`, `registry` |
| `enable_memory_snapshot` | `flashboot` (default `True`) | `--flash-boot` | `flashboot` (`OFF` by default in REST) |
| `retries`, `schedule`, `buffer_containers`, `cloud`, `proxy` | See *Gaps* | | |

GPU names:

| Modal | Runpod SDK `gpu=` | Pool |
|---|---|---|
| `T4` | `GpuGroup.AMPERE_16` | `AMPERE_16` |
| `L4` | `"L4"` | `AMPERE_24` |
| `A10`, `A10G` | `GpuGroup.AMPERE_24` or `GpuGroup.ADA_24` | `AMPERE_24`, `ADA_24` |
| `L40S` | `"L40S"` | `ADA_48_PRO` |
| `A100`, `A100-40GB` | `GpuGroup.AMPERE_48` or `GpuGroup.AMPERE_80` | `AMPERE_48`, `AMPERE_80` |
| `A100-80GB` | `GpuGroup.AMPERE_80` | `AMPERE_80` |
| `RTX-PRO-6000` | `GpuGroup.BLACKWELL_96` | `BLACKWELL_96` |
| `H100`, `H100!` | `"H100"` | `ADA_80_PRO` |
| `H200` | `"H200"` | `HOPPER_141` |
| `B200`, `B200+` | `"B200"` | `BLACKWELL_180` |
| `B300` | confirm with `runpodctl gpu list` | |
| `any` | `GpuGroup.ANY` | |

Check live stock (`runpodctl gpu list`, or the MCP capacity tools) in the data center that
holds the network volume before fixing a GPU. Stock varies by data center. Pick the GPU for
VRAM fit, not for price.

`modal.Image` methods: `pip_install` / `uv_pip_install` to `dependencies=[...]`;
`apt_install` to `system_dependencies=[...]`; `env({...})` to `env={...}`;
`from_registry("x")` to `image="x"`; `add_local_*` to the deployed project directory;
`run_commands`, `dockerfile_commands`, `from_dockerfile`, `workdir`, `entrypoint` to a
Dockerfile; `run_function(download)` to `model=runpod.Model(...)` or a volume. Leave `torch`,
`torchvision`, `torchaudio` out of `dependencies` on the built-in GPU image.

## Code translation

Function to queue:

```python
# Modal
@app.function(image=image, gpu="L4", timeout=600, scaledown_window=120, max_containers=5)
def embed(texts: list[str]) -> list[list[float]]: ...

@app.local_entrypoint()
def main(): print(embed.remote(["hi"]))
```

```python
# Runpod
import runpod
app = runpod.App("embed")

@app.queue(gpu="L4", dependencies=["sentence-transformers"], workers=(0, 5),
           idle_timeout=120, execution_timeout_ms=600000)
def embed(texts: list[str]) -> list[list[float]]: ...

@runpod.local_entrypoint
def main(): print(embed.remote(["hi"]))
```

Cls with `@modal.enter` to queue with a module-level cache:

```python
# Modal
@app.cls(gpu="A10", min_containers=1, secrets=[modal.Secret.from_name("huggingface")])
class Generator:
    @modal.enter()
    def load(self): self.pipe = pipeline("text-generation", model=MODEL, device=0)
    @modal.method()
    def generate(self, prompt: str) -> str: return self.pipe(prompt)[0]["generated_text"]
```

```python
# Runpod
qwen = runpod.Model("Qwen/Qwen2.5-7B-Instruct")
_PIPE = None

@app.queue(gpu=runpod.GpuGroup.AMPERE_24, workers=(1, 4), model=qwen,
           dependencies=["transformers"], env={"HF_TOKEN": runpod.Secret("hf-token")})
def generate(prompt: str) -> str:
    global _PIPE
    if _PIPE is None:
        from transformers import pipeline
        _PIPE = pipeline("text-generation", model=str(qwen.path), device=0)
    return _PIPE(prompt)[0]["generated_text"]
```

Web endpoint to API resource (`@runpod.init` replaces `@modal.enter`):

```python
# Modal
@app.function(image=image, gpu="T4")
@modal.asgi_app()
def web():
    api = FastAPI()
    @api.post("/classify")
    async def classify(body: dict): return clf(body["text"])[0]
    return api
```

```python
# Runpod
@app.api(gpu=runpod.GpuGroup.AMPERE_16, workers=(1, 3), dependencies=["transformers"])
class Classifier:
    @runpod.init
    def load(self):
        from transformers import pipeline
        self.clf = pipeline("sentiment-analysis", device=0)

    @runpod.post("/classify")
    async def classify(self, body: dict): return self.clf(body["text"])[0]

    @runpod.get("/health")
    async def health(self): return {"status": "ok"}
```

Training Function to task:

```python
# Modal
ckpt = modal.Volume.from_name("checkpoints", create_if_missing=True)

@app.function(gpu="H100", volumes={"/ckpt": ckpt}, timeout=86400,
              secrets=[modal.Secret.from_name("wandb")], retries=2)
def train(run: str) -> dict:
    ...; ckpt.commit()
```

```python
# Runpod
ckpt = runpod.NetworkVolume("checkpoints", size=100)

@app.task(gpu="H100", mounts={"/ckpt": ckpt}, dependencies=["wandb"],
          env={"WANDB_API_KEY": runpod.Secret("wandb-api-key")})
def train(run: str) -> dict:
    out = ckpt.path / run      # read .path inside the function
    ...                        # no commit(); writes are durable
```

Custom image path (queue handler): a module that defines `def handler(job)`, reads
`job["input"]`, returns JSON, and ends with `runpod.serverless.start({"handler": handler})`.
Load models at module level so they load once per worker.

Load-balancing path: keep the FastAPI/Flask app, add `GET /ping` returning `200` (or `204`
while loading), listen on `0.0.0.0:$PORT`, set `PORT` and `PORT_HEALTH` to the same value.
Worked example: [golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md).

Rules that change code:

- Queue arguments and results are JSON. Convert pickled objects (arrays, DataFrames, bytes) to
  lists, base64, or a URL.
- Import heavy packages inside function bodies. Replace `modal.is_local()` with `runpod.is_local()`.
- Delete `vol.commit()` and `vol.reload()`.
- One file per app for `rp flash dev`. `rp flash deploy` packages the project directory.
- Queue and API resource names need 3 or more characters.
- Verify with `rp flash dev FILE --once` before `rp flash deploy`.

## Data

| Modal | Runpod | Command |
|---|---|---|
| Secret key | Secret | `rp secret add NAME` (prompts for the value), or `POST /v2/account/secrets`. The user enters values. See [secrets](../../runpod-usage/reference/secrets.md). |
| Volume used as Hugging Face cache | `runpod.Model("owner/name")` or `--model-reference` | No copy |
| Volume with data | Network volume | `modal volume get VOL / ./export`, then `runpodctl network-volume create --name N --size GB --data-center-id DC`, then `runpodctl network-volume upload VOLUME_ID ./export /` |
| Large Volume | Network volume, copied from a Pod | CPU Pod with the volume attached, `pip install modal`, `modal volume get VOL / /workspace/` |
| CloudBucketMount | Bucket access in code, or one-time copy | `aws s3 sync` / `rclone` from a Pod to `/workspace` |
| Dict / Queue contents | External store | `modal dict items NAME --all --json` to export |

`network-volume upload` (runpodctl v3.1.0+) uses S3 API keys (`RUNPOD_S3_ACCESS_KEY`, `RUNPOD_S3_SECRET_KEY`), which
are separate from the API key, and a data center with the S3 API. Check
`runpodctl network-volume upload --help`, and
[command-reference](../../runpodctl/reference/command-reference.md) for resume behavior.
Volume root maps to `/runpod-volume` on Serverless and `/workspace` on Pods. A network volume
pins every resource that mounts it to its data center. Storage tiers:
[storage](../../runpod-usage/reference/storage.md).

## Client and API call map

| Modal | Runpod |
|---|---|
| `modal.Function.from_name("app", "fn").remote(x)` | `runpod.Queue(app="app", name="fn").remote(x=x)` (keyword arguments only) |
| `.spawn(x)` then `call.get(timeout=T)` | `.spawn(x=x)` then `job.result(timeout=T)` |
| `modal.FunctionCall.from_id(id).get()` | `GET https://api.runpod.ai/v2/ENDPOINT_ID/status/JOB_ID` |
| `call.cancel()` | `job.cancel()` / `POST .../cancel/JOB_ID` |
| `fn.remote_gen(x)` | `fn.stream(x)` / `GET .../stream/JOB_ID` |
| `modal.Cls.from_name("app", "Model")().method.remote(x)` | `runpod.Api(app="app", name="Model").post("/path", {...})` |
| Any endpoint by ID | `runpod.Endpoint("ENDPOINT_ID").run_sync({...})` / `.run({...})` |
| `POST https://WS--APP-FN.modal.run/path` | API or load-balancing: `POST https://ENDPOINT_ID.api.runpod.ai/path`, same body |
| Same, onto a queue endpoint | `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` with `{"input": {...}}`; result under `output` |
| `Modal-Key` + `Modal-Secret` headers, or public URL | `Authorization: Bearer RUNPOD_API_KEY` on every request |
| `modal run f.py` | `rp flash dev f.py --once` |
| `modal serve f.py` | `rp flash dev f.py` (no dev URL; call routes from the entrypoint) |
| `modal deploy f.py [--env E]` | `rp flash deploy [--env E]` |
| `modal app list` / `modal app stop APP` | `rp flash app list` / `rp flash undeploy --app APP` |
| `modal secret create N K=V` | `rp secret add N` |
| `modal volume put/get` | `runpodctl network-volume upload/download` (runpodctl v3.1.0+; check `runpodctl network-volume --help`) |
| `modal token set`, `MODAL_TOKEN_ID/SECRET` | `rp login --api-key`, `RUNPOD_API_KEY` |

Limits to carry into client changes: `/run` body 10 MB, `/runsync` 20 MB, load-balancing 30 MB;
results kept 30 minutes (async) and 1 minute (sync); `/runsync` waits 90 seconds by default;
default job TTL 24 hours.

## Gaps: stop and ask the user

| Modal feature | Why it needs a decision | Options |
|---|---|---|
| `schedule=modal.Cron/Period` | The SDK docs define no schedule argument | (a) external scheduler (GitHub Actions, cron host, orchestrator) calling `/run`; (b) keep the schedule on Modal calling Runpod during transition |
| `modal.Dict`, `modal.Queue` | The SDK docs describe no shared key-value or queue object | (a) Redis or a database with the URL in a secret; (b) drop a Queue that only feeds a Function, since the endpoint queues jobs |
| `.map()` / `.spawn_map()` | The SDK call styles are `.remote`, `.spawn`, `.stream`, `.local` | (a) `.spawn()` loop + `job.result()`; (b) `asyncio.gather` over `.remote.aio`; (c) Serverless batch jobs for offline runs |
| `@modal.batched` | Each queue job is handled on its own | (a) caller sends lists; (b) `max_concurrency` + batching in the worker |
| `retries=` | Retry policy is not a decorator argument in the SDK docs | (a) caller retries; (b) `job.retry()`; (c) resumable checkpoints for tasks |
| Results read hours later (Modal keeps `.spawn()` results 7 days) | Runpod keeps async results 30 minutes | (a) webhook; (b) write to a volume or bucket |
| Payloads above 10 MB (queue) or 30 MB (load balancing) | Smaller limits than Modal | (a) pass URLs; (b) shared volume; (c) chunking |
| Public Web Function URL (no auth) | Runpod requests carry an API key | (a) proxy that holds the key; (b) give callers a key |
| Custom domain on a Web Function | Endpoint URLs are on `api.runpod.ai` | Proxy or CDN in front |
| `modal.Proxy` static egress IP | This reference has no verified mapping | User picks another egress path; verify allowlists before cutover |
| `modal.Sandbox` | Different product shape | (a) Pods created and deleted per session; (b) keep sandboxes on Modal |
| `cpu=` / `memory=` on a GPU Function | `gpu` and `cpu` are mutually exclusive | Pick a GPU type that fits; drop the request |
| `min_containers >= 1` | Becomes an always-billed worker | Confirm the minimum with the user |
| `modal.parameter`, `with_options(gpu=...)` | Resources take their configuration at decoration time | (a) pass as input; (b) one resource per configuration |
| Multi-region Volume access | Network volumes are single data center | (a) one volume per data center + copies; (b) global volume (beta, GPU only, no file locking) |
| Long request on a web endpoint (Modal: 150 s then `303` redirects) | Load-balancing requests have a processing timeout (5.5 min) | Move long work to a queue endpoint with `/run` + `/status` |

Always ask before creating anything billable (endpoints, Pods, volumes), before setting worker
minimums above 0, and before any change to Modal resources.

## Verify

1. `rp flash dev FILE --once` exits 0 and prints the expected result.
2. `rp flash deploy`, then `rp flash app list` and `rp flash env get ENV` show the endpoints.
3. Real request from outside:
   `curl -s -X POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" -d '{"input": {...}}'`
   returns `"status": "COMPLETED"` and the same output as Modal for the same input.
   For API or load-balancing endpoints: `curl https://ENDPOINT_ID.api.runpod.ai/PATH` with the
   same header.
4. `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` shows workers and no failed jobs.
5. Measure one cold request and one warm request; report both next to the Modal numbers.
6. Volume check: a file written by one resource is readable by another that mounts the volume.
7. Cost guards in place: `execution_timeout_ms` set, `workers` maximum explicit, no forgotten
   task Pods (`runpodctl pod list`), no leftover `dev-` endpoints (`runpodctl serverless list`).

## Shut down Modal

Only after explicit user approval, and only after traffic runs on Runpod. Per Environment
(`--env NAME`):

```bash
modal app list
modal app stop APP_NAME --yes            # permanent; also ends its scheduled Functions
modal endpoint list                      # then: modal endpoint stop (check --help)
modal volume delete VOLUME_NAME --yes    # deletes all data; confirm the Runpod copy first
modal dict delete DICT_NAME --yes
modal queue delete QUEUE_NAME --yes
modal secret delete SECRET_NAME --yes
modal container list                     # expect no running containers
```

Then have the user revoke the Modal tokens and Proxy Tokens used by callers and CI, and remove
`MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` from CI secrets. On rollback, delete Runpod volumes
that are no longer needed: `rp flash undeploy` leaves them in place and they keep billing.
