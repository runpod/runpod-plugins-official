# Runpod SDK app examples

Single-file apps for the Runpod Python SDK (`runpod` 2.0). Each file carries a
`@runpod.local_entrypoint` that asserts its own result, so a passing run proves it works.

```bash
rp flash dev queue_gpu.py --once        # temporary endpoints, run main() once, clean up
rp flash deploy queue_gpu.py            # persistent endpoints
rp flash deploy queue_gpu.py --build-only   # offline check: discovery + dependency resolution
```

| File | Shows |
|---|---|
| [`queue_gpu.py`](queue_gpu.py) | `@app.queue` on a GPU list with `workers=(0, 5)` |
| [`api_model_service.py`](api_model_service.py) | `@app.api` class, model loaded once in `@runpod.init`, `POST /generate` + `GET /health` |
| [`cpu_gpu_pipeline.py`](cpu_gpu_pipeline.py) | CPU stage feeding a GPU stage, `.spawn()` fan-out |
| [`train_then_serve.py`](train_then_serve.py) | `@app.task` writes a checkpoint to a `NetworkVolume`, a queue endpoint reads it |
| [`call_deployed.py`](call_deployed.py) | `runpod.Queue`, `runpod.Api` and `runpod.Endpoint` from plain Python |

Cost and cleanup: dev sessions delete their endpoints on exit. `train_then_serve.py` creates
the `train-serve-ckpts` network volume, which stays and bills until you delete it. Remove
deployed apps with `rp flash app delete APP --yes`.

The upstream SDK ships more examples in
[runpod-python `examples/apps`](https://github.com/runpod/runpod-python/tree/main/examples/apps).
