---
concepts: [flash, serverless-handler, network-volume, container-disk, volume-cache, model-store]
---
# Flash — Common Patterns

## Choosing a model

Flash has **no model catalog** — name a HuggingFace repo id in code and it downloads to the
worker at runtime (see *Loading ML models* below). Other sources: a custom image's `MODEL_NAME` env
(vLLM etc.), a URL, or your own weights on a NetworkVolume.

- **Start with the smallest model that proves the pipeline** (`gpt2`, `stabilityai/sd-turbo`,
  a 0.5–1B variant) — it provisions in seconds, so you validate the `@Endpoint` wiring, deps,
  GPU, and I/O fast under `flash dev`, then change *only the id string* to the real model.
- **Match the model to GPU VRAM** (fp16 ≈ params × 2 bytes + overhead):

  | Model (fp16) | ~VRAM | `gpu=` |
  |---|---|---|
  | ≤3B / SD1.5 / sd-turbo | ≤8 GB | `GpuGroup.AMPERE_16` or `GpuGroup.ADA_24` |
  | 7–8B | ~16 GB | `GpuGroup.ADA_24` or `GpuGroup.AMPERE_24` |
  | 13B | ~28 GB | `GpuGroup.ADA_32_PRO` or `GpuGroup.AMPERE_48` |
  | 70B | ~140 GB | `GpuGroup.HOPPER_141` / `GpuGroup.BLACKWELL_180` (or quantize) |

- A ready-made hosted model with **no code** is [Runpod Public Endpoints / Hub](https://docs.runpod.io/hub) — a different product, not Flash.

> **Big model? Naming it still works — but mind the re-download.** Model size is not a
> flash limit: naming a large HF repo streams the weights to the worker at runtime. The
> catch is that a scaled-to-zero worker **re-downloads on every cold start**. For a large
> model you call often, cache it so it isn't re-pulled each time — persist to a
> **NetworkVolume** with `VolumeCache` (see *Loading ML models* below), or on the runpodctl/serverless side use
> the **HF model cache** (`--model-reference`, attached after `flash deploy`) or bake it into the image. This is the same
> tradeoff as the delivery-methods table in
> [`runpodctl/reference/model-caching.md`](../../runpodctl/reference/model-caching.md): easy
> streaming vs. faster/cheaper cold starts for reused weights — not a contradiction.

## Loading ML models (warm workers)

Model **weights are not part of the 1.5GB build artifact** — that cap is your code + pip
deps (torch is auto-excluded). Weights download on the worker at runtime (HuggingFace,
etc.), so **model size is not a Flash limit**. Two things make this fast and cheap:

- **Load once per worker, not per request** — use a *class* `@Endpoint`: `__init__` loads
  the model into VRAM once when the worker starts; methods handle requests and reuse it.
- **Keep the weights close so a cold worker doesn't re-pull them from the Hub.** Two ways:
  - **Model Store**, when the model is on HuggingFace and the endpoint is GPU: no volume and
    no cache code. Set `env={"HF_HUB_CACHE": "/runpod-volume/huggingface-cache/hub"}` on the
    `@Endpoint`, then after `flash deploy` attach the model with
    `runpodctl serverless update <endpoint-id> --model-reference https://huggingface.co/<org>/<model>:main`.
    Later `flash deploy` runs keep the reference. Worker start waits until a host holds the
    model, so time the whole cold request; if that wait is too long, use the volume below.
  - **A NetworkVolume mirrored with `VolumeCache`**: a cold worker copies the weights an
    earlier worker downloaded onto its local disk and loads from there, not over the network
    mount. Keep the HF cache on container disk (not under `/runpod-volume`) and wrap the load
    in `VolumeCache` from the Runpod Python SDK (`runpod>=1.12.0`). It hydrates the local cache
    from the volume's mirror, then syncs new files back:

```python
from runpod_flash import Endpoint, GpuType, DataCenter, NetworkVolume

vol = NetworkVolume(name="model-cache", size=100, datacenter=DataCenter.US_GA_2)

@Endpoint(
    name="sd",
    gpu=GpuType.NVIDIA_GEFORCE_RTX_5090,
    workers=(0, 3),
    idle_timeout=300,                                # keep workers warm between calls
    datacenter=DataCenter.US_GA_2,
    volume=vol,
    env={"HF_HUB_CACHE": "/opt/hf-cache"},           # local container disk, mirrored by VolumeCache
    dependencies=["torch", "diffusers", "transformers", "accelerate", "runpod>=1.12.0"],
)
class SD:
    def __init__(self):                              # runs ONCE per worker
        import torch
        from diffusers import StableDiffusionPipeline
        from runpod.serverless import VolumeCache

        with VolumeCache(dirs=["/opt/hf-cache"]):    # hydrate from the volume, then sync back
            self.pipe = StableDiffusionPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5", torch_dtype=torch.float16
            ).to("cuda")

    async def generate(self, prompt: str) -> dict:   # per request, reuses self.pipe
        image = self.pipe(prompt=prompt).images[0]
        image.save("/runpod-volume/out.png")         # /runpod-volume/ persists; elsewhere is wiped
        return {"saved": "/runpod-volume/out.png"}
```

- **Gated** models: pass `env={"HF_TOKEN": "..."}`.
- **`VolumeCache` is best-effort.** Any cache error is logged and swallowed, and the worker
  does a normal cold start, so a broken cache looks like a slow cold start. Pass
  `VolumeCache(..., best_effort=False)` while debugging. It never copies symlinks, which the HF
  cache uses for `snapshots/`. Leave Hub access on (don't set `HF_HUB_OFFLINE=1`) so
  `from_pretrained` can re-link the snapshot with a metadata call. Size the volume for the
  mirror (`/runpod-volume/.cache/<endpoint id>`), and size the **container disk** for the whole
  local cache plus headroom. It defaults to 64 GB, so a 70B fp16 model (~140 GB) needs
  `template=PodTemplate(containerDiskInGb=200)` on the `@Endpoint`. Let one worker populate it first: workers
  that cold-start together on an empty mirror each download and sync a full copy. Full
  behavior: [`concepts/volume-cache.yaml`](../../runpod-usage/concepts/volume-cache.yaml).
- `workers=(1, n)` keeps one worker warm (no cold start on the first request); `(0, n)` scales to zero and cold-starts after `idle_timeout`.
- The class form is the cleanest way to load once. In function-form `@Endpoint` the same effect needs the module-global cache trick (see Gotcha #11 in the skill); the class form is preferred for real inference.

## CPU + GPU Pipeline

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

## Parallel Execution

```python
import asyncio
results = await asyncio.gather(compute(a), compute(b), compute(c))
```
