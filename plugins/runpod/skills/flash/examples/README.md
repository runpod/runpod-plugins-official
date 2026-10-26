# Runpod SDK app examples

Single-file apps for the Runpod Python SDK (`runpod` 2.0). Each file carries a
`@runpod.local_entrypoint` that asserts its own result, so a passing run proves it works.

```bash
rp flash dev queue_gpu.py --once        # temporary endpoints, run main() once, clean up
rp flash deploy queue_gpu.py            # persistent endpoints
rp flash deploy queue_gpu.py --build-only   # offline check: discovery + dependency resolution
```

Live checks ran on `runpod` 2.0.0rc1, before the GPU-pinning and build changes in 2.0.1;
`queue_gpu.py` (float dtype) and `cpu_gpu_pipeline.py` (parallel CPU stage) changed slightly
since. Re-run them on 2.0.1.

| File | Shows | Live check (`runpod` 2.0.0rc1, `--once`) |
|---|---|---|
| [`queue_gpu.py`](queue_gpu.py) | `@app.queue` on a GPU list with `workers=(0, 5)` | ✅ 2026-10-16 |
| [`api_model_service.py`](api_model_service.py) | `@app.api` class, model loaded once in `@runpod.init`, `POST /generate` + `GET /health` | ✅ 2026-10-16 |
| [`cpu_gpu_pipeline.py`](cpu_gpu_pipeline.py) | CPU stage feeding a GPU stage, `.spawn()` fan-out | ✅ 2026-10-16 |
| [`train_then_serve.py`](train_then_serve.py) | `@app.task` trains on a GPU Pod, a queue endpoint serves the returned weights | ✅ 2026-10-16 |
| [`call_deployed.py`](call_deployed.py) | `runpod.Queue`, `runpod.Api` and `runpod.Endpoint` from plain Python | ✅ 2026-10-16 (against both apps deployed) |

Cost and cleanup: dev sessions delete their endpoints on exit, and task Pods terminate when the
task returns. Remove deployed apps with `rp flash app delete APP --yes`. For a checkpoint shared
through a network volume, see [golden path 07](../../runpod/golden-paths/07-network-volume-handoff.md).

The upstream SDK ships more examples in
[runpod-python `examples/apps`](https://github.com/runpod/runpod-python/tree/main/examples/apps).
