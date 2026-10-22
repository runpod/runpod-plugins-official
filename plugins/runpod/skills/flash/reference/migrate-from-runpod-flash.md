---
concepts: [flash]
---

# Migrate a `runpod-flash` project to the Runpod SDK

`runpod-flash` is deprecated on October 29, 2026 and gets no fixes after that date. Its
features live in the `runpod` package (2.0) as SDK apps with the `rp flash` CLI. Endpoints
already deployed with `runpod-flash` keep running; migrating changes how you build and deploy,
not what is running.

Run this as a plan with the user, not a silent rewrite: inventory, check *Known differences*,
convert, smoke-test with `rp flash dev --once`, deploy, then remove the old endpoints.

Keep a way back until the SDK version works: convert on a branch, and leave the
`runpod-flash` endpoints running until the new ones pass. If the SDK fails on something the old
package handled, roll back to the previous commit and keep deploying with `flash`, installed with
`uv tool install runpod-flash --with "runpod<2"`. Check the runpod-python
[CHANGELOG](https://github.com/runpod/runpod-python/blob/main/CHANGELOG.md) and
[commit history](https://github.com/runpod/runpod-python/commits/main/runpod/apps) for a fix
before retrying.

## 1. Inventory

```bash
grep -rnE "runpod_flash|runpod-flash|@Endpoint|flash (dev|deploy|build|login|undeploy|app|env)" \
  --include='*.py' --include='*.toml' --include='*.txt' --include='*.cfg' \
  --include='Makefile' --include='*.yml' --include='*.yaml' --include='*.sh' .
```

List every `Endpoint`, its mode (decorator, load-balanced routes, `image=`, `id=`), and every
CI step that calls `flash`.

## 2. Check known differences first

These patterns behave differently in the SDK. If the project relies on one, tell the user
before converting, and test it carefully or keep the project on `runpod-flash`:

- Projects split across multiple local files. Discovery ships one module per app.
- Classes as remote resources, other than `@app.api` classes.
- Path and query parameters on HTTP routes.
- Resources that reference an existing template or endpoint with `template=` or `id=`.
- `volume=[...]` lists across data centers. The SDK mounts one volume per queue or API
  resource.
- Local testing that curls `localhost:8888`. Dev sessions run no local server.

## 3. Install and log in

```bash
pip uninstall runpod-flash && pip install "runpod>=2.0.1"
# uv: uv remove runpod-flash && uv add "runpod>=2.0.1"
rp login            # a key saved by `flash login` keeps working
```

## 4. Convert the code

| runpod-flash | Runpod SDK |
|---|---|
| `from runpod_flash import Endpoint, GpuGroup, GpuType` | `import runpod` |
| project folder = app | `app = runpod.App("APP_NAME")` |
| `@Endpoint(name="x", gpu=..., ...)` on a function | `@app.queue(name="x", gpu=...)` |
| `api = Endpoint(name=..., ...)` + `@api.post("/p")` functions | `@app.api(...)` on a class with `@runpod.post("/p")` methods |
| class `@Endpoint` with `__init__` loading a model | `@app.api` class with a `@runpod.init` method |
| `await fn(x)` | `fn.remote(x)` or `await fn.remote.aio(x)` |
| `asyncio.gather(fn(a), fn(b))` | `[fn.spawn(a), fn.spawn(b)]` then `job.result()` |
| `if __name__ == "__main__": asyncio.run(main())` | `@runpod.local_entrypoint` on `main`, run with `rp flash dev main.py` |
| `gpu=GpuType.NVIDIA_GEFORCE_RTX_4090` | `gpu="4090"` (or `runpod.GpuType...`) |
| `gpu=GpuGroup.ADA_24` | `gpu="ADA_24"` (or `runpod.GpuGroup.ADA_24`) |
| `cpu=CpuInstanceType.CPU5C_4_8` | `cpu="cpu5c-4-8"` |
| `NetworkVolume(name="m", size=100, datacenter=DataCenter.US_CA_2)` | `runpod.NetworkVolume("m", size=100, datacenter="US-CA-2")` |
| `volume=vol`, files at `/runpod-volume/...` | `mounts={"/runpod-volume": vol}`, read `vol.path` inside the function |
| `template=PodTemplate(containerDiskInGb=100)` | `container_disk_gb=100` |
| `min_cuda_version=CudaVersion.V12_8` | `min_cuda_version="12.8"` |
| `env={"HF_TOKEN": "hf_..."}` | `env={"HF_TOKEN": runpod.Secret("hf-token")}` after `rp secret add hf-token` |
| `Endpoint(id="ID")` + `await ep.runsync(...)` | `runpod.Endpoint("ID").run_sync({...}, timeout=120)` |
| `Endpoint(name=..., image="IMG")` (image is a Serverless worker) | `image="IMG"` on a decorator (any Python 3 image); a prebuilt worker image goes through runpodctl/runpod-mcp + `runpod.Endpoint` |
| `idle_timeout`, `execution_timeout_ms`, `flashboot`, `scaler_type`, `scaler_value`, `accelerate_downloads`, `datacenter`, `dependencies`, `system_dependencies`, `gpu_count`, `max_concurrency` | same names on the decorator |

Before and after for a queue function:

```python
# runpod-flash
from runpod_flash import Endpoint, GpuType

@Endpoint(name="hello-gpu", gpu=GpuType.NVIDIA_GEFORCE_RTX_4090, dependencies=["numpy"])
async def hello():
    import torch
    return {"gpu": torch.cuda.get_device_name(0)}
```

```python
# Runpod SDK
import runpod

app = runpod.App("hello-gpu")

@app.queue(gpu="4090", dependencies=["numpy"])
def hello():
    import torch
    return {"gpu": torch.cuda.get_device_name(0)}

@runpod.local_entrypoint
def main():
    print(hello.remote())
```

Load-balanced routes become a class:

```python
# runpod-flash
api = Endpoint(name="my-api", gpu=GpuGroup.ADA_24, workers=(1, 5))

@api.post("/predict")
async def predict(data: list[float]): ...
```

```python
# Runpod SDK
@app.api(gpu="ADA_24", workers=(1, 5))
class MyApi:
    @runpod.post("/predict")
    async def predict(self, body: dict): ...     # body is the request JSON
```

## 5. Behavior that changes without an error

- **Default `workers` is `(0, 3)`**, not `(0, 1)`. Set it explicitly to keep the old ceiling.
- **The whole module ships** in dev and deploy alike, so the runpod-flash "only the function
  body ships under `flash dev`" workaround (imports and constants inside the body, the
  `try: _MODEL except NameError` cache) is no longer needed. It still works.
- **Queue arguments must be JSON-serializable**, in dev as well as deployed.
- **Raw HTTP body shapes.** Queue endpoints keep the runpod-flash shape: the function's
  keyword arguments go in `input` (`{"input": {"data": {...}}}` for `def f(data)`).
  Load-balanced routes change: a POST route receives the whole JSON body, so callers that sent
  `{"data": {...}}` to a runpod-flash route `def predict(data)` now send the object itself.
- **`.flashignore` becomes `.runpodignore`**, and `.gitignore` files apply too.
- **Local Python must be 3.10–3.14** and matches the worker's in dev sessions and tasks.
- **Volumes outlive undeploy** and keep billing.
- **The torch family still comes from the GPU image**, as in runpod-flash, including torch
  pulled in by another dependency. A CPU resource in the same app that needs torch installs it
  at cold start, so give it `container_disk_gb` room.
- **GPU device names pin the exact device**, as runpod-flash's pool exclusions did, now using
  the platform's live pool membership, so pool members runpod-flash didn't know about (MIG
  slices) are excluded too.
- **Every resource gets `RUNPOD_API_KEY`** in its worker env. runpod-flash added it only to
  endpoints that made remote calls, so after migrating, more endpoint templates hold the account
  key.

## 6. Smoke-test, deploy, clean up

```bash
rp flash dev main.py --once          # exits non-zero if the entrypoint fails
rp flash deploy                      # creates the new endpoints (default environment)
rp flash app list                    # confirm
```

Then, once the new endpoints pass, remove the ones deployed with `runpod-flash`, scoped to
that app:
`flash app delete OLD_APP` (with the old CLI still installed), or
`runpodctl serverless delete ENDPOINT_ID` for each old endpoint id. Update CI to call `rp flash`
instead of `flash`, and update any client that called the old endpoint ids.

## Silencing the notice in CI

`runpod-flash` 1.21.0 and later print a deprecation notice on every `flash` command and a
`FutureWarning` on import. Set `RUNPOD_FLASH_SILENCE_DEPRECATION=1` to silence both while a
pipeline still runs the old package.

## Exact rules

- [flash](../../runpod-usage/concepts/flash.yaml)
