---
name: flash
description: >-
  runpod-flash — code-first serverless: write Python locally, run it on remote
  Runpod GPUs/CPUs with `flash dev` (hot-reload + live worker logs), then
  `flash deploy`. Use for @Endpoint/@remote functions, resource config, and
  debugging flash deployments. For CLI-only infra management use runpodctl or
  runpod-mcp.
user-invocable: true
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Runpod Flash

Write code locally, iterate with `flash dev` — it runs your functions on remote Runpod GPUs/CPUs with hot-reload and live worker logs — then `flash deploy` to ship. `Endpoint` handles provisioning.

**Load on demand — this skill keeps the mental model + gotchas inline; details live in [`reference/`](reference/):**

| Need | Read |
|------|------|
| Install, auth, `flash init`, and the full `flash` command list | [reference/setup-and-cli.md](reference/setup-and-cli.md) |
| `Endpoint(...)` constructor params, `NetworkVolume`/`PodTemplate`/`EndpointJob`, GPU & CPU enum tables | [reference/api.md](reference/api.md) |
| Worked patterns — choosing a model, warm-worker model loading, CPU→GPU pipeline, parallel calls | [reference/patterns.md](reference/patterns.md) |

Quick start: `uv tool install runpod-flash` → `flash login` (or `export RUNPOD_API_KEY=...`) → `flash init my-project` → `flash dev`. Details in [reference/setup-and-cli.md](reference/setup-and-cli.md).

## Dev vs Deploy

- `flash dev` — **iterate.** Local server at `:8888`, but your decorated functions
  execute on **remote GPU/CPU workers**. Hot-reloads on save and **streams the worker's
  logs live** to the terminal. No build/upload/deploy wait — use this the whole time you
  develop.
- `flash deploy` — **ship.** Builds an artifact and deploys a stable endpoint. Slow
  (build + upload + provision); only do this once the code works under `flash dev`.

`flash dev` ships **only the function body** to the worker, so a `NameError` for a
module-level name surfaces immediately here. `flash deploy` imports the whole module and
can mask that bug (see Gotcha #1). Develop against `flash dev` and you catch it first.

## Autonomous Dev Loop

`flash dev` is a long-running server. Three rules:
- **Run it in the background** — don't block on it.
- **Capture its output** to a log file.
- **Drive it over HTTP.**

The captured log is the remote worker's live stream (cold start, model load, `print`s,
tracebacks) — read it to debug.

```bash
flash dev > /tmp/flash-dev.log 2>&1 &                          # background; never run it blocking
for i in $(seq 1 60); do grep -q "flash dev  localhost:" /tmp/flash-dev.log && break; sleep 2; done  # bounded ~2min; if it never appears, check the log for errors
URL=$(grep -o "localhost:[0-9]*" /tmp/flash-dev.log | head -1)               # actual port (8888 bumps if taken)
curl -s "$URL/main/predict" -d '{"data": {...}}'               # dispatches to the remote worker
```

- **Read the real URL from the log** — flash auto-bumps the port if 8888 is in use, and
  prints `✓ flash dev  localhost:<port>` plus the route table.
- **Routes are namespaced by file**: `main.py`'s `/predict` is served at `/main/predict`.
- **Two route shapes, two body shapes** (mismatch → `422` naming the missing field in `loc`):
  - **Load-balanced** (`@api.post("/predict")`) → `POST /main/predict`, body is the arg
    at top level: a handler `def predict(data: dict)` wants `{"data": {...}}` (not the bare object).
  - **Queue-based** (bare `@Endpoint` decorator) → `POST /main/runsync` (the local dev
    server only generates `/runsync`; production also exposes `/run`),
    body is **double-wrapped** in `input`: a handler `def synthesize(data: dict)` wants
    `{"input": {"data": {...}}}`. The outer `input` is the queue envelope; the inner key is
    the handler's param name.
- Edit a handler and save — hot-reload re-syncs the body; just re-send the request, no
  redeploy. Add `--auto-provision` to skip the first-call cold start. `kill %1` when done.

## Endpoint: Three Modes

Full constructor params and the GPU/CPU enum tables are in [reference/api.md](reference/api.md).

### Mode 1: Your Code (Queue-Based Decorator)

One function = one endpoint with its own workers.

```python
from runpod_flash import Endpoint, GpuGroup

@Endpoint(name="my-worker", gpu=GpuGroup.AMPERE_80, workers=5, dependencies=["torch"])
async def compute(data):
    import torch  # MUST import inside function (cloudpickle)
    return {"sum": torch.tensor(data, device="cuda").sum().item()}

result = await compute([1, 2, 3])
```

### Mode 2: Your Code (Load-Balanced Routes)

Multiple HTTP routes share one pool of workers.

```python
from runpod_flash import Endpoint, GpuGroup

api = Endpoint(name="my-api", gpu=GpuGroup.ADA_24, workers=(1, 5), dependencies=["torch"])

@api.post("/predict")
async def predict(data: list[float]):
    import torch
    return {"result": torch.tensor(data, device="cuda").sum().item()}

@api.get("/health")
async def health():
    return {"status": "ok"}
```

### Mode 3: External Image (Client)

Deploy a pre-built Docker image and call it via HTTP.

```python
from runpod_flash import Endpoint, GpuGroup, PodTemplate

server = Endpoint(
    name="my-server",
    image="my-org/my-image:latest",
    gpu=GpuGroup.AMPERE_80,
    workers=1,
    env={"HF_TOKEN": "xxx"},
    template=PodTemplate(containerDiskInGb=100),
)

# LB-style
result = await server.post("/v1/completions", {"prompt": "hello"})
models = await server.get("/v1/models")

# QB-style
job = await server.run({"prompt": "hello"})        # optional: webhook="https://..." for completion callback
await job.wait()
print(job.output)
```

Connect to an existing endpoint by ID (no provisioning):

```python
ep = Endpoint(id="abc123")
job = await ep.runsync({"prompt": "hello"})  # runsync wraps this as {"input": {"prompt": "hello"}}
print(job.output)
```

## How Mode Is Determined

| Parameters | Mode |
|-----------|------|
| `name=` only | Decorator (your code) |
| `image=` set | Client (deploys image, then HTTP calls) |
| `id=` set | Client (connects to existing, no provisioning) |

The table above is *how* the mode is picked from params. *When* to reach for `image=`:

### When to use `image=` (custom container) vs your own code

Default to writing Python (decorator / routes) — it runs arbitrary code with
`dependencies=[...]`/`system_dependencies=[...]` and needs no Dockerfile. Even large
HuggingFace models stay in decorator mode (weights stream at runtime — see
[reference/patterns.md → Loading ML models](reference/patterns.md#loading-ml-models-warm-workers)).
Reach for `image=` **only** when you need:

- **a pre-built inference server** — vLLM, TensorRT-LLM (`image="vllm/vllm-openai:latest"`, or `runpod/worker-vllm`, `runpod/worker-comfy`)
- **system-level deps not pip-installable** — a specific CUDA/cuDNN, OS libraries
- **models baked into the image** — to skip the runtime download entirely
- **an existing Runpod Serverless worker** — you already have a working image

Trade-off: `image=` mode **can't run arbitrary Python** (the image owns all logic) and the
image must implement a Runpod Serverless handler. Full list + examples:
https://docs.runpod.io/flash/custom-docker-images

## Gotchas

1. **Only the function body ships to the worker** -- most common error. Put imports *and* any module-level constants/helpers the function uses *inside* the decorated body. `flash deploy` imports the whole module so module globals happen to work; `flash dev` ships just the body, so a module-level name raises `NameError`. A handler that works deployed can break under dev — fix it by moving everything inside.
2. **Forgetting await** -- all decorated functions and client methods need `await`.
3. **Missing dependencies** -- must list in `dependencies=[]`.
4. **gpu/cpu are exclusive** -- pick one per Endpoint.
5. **idle_timeout is seconds** -- default 60s, not minutes.
6. **10MB payload limit** -- pass URLs, not large objects. Return binary (audio/images/files) as base64 in the JSON (`{"audio_b64": ...}`) and decode client-side; for larger outputs write to a NetworkVolume or upload to storage and return a URL.
7. **Client vs decorator** -- `image=`/`id=` = client. Otherwise = decorator.
8. **Auto GPU switching requires workers >= 5** -- pass a list of GPU types (e.g. `gpu=[GpuGroup.ADA_24, GpuGroup.AMPERE_80]`) and set `workers=5` or higher. The platform only auto-switches GPU types based on supply when max workers is at least 5.
9. **`runsync` timeout is 60s** -- cold starts can exceed 60s. Use `ep.runsync(data, timeout=120)` for first requests or use `ep.run()` + `job.wait()` instead.
10. **Request body shape (raw/external HTTP callers only)** -- match the request shape to the endpoint type:
    - **LB routes** (`@api.post(...)`): send the handler arg at the top level — `{"data": {...}}`.
    - **QB endpoints** (bare `@Endpoint`, hit via `.../run` or `.../runsync`): the worker calls
      **`handler(**job_input)`**, so the request's `input` keys must match the handler's parameter
      names — `def transcribe(input_data: dict)` wants `{"input": {"input_data": {...}}}`, and
      `def read(input: dict)` wants `{"input": {"input": {...}}}`. A mismatch fails with
      `got an unexpected keyword argument …`. Use `**kwargs` if the handler ignores the payload.
    - **Never send an empty `input`.** A QB request with `{"input": {}}` is rejected by the
      worker SDK as `Job has missing field(s): id or input` — always include at least one key.
    - *Context:* the flash client (`ep.runsync(x)`, `api.post(...)`) hides the spreading, so this
      only bites raw HTTP/external callers (mismatch behavior verified 2026-07-10 via worker logs).
      See *Autonomous Dev Loop*.
11. **Load a model once per worker (not per call)** -- for real inference use a class `@Endpoint` whose `__init__` loads the model once per worker (see [reference/patterns.md → Loading ML models](reference/patterns.md#loading-ml-models-warm-workers)). In function-form, reconcile with #1 by caching in a module global *inside* the body so it works under both `flash dev` and `deploy`:
    ```python
    global _MODEL
    try: _MODEL
    except NameError: _MODEL = load_model()   # runs once per worker, reused across calls
    ```
12. **Native CUDA libs go in `dependencies=[]` too** -- e.g. CTranslate2/faster-whisper needs `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` or it silently falls back to CPU. Add them alongside the Python package.
13. **Silent 401 auth failure** -- a set `RUNPOD_API_KEY` env var overrides the `flash login` token, so a bad/expired key wins. The failure is quiet: provisioning logs `GraphQL request failed: 401`, but `flash dev` still prints its normal ready line ("failed endpoints deploy on-demand"), so it *looks* healthy. When endpoints fail to provision:
    1. Check the provisioning log for `GraphQL request failed: 401`.
    2. Verify the current key independently: `curl -s -o /dev/null -w '%{http_code}' https://rest.runpod.io/v1/endpoints -H "Authorization: Bearer $RUNPOD_API_KEY"` (200 = good, 401 = bad).
    3. Fix it: `unset RUNPOD_API_KEY` to fall back to the `flash login` token, or `export` a valid key.
14. **`system_dependencies=` adds to cold start** -- apt packages (e.g. `["ffmpeg", "espeak-ng"]`) install on the worker before first use, so the initial call is slower (on top of any model download); warm calls are unaffected.
15. **Teardown a deployed app with `flash app delete <app>`** -- `flash undeploy list` may show "no endpoints" for an app that is deployed and serving; `flash app delete` (or `runpodctl serverless delete <id>`) reliably removes it.

## Resources

- Setup & CLI: [reference/setup-and-cli.md](reference/setup-and-cli.md) · API & compute enums: [reference/api.md](reference/api.md) · Patterns: [reference/patterns.md](reference/patterns.md)
- Flash source: https://github.com/runpod/flash
- Runnable examples: https://github.com/runpod/flash-examples — clone and adapt the closest one
- Package (PyPI): https://pypi.org/project/runpod-flash/
- Docs: https://docs.runpod.io/flash/overview
  - Custom Docker images (when + how): https://docs.runpod.io/flash/custom-docker-images
  - Storage / network volumes: https://docs.runpod.io/flash/configuration/storage
