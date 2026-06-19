---
name: flash
description: runpod-flash SDK and CLI for deploying AI workloads on Runpod serverless GPUs/CPUs.
user-invocable: true
---

# Runpod Flash

Write code locally, test with `flash dev` (dev server at localhost:8888), and flash automatically provisions and deploys to remote GPUs/CPUs in the cloud. `Endpoint` handles everything.

## Setup

```bash
# install the CLI — requires Python 3.10-3.13
uv tool install runpod-flash
pip install runpod-flash

# auth option 1: browser-based login (saves token locally)
flash login
flash login --no-open                    # headless: print URL instead of opening a browser
flash login --timeout 300                # max seconds to wait for browser auth (default 600)

# auth option 2: API key via environment variable
export RUNPOD_API_KEY=your_key

flash init my-project                    # scaffold a new project in ./my-project (writes AGENTS.md + CLAUDE.md)
flash init .                             # scaffold in the current directory
flash init my-project --force            # overwrite existing files (-f)
flash update                             # update the CLI to the latest version
flash update --version 1.16.0            # pin a specific version (-V also works)
```

`flash init` writes `AGENTS.md` (+ a `CLAUDE.md` symlink). To add them to an existing project: `python -c "from runpod_flash.rules import install_agent_files; from pathlib import Path; install_agent_files(Path.cwd())"`.

## CLI

`flash dev` is the canonical dev-server command (`flash run` still works as a hidden alias).

```bash
flash dev                                # start local dev server at localhost:8888
flash dev --auto-provision               # same, but pre-provision endpoints (no cold start)
flash dev --port 9000 --host 0.0.0.0     # custom port/host; --reload/--no-reload toggles autoreload
flash deploy                             # build + deploy (auto-selects env if only one)
flash deploy --env staging               # build + deploy to "staging" environment
flash deploy --app my-app --env prod     # deploy a specific app to an environment
flash deploy --preview                   # build + launch local preview in Docker
flash deploy --no-deps --python-version 3.11  # build flags below also apply to deploy
flash env list                           # list deployment environments
flash env create staging                 # create "staging" environment
flash env get staging                    # show environment details + resources
flash env delete staging                 # delete environment + tear down resources
flash app list                           # list flash apps in your account
flash app create my-app                  # create a flash app
flash app get my-app                     # show an app's environments + builds
flash app delete my-app                  # delete an app and all its resources
flash undeploy list                      # list all active endpoints
flash undeploy my-endpoint               # remove a specific endpoint
flash undeploy --all                     # remove all endpoints (--interactive/-i to pick, --force/-f to skip prompts)
flash undeploy --cleanup-stale           # remove endpoints whose code no longer exists locally

# `flash build` is build-only (no deploy) — mainly for debugging the artifact; `flash deploy` builds for you
flash build                              # package the artifact without deploying (1500MB limit; torch auto-excluded)
flash build --no-deps                    # build flags: --no-deps, --exclude pkg1,pkg2, --output name.tar.gz, --python-version 3.11
```

## Endpoint: Three Modes

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

## Endpoint Constructor

```python
Endpoint(
    name="endpoint-name",                  # required (unless id= set)
    id=None,                               # connect to existing endpoint
    gpu=GpuGroup.AMPERE_80,               # GpuGroup tier, GpuType model, or list of either (default: GpuGroup.ANY)
    cpu=CpuInstanceType.CPU5C_4_8,        # CPU type (mutually exclusive with gpu)
    workers=5,                             # shorthand for (0, 5)
    workers=(1, 5),                        # explicit (min, max)
    max_concurrency=1,                     # concurrent requests per worker (default 1)
    idle_timeout=60,                       # seconds before scale-down (default: 60)
    dependencies=["torch"],                # pip packages for remote exec
    system_dependencies=["ffmpeg"],        # apt-get packages
    image="org/image:tag",                 # pre-built Docker image (client mode)
    env={"KEY": "val"},                    # environment variables
    volume=NetworkVolume(...),             # persistent storage
    datacenter=DataCenter.US_CA_2,         # DataCenter | list | str (default: None)
    gpu_count=1,                           # GPUs per worker
    template=PodTemplate(containerDiskInGb=100),
    flashboot=True,                        # fast cold starts
    accelerate_downloads=True,             # speed up model/file downloads (default True)
    min_cuda_version=CudaVersion.V12_8,    # minimum CUDA version (default 12.8)
    scaler_type=ServerlessScalerType.QUEUE_DELAY,  # default unset; or REQUEST_COUNT
    scaler_value=4,                        # scaler threshold (default 4)
    execution_timeout_ms=0,                # max execution time (0 = unlimited)
)
```

- `gpu=` and `cpu=` are mutually exclusive
- `gpu=` accepts a `GpuGroup`, a `GpuType`, or a list of either (see GPU Types below)
- `workers=5` means `(0, 5)`. Default is `(0, 1)`
- `max_concurrency` -- requests handled concurrently per worker (default 1). Raise it for I/O-bound LB routes so one worker serves multiple requests
- `idle_timeout` default is **60 seconds**
- `flashboot=True` (default) -- enables fast cold starts via snapshot restore
- `gpu_count` -- GPUs per worker (default 1), use >1 for multi-GPU models
- `datacenter` -- a `DataCenter` enum, list, or string; defaults to `None` (unset)
- `scaler_type` -- defaults to `QUEUE_DELAY` for queue-based endpoints and `REQUEST_COUNT` for load-balanced endpoints; pass `ServerlessScalerType.QUEUE_DELAY` or `REQUEST_COUNT` to override
- `DataCenter`, `CudaVersion`, and `ServerlessScalerType` are importable from `runpod_flash`

### NetworkVolume

```python
NetworkVolume(name="my-vol", size=100)  # size in GB, default 100
```

### PodTemplate

```python
PodTemplate(
    containerDiskInGb=64,    # container disk size (default 64)
    dockerArgs="",           # extra docker arguments
    ports="",                # exposed ports
    startScript="",          # script to run on start
)
```

## EndpointJob

Returned by `ep.run()` and `ep.runsync()` in client mode.

```python
job = await ep.run({"data": [1, 2, 3]})
await job.wait(timeout=120)        # poll until done
print(job.id, job.output, job.error, job.done)
await job.cancel()
```

## GPU Types

`gpu=` accepts a `GpuGroup` (a supply pool by VRAM tier), a `GpuType` (a pinned GPU model), or a list of either. `GpuGroup` picks the cheapest available GPU within a tier; `GpuType` pins a specific model.

### GpuGroup (supply pool)

| Enum | GPU | VRAM |
|------|-----|------|
| `ANY` | any | varies |
| `AMPERE_16` | RTX A4000 / A4500 / RTX 4000 Ada / RTX 2000 Ada | 16GB |
| `AMPERE_24` | RTX A5000 / L4 / RTX 3090 | 24GB |
| `AMPERE_48` | A40 / RTX A6000 | 48GB |
| `AMPERE_80` | A100 (PCIe / SXM4) | 80GB |
| `ADA_24` | RTX 4090 | 24GB |
| `ADA_32_PRO` | RTX 5090 | 32GB |
| `ADA_48_PRO` | RTX 6000 Ada / L40 / L40S | 48GB |
| `ADA_80_PRO` | H100 PCIe (80GB) / H100 HBM3 (80GB) / H100 NVL (94GB) | 80GB+ |
| `HOPPER_141` | H200 | 141GB |
| `BLACKWELL_96` | RTX PRO 6000 Blackwell | 96GB |
| `BLACKWELL_180` | B200 | 180GB |

### GpuType (pinned model)

Pin an exact GPU model. Members include `NVIDIA_GEFORCE_RTX_4090`, `NVIDIA_GEFORCE_RTX_5090`, `NVIDIA_RTX_6000_ADA_GENERATION`, `NVIDIA_H100_80GB_HBM3`, `NVIDIA_A100_80GB_PCIe`, `NVIDIA_A100_SXM4_80GB`, `NVIDIA_H200`, `NVIDIA_B200`, the `NVIDIA_RTX_PRO_6000_BLACKWELL_*` editions (Server / Workstation / Max-Q), and the Ampere/Ada RTX A-series models (`NVIDIA_RTX_A4000`, `A4500`, `A5000`, `A6000`, `NVIDIA_L4`, `NVIDIA_A40`, `NVIDIA_GEFORCE_RTX_3090`, `NVIDIA_RTX_4000_ADA_GENERATION`, `NVIDIA_RTX_2000_ADA_GENERATION`).

```python
from runpod_flash import Endpoint, GpuType

@Endpoint(name="pinned", gpu=GpuType.NVIDIA_GEFORCE_RTX_4090, dependencies=["torch"])
async def report_gpu(data):
    import torch
    return {"gpu": torch.cuda.get_device_name(0)}
```

## CPU Types (CpuInstanceType)

| Enum | vCPU | RAM | Max Disk | Type |
|------|------|-----|----------|------|
| `CPU3G_1_4` | 1 | 4GB | 10GB | General |
| `CPU3G_2_8` | 2 | 8GB | 20GB | General |
| `CPU3G_4_16` | 4 | 16GB | 40GB | General |
| `CPU3G_8_32` | 8 | 32GB | 80GB | General |
| `CPU3C_1_2` | 1 | 2GB | 10GB | Compute |
| `CPU3C_2_4` | 2 | 4GB | 20GB | Compute |
| `CPU3C_4_8` | 4 | 8GB | 40GB | Compute |
| `CPU3C_8_16` | 8 | 16GB | 80GB | Compute |
| `CPU5C_1_2` | 1 | 2GB | 15GB | Compute (5th gen) |
| `CPU5C_2_4` | 2 | 4GB | 30GB | Compute (5th gen) |
| `CPU5C_4_8` | 4 | 8GB | 60GB | Compute (5th gen) |
| `CPU5C_8_16` | 8 | 16GB | 120GB | Compute (5th gen) |

```python
from runpod_flash import Endpoint, CpuInstanceType

@Endpoint(name="cpu-work", cpu=CpuInstanceType.CPU5C_4_8, workers=5, dependencies=["pandas"])
async def process(data):
    import pandas as pd
    return pd.DataFrame(data).describe().to_dict()
```

## Common Patterns

### CPU + GPU Pipeline

```python
from runpod_flash import Endpoint, GpuGroup, CpuInstanceType

@Endpoint(name="preprocess", cpu=CpuInstanceType.CPU5C_4_8, workers=5, dependencies=["pandas"])
async def preprocess(raw):
    import pandas as pd
    return pd.DataFrame(raw).to_dict("records")

@Endpoint(name="infer", gpu=GpuGroup.AMPERE_80, workers=5, dependencies=["torch"])
async def infer(clean):
    import torch
    t = torch.tensor([[v for v in r.values()] for r in clean], device="cuda")
    return {"predictions": t.mean(dim=1).tolist()}

async def pipeline(data):
    return await infer(await preprocess(data))
```

### Parallel Execution

```python
import asyncio
results = await asyncio.gather(compute(a), compute(b), compute(c))
```

## Gotchas

1. **Imports outside function** -- most common error. Everything inside the decorated function.
2. **Forgetting await** -- all decorated functions and client methods need `await`.
3. **Missing dependencies** -- must list in `dependencies=[]`.
4. **gpu/cpu are exclusive** -- pick one per Endpoint.
5. **idle_timeout is seconds** -- default 60s, not minutes.
6. **10MB payload limit** -- pass URLs, not large objects.
7. **Client vs decorator** -- `image=`/`id=` = client. Otherwise = decorator.
8. **Auto GPU switching requires workers >= 5** -- pass a list of GPU types (e.g. `gpu=[GpuGroup.ADA_24, GpuGroup.AMPERE_80]`) and set `workers=5` or higher. The platform only auto-switches GPU types based on supply when max workers is at least 5.
9. **`runsync` timeout is 60s** -- cold starts can exceed 60s. Use `ep.runsync(data, timeout=120)` for first requests or use `ep.run()` + `job.wait()` instead.

## Resources

- Flash source: https://github.com/runpod/flash
- Runnable examples: https://github.com/runpod/flash-examples
- Docs: https://docs.runpod.io
