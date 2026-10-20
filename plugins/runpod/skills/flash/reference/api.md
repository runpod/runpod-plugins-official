---
concepts: [flash, cpu-flavor, gpu-pool, network-volume, model-store, runpod-secret]
---

# Runpod SDK — app API & compute reference

Everything is importable from `runpod` (`runpod.App`, `runpod.NetworkVolume`, ...).

## App and decorators

```python
import runpod

app = runpod.App("my-app")            # App(name, *, env="default")
```

| Decorator | Wraps | Creates |
|---|---|---|
| `@app.queue(...)` | a function (sync, async, or generator) | queue-based Serverless endpoint |
| `@app.api(...)` | a class with `@runpod.get` / `@runpod.post` methods and an optional `@runpod.init` setup method | load-balanced Serverless endpoint |
| `@app.task(...)` | a function | one Pod per call, terminated when the function returns |
| `@runpod.local_entrypoint` | your `main()` | the code `rp flash dev` runs on your machine |

### Parameters

| Parameter | Default | Queue | API | Task | Notes |
|---|---|---|---|---|---|
| `name` | function or class name | ✓ | ✓ | ✓ | endpoint name inside the app |
| `gpu` | any GPU | ✓ | ✓ | ✓ | `"4090"`, `"H100"`, a `GpuGroup`, a `GpuType`, or a list of acceptable ones |
| `cpu` | `None` | ✓ | ✓ | ✓ | a CPU flavor id such as `"cpu5c-4-8"`; exclusive with `gpu` |
| `gpu_count` | `1` | ✓ | ✓ | ✓ | GPUs per worker or Pod |
| `workers` | `(0, 3)` | ✓ | ✓ | | `int` n means `(0, n)` |
| `idle_timeout` | `60` | ✓ | ✓ | | seconds before an idle worker scales down |
| `max_concurrency` | `1` | ✓ | | | concurrent jobs per worker |
| `dependencies` | `None` | ✓ | ✓ | ✓ | pip requirements, installed before your code runs |
| `system_dependencies` | `None` | ✓ | ✓ | ✓ | apt packages; they add to cold start |
| `mounts` | `None` | ✓ | ✓ | ✓ | `{"/runpod-volume": vol}`; see *Storage* |
| `env` | `None` | ✓ | ✓ | ✓ | plain values or `runpod.Secret("name")` |
| `datacenter` | any | ✓ | ✓ | ✓ | a data center id or a list, such as `"US-CA-2"` |
| `image` | Runpod runtime image | ✓ | ✓ | ✓ | any image with Python 3 |
| `registry_auth` | `None` | ✓ | ✓ | ✓ | name of credentials saved with `rp registry add` |
| `model` | `None` | ✓ | ✓ | | a `runpod.Model`, staged on the host before the worker starts |
| `execution_timeout_ms` | `0` (no limit) | ✓ | ✓ | | per-job limit |
| `flashboot` | `True` | ✓ | ✓ | | |
| `scaler_type`, `scaler_value` | by resource type, `4` | ✓ | ✓ | | |
| `min_cuda_version` | `None` | ✓ | ✓ | ✓ | such as `"12.8"` |
| `accelerate_downloads` | `True` | ✓ | ✓ | ✓ | |
| `container_disk_gb` | 30 (GPU), 10 (CPU) | ✓ | ✓ | ✓ | size it for local model caches |

> **These are SDK defaults, not platform defaults.** REST v2, the console and runpodctl each
> use their own values for `workers`, idle timeout and execution timeout. Set the ones that
> matter explicitly.

## Calling resources

On a queue or task handle:

| Call | Does |
|---|---|
| `fn.remote(*args, **kwargs)` | runs remotely, blocks for the result; on a queue, stops waiting after 300 s with `TimeoutError` |
| `await fn.remote.aio(...)` | async form |
| `fn.spawn(...)` | submits, returns a job immediately |
| `fn.stream(...)` | yields chunks from a generator function |
| `fn.local(...)` | runs the body in the local process |
| `fn.with_options(webhook=..., execution_timeout=..., ttl=..., low_priority=...)` | a copy of the handle with per-job options |

Queue jobs from `.spawn()`: `job.id`, `job.status()`, `job.result(timeout=...)`, `job.stream()`,
`job.cancel()`, `job.retry()`; each has an `.aio` async form.

Task jobs from `.spawn()` own a Pod: `await job.wait(timeout=...)` returns the result and then
terminates the Pod (also on timeout or failure); `await job.cancel()` abandons it and
terminates the Pod. If the SDK cannot delete the Pod it warns and keeps the id in `job.pod_id`.

On an `@app.api` class: `MyApi.post("/path", body)` / `MyApi.get("/path")`, with
`await MyApi.post.aio(...)` as the async form.

### Deployed resources from other code

```python
import runpod

transcribe = runpod.Queue(app="media", name="transcribe")       # env="default" unless given
text = transcribe.remote(audio_url="https://example.com/a.mp3")  # keyword arguments only
job = transcribe.spawn(audio_url="...")

inference = runpod.Api(app="media", name="inference")
resp = inference.post("/generate", {"prompt": "hi"})
```

`Queue(..., id="ENDPOINT_ID")` and `Api(..., id=...)` target an endpoint by id instead of name.

### Any queue endpoint by id

```python
ep = runpod.Endpoint("ENDPOINT_ID")             # also works for endpoints the SDK did not create
out = ep.run_sync({"prompt": "hello"}, timeout=120)   # sends {"input": {...}}
job = ep.run({"prompt": "hello"})
job.status(); job.output(timeout=300); job.cancel()
ep.health(); ep.purge_queue()
```

### Raw HTTP to a deployed queue resource

A deployed queue function reads the job's `input` as its keyword arguments, so a function
`def transcribe(audio_url: str)` takes:

```bash
curl -s -X POST "https://api.runpod.ai/v2/$ENDPOINT_ID/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input": {"audio_url": "https://example.com/a.mp3"}}'
```

A function with no parameters still needs a non-empty `input`; the SDK sends
`{"input": {"__empty": true}}`.

### Raw HTTP to a deployed API resource

A POST route receives the request's JSON body as its one argument, and a GET route takes none.
For `@runpod.post("/generate") async def generate(self, body: dict)`:

```bash
curl -s -X POST "https://$ENDPOINT_ID.api.runpod.ai/generate" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "hi"}'
```

The body is the object itself, with no wrapper key.

## Storage

```python
models = runpod.NetworkVolume("models", size=100, datacenter="US-CA-2")  # created on first use
shared = runpod.GlobalVolume("shared")                                   # not tied to a data center
existing = runpod.NetworkVolume("vol_id_or_name", create=False)          # must already exist
```

- Queue and API resources mount **one** volume, at `/runpod-volume`:
  `mounts={"/runpod-volume": models}`.
- Tasks mount up to one network volume and one global volume, at distinct paths.
- Global volumes need GPU compute.
- A new network volume is placed in a data center that has network storage and stock for every
  resource sharing it; resources using it are scheduled in that data center.
- Read `models.path` **inside** the remote function. Volumes are not mounted locally.
- Undeploying an app or ending a dev session leaves its volumes in place, and they keep billing.

## Models and secrets

```python
llama = runpod.Model("meta-llama/Llama-3.1-8B-Instruct")       # "owner/name" or "owner/name:revision"

@app.queue(gpu="H100", model=llama, env={"HF_TOKEN": runpod.Secret("hf-token")})
def chat(prompt: str):
    import vllm
    llm = vllm.LLM(model=str(llama.path))   # staged weights; transformers/vllm also find the HF cache
    ...
```

The platform stages the weights on the host before the worker starts, so a cold start does
not download them. Gated models need `HF_TOKEN` on the same resource. Create the secret with
`rp secret add hf-token`.

## GPU and CPU names

`gpu=` accepts:

- **A fragment of the device name**: `"4090"`, `"H100"`, `"B200"`, `"L4"`. Every device whose
  name contains it matches, so `"H100"` covers the H100 variants.
- **A `runpod.GpuGroup` pool**: `ANY`, `AMPERE_16`, `AMPERE_24`, `AMPERE_48`, `AMPERE_80`,
  `ADA_24`, `ADA_32_PRO`, `ADA_48_PRO`, `ADA_80_PRO`, `HOPPER_141`, `BLACKWELL_96`,
  `BLACKWELL_180`. The VRAM tiers match the GPU pool table in
  [gpu-pool](../../runpod-usage/concepts/gpu-pool.yaml).
- **A `runpod.GpuType` member** for an exact model, such as `GpuType.NVIDIA_GEFORCE_RTX_4090`.
- **A list** of any of these. Automatic switching between listed GPUs needs a max of at least 5
  workers.

Device names pin those exact devices. Endpoints select GPUs by pool, so the SDK selects each
device's pool and excludes the pool's other devices, reading pool membership from the live GPU
catalog: `gpu=["4090", "L4", "A5000"]` deploys as `ADA_24,AMPERE_24,-NVIDIA GeForce RTX 3090,
-NVIDIA RTX PRO 6000 Blackwell Server Edition MIG 1g.24gb`. A pool id allows every device in
the pool, including MIG slices the platform adds to it.

`cpu=` takes a flavor id: `cpu3g-{1-4,2-8,4-16,8-32}` (general), `cpu3c-{1-2,2-4,4-8,8-16}`
(compute), `cpu5c-{1-2,2-4,4-8,8-16}` (compute, 5th gen), where the numbers are vCPUs and GB of
RAM. `runpod.CpuInstanceType` holds the same values.

## Credentials on workers

A worker that calls another resource (`.remote()`, `.spawn()`, a `runpod.Queue`/`Api` client)
needs the account API key, so deploy and dev add `RUNPOD_API_KEY` to the endpoints whose code
can reach one. The build reads the resource's own body and the module-level helpers it calls.
Code it cannot follow (a local helper module, a nested function) gets the key too, so a caller
never goes without it. Resources that make no such call run without the key.

## Exact rules

- [flash](../../runpod-usage/concepts/flash.yaml)
- [cpu-flavor](../../runpod-usage/concepts/cpu-flavor.yaml)
- [model-store](../../runpod-usage/concepts/model-store.yaml)
