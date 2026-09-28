---
concepts: [cpu-flavor]
---

# Flash — Endpoint API & compute-type reference

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

> **These defaults are flash-SDK defaults, and differ from the Runpod platform defaults**
> (Console / `runpodctl` / API): `idle_timeout` 60s here vs **5s** on the platform,
> `workers` (0, 1) here vs max **3** on the platform, `execution_timeout` unlimited here vs
> **600s** on the platform. When you read a default, note which layer it belongs to.

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
