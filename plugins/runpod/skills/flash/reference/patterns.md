---
concepts: [flash, serverless-handler, network-volume, container-disk, volume-cache, model-store]
---
# Runpod SDK — common patterns

Complete runnable versions live in [`../examples/`](../examples/).

## Choosing a model

The SDK has **no model catalog**: name a HuggingFace repo id in code and the worker downloads
it at runtime, or attach it with `runpod.Model` so the platform stages it on the host first.

- **Start with the smallest model that proves the pipeline** (`gpt2`, `stabilityai/sd-turbo`,
  a 0.5–1B variant). It loads in seconds, so you validate the decorator, dependencies, GPU and
  I/O fast under `rp flash dev`, then change only the id string.
- **Match the model to GPU VRAM** (fp16 ≈ params × 2 bytes + overhead):

  | Model (fp16) | ~VRAM | `gpu=` |
  |---|---|---|
  | ≤3B / SD1.5 / sd-turbo | ≤8 GB | `"AMPERE_16"` or `"4090"` |
  | 7–8B | ~16 GB | `"4090"`, `"L4"`, `"AMPERE_24"` |
  | 13B | ~28 GB | `"5090"` or `"AMPERE_48"` |
  | 70B | ~140 GB | `"H200"` / `"B200"` (or quantize) |

- A hosted model with **no code** is a [Public Endpoint](https://docs.runpod.io/hub/public-endpoints),
  a different product.

## Loading ML models

Model weights are not part of the 1,500 MB build artifact; the artifact is your code plus pip
dependencies. Two things make loading fast and cheap.

**Load once per worker, not per request.** Put the load in an `@app.api` class's
`@runpod.init` method. It runs once when a worker starts, and every route reuses `self`:

```python
import runpod

app = runpod.App("sd")

@app.api(gpu="5090", workers=(0, 3), idle_timeout=300,
         dependencies=["diffusers", "transformers"])
class StableDiffusion:
    @runpod.init
    def load(self):
        import torch
        from diffusers import StableDiffusionPipeline
        self.pipe = StableDiffusionPipeline.from_pretrained(
            "stabilityai/sd-turbo", torch_dtype=torch.float16).to("cuda")

    @runpod.post("/generate")
    async def generate(self, body: dict):
        import base64, io
        image = self.pipe(prompt=body["prompt"], num_inference_steps=1).images[0]
        buf = io.BytesIO(); image.save(buf, format="PNG")
        return {"png_b64": base64.b64encode(buf.getvalue()).decode()}
```

In a queue function, cache in a module global. Deployed workers import the module once, so the
load runs once per worker:

```python
_PIPE = None

@app.queue(gpu="4090", dependencies=["transformers"])
def generate(prompt: str) -> str:
    global _PIPE
    if _PIPE is None:
        from transformers import pipeline
        _PIPE = pipeline("text-generation", model="gpt2", device=0)
    return _PIPE(prompt, max_new_tokens=20)[0]["generated_text"]
```

**Keep the weights close to the worker.** A scaled-to-zero worker re-downloads on every cold
start unless you cache. Pick one:

- **`runpod.Model`** (HuggingFace model, GPU resource). The platform stages the weights on the
  host and holds the worker until they are ready, so the cold request includes that wait. Time
  the whole cold request before deciding it is fast enough.

  ```python
  qwen = runpod.Model("Qwen/Qwen2.5-7B-Instruct")

  @app.queue(gpu="4090", model=qwen, dependencies=["transformers"])
  def chat(prompt: str) -> str:
      from transformers import pipeline
      pipe = pipeline("text-generation", model=str(qwen.path), device=0)
      return pipe(prompt, max_new_tokens=64)[0]["generated_text"]
  ```

- **A `NetworkVolume` mirrored with `VolumeCache`.** A cold worker copies weights an earlier
  worker downloaded onto its local disk and loads from there instead of over the network mount.
  Keep the HF cache on container disk (not under `/runpod-volume`) and wrap the load:

  ```python
  cache = runpod.NetworkVolume("model-cache", size=100)

  @app.api(gpu="5090", mounts={"/runpod-volume": cache}, container_disk_gb=60,
           env={"HF_HUB_CACHE": "/opt/hf-cache"}, dependencies=["transformers"])
  class Chat:
      @runpod.init
      def load(self):
          from runpod.serverless import VolumeCache
          from transformers import pipeline
          with VolumeCache(dirs=["/opt/hf-cache"]):   # hydrate from the volume, then sync back
              self.pipe = pipeline("text-generation", model="Qwen/Qwen2.5-7B-Instruct", device=0)
  ```

  `rp flash deploy` vendors your local `runpod` package into the artifact, so
  `runpod.serverless.VolumeCache` is importable on the worker without listing `runpod` in
  `dependencies`.

  The same code works on a `runpod.GlobalVolume` (GPU resources only): mount it at
  `/runpod-volume` and `VolumeCache` mirrors there. Restores from a global volume measured
  slower than from a network volume before 2.0.1's parallel restore; re-time on your version,
  and prefer a network volume when the endpoint stays in one data center
  ([model-caching](../../runpodctl/reference/model-caching.md#measured-cold-starts)).

**Don't load weights straight off the mount** (`HF_HOME=/runpod-volume/...` or
`from_pretrained("/runpod-volume/model")`). Every read then crosses the network; restoring with
`VolumeCache` and loading from local disk measured faster
([model-caching](../../runpodctl/reference/model-caching.md#measured-cold-starts)).

`VolumeCache` details that bite:
- **Best-effort.** Cache errors are logged and swallowed, and the worker cold-starts normally,
  so a broken cache looks like a slow cold start. Use `VolumeCache(..., best_effort=False)`
  while debugging.
- It never copies symlinks, which the HF cache uses for `snapshots/`. Leave Hub access on
  (don't set `HF_HUB_OFFLINE=1`) so `from_pretrained` can re-link with a metadata call.
- Size the volume for the mirror and `container_disk_gb` for the whole local cache plus
  headroom; the default is 30 GB on GPU.
- Let one worker populate the mirror first. Workers that cold-start together on an empty mirror
  each download and sync a full copy.
- The mirror is keyed by endpoint ID (`namespace` defaults to `RUNPOD_ENDPOINT_ID`). Every dev
  session creates new endpoints, so each session starts from an empty mirror and leaves its copy
  on the volume. Pass a fixed `namespace="qwen-7b"` to share one mirror across dev sessions and
  deploys.

Full behavior: [`concepts/volume-cache.yaml`](../../runpod-usage/concepts/volume-cache.yaml).

## CPU + GPU pipeline

```python
@app.queue(cpu="cpu5c-4-8", dependencies=["pandas"])
def preprocess(rows: list[dict]) -> list[list[float]]:
    import pandas as pd
    return pd.DataFrame(rows).dropna().astype(float).values.tolist()

@app.queue(gpu="AMPERE_80")
def score(matrix: list[list[float]]) -> list[float]:
    import torch
    return torch.tensor(matrix, dtype=torch.float32, device="cuda").mean(dim=1).tolist()

@runpod.local_entrypoint
def main():
    print(score.remote(preprocess.remote([{"a": 1, "b": 3}, {"a": 5, "b": 7}])))
```

Each stage is its own endpoint with its own workers and hardware. A remote function can also
call another resource's `.remote()` directly.

## Parallel execution

```python
jobs = [score.spawn(batch) for batch in batches]     # submit all, don't wait
results = [job.result() for job in jobs]             # collect

# async code
results = await asyncio.gather(*(score.remote.aio(b) for b in batches))
```

## Training jobs as tasks

`@app.task` gets a Pod per call and terminates it when the function returns, which fits
training. Share artifacts through a volume:

```python
ckpts = runpod.NetworkVolume("ckpts", size=50)

@app.task(gpu="H100", gpu_count=2, mounts={"/ckpts": ckpts})
def finetune(steps: int = 1000) -> str:
    ...
    return str(ckpts.path / "adapter")
```

A queue endpoint that mounts the same volume at `/runpod-volume` reads what the task wrote (golden
path 07 shows the volume handoff). Small results can skip the volume: return them from the task
as JSON, as [`train_then_serve.py`](../examples/train_then_serve.py) does. For a long run, `job = finetune.spawn()`
then `await job.wait(timeout=...)`, which terminates the Pod when it finishes or times out.

## Streaming results

```python
@app.queue(cpu="cpu3c-1-2")
def tokens(prompt: str):
    for word in prompt.split():
        yield word

for chunk in tokens.stream("hello streaming world"):
    print(chunk)
```

## Returning binary output

Requests and results go through the job API as JSON, capped at 10 MB. Return images and audio
as base64 (`{"png_b64": ...}`) and decode on the client. For larger outputs, write to a volume
or object storage and return a path or URL.

## Calling from outside Python

Deployed queue resources take their keyword arguments as the job `input`:
`def generate(prompt: str)` takes `{"input": {"prompt": "hi"}}` on `/run` or `/runsync`.
Deployed API routes take the JSON body itself on `https://ENDPOINT_ID.api.runpod.ai/PATH`.
Full examples in [api.md](api.md#raw-http-to-a-deployed-queue-resource).
