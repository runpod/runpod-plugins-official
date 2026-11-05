# Runpod SDK app examples

Single-file apps for the Runpod Python SDK (`runpod` 2.0). Each file carries a
`@runpod.local_entrypoint` that asserts its own result, so a passing run proves it works.

```bash
rp flash dev queue_gpu.py --once        # temporary endpoints, run main() once, clean up
rp flash deploy queue_gpu.py            # persistent endpoints
rp flash deploy queue_gpu.py --build-only   # offline check: discovery + dependency resolution
```

Live checks ran with `rp flash dev --once` on `runpod` 2.1.0 (2026-11-04) unless noted.

| File | Shows | Live check |
|---|---|---|
| [`queue_gpu.py`](queue_gpu.py) | `@app.queue` on a GPU list with `workers=(0, 5)` | ✅ 2.1.0 |
| [`api_model_service.py`](api_model_service.py) | `@app.api` class, model loaded once in `@runpod.init`, `POST /generate` + `GET /health` | ✅ 2.1.0 |
| [`cpu_gpu_pipeline.py`](cpu_gpu_pipeline.py) | CPU stage feeding a GPU stage, `.spawn()` fan-out | ✅ 2.1.0 |
| [`train_then_serve.py`](train_then_serve.py) | `@app.task` trains on a GPU Pod, a queue endpoint serves the returned weights | ✅ 2.0.0rc1 (2026-10-16); the 2.1.0 run found no Pod stock for any listed GPU |
| [`call_deployed.py`](call_deployed.py) | `runpod.Queue`, `runpod.Api` and `runpod.Endpoint` from plain Python | ✅ 2.1.0, against `queue_gpu.py` and `api_model_service.py` deployed |

Cost and cleanup: dev sessions delete their endpoints on exit, and task Pods terminate when the
task returns. Remove deployed apps with `rp flash app delete APP --yes`. For a checkpoint shared
through a network volume, see [golden path 07](../../runpod/golden-paths/07-network-volume-handoff.md).

The upstream SDK ships more examples in
[runpod-python `examples/apps`](https://github.com/runpod/runpod-python/tree/main/examples/apps).
