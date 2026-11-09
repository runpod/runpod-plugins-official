---
concepts: [serverless-endpoint, worker, container-image, exposed-port, endpoint-autoscaling]
---

# vLLM on a load-balancing endpoint

A load-balancing endpoint sends HTTP requests straight to the worker's own server, so the stock `vllm/vllm-openai` image serves the OpenAI API with no handler in between. Use it when the model needs a vLLM version that the Hub worker-vllm release does not have, or when the user wants direct HTTP and streaming without a queue.

## The contract

A worker counts as ready only when it answers the health check. vLLM listens on port 8000 and answers `GET /health` once the engine is up, so set all three:

| Env | Value | Why |
|---|---|---|
| `PORT` | `8000` | the port requests are routed to |
| `PORT_HEALTH` | `8000` | the port the health check polls |
| `HEALTH_CHECK_PATH` | `/health` | the path vLLM answers; set it explicitly whatever image you use |

The generic load-balancer rules (defaults, immutable type, no queue) are in [runpod-serverless-deploy's scenarios](../../runpod-serverless-deploy/reference/scenarios.md#load-balancer-endpoint). The endpoint read returns the exact health URL it polls in `requestUrls.health`.

**Auth.** The gateway checks the Runpod API key on every request (a request without it gets `401`). Do not also give vLLM an `--api-key` or `VLLM_API_KEY`: the client's one `Authorization` header carries the Runpod key, so vLLM would reject every request that the gateway let through.

## Create

```json
{
  "name": "vllm-qwen3-8b-lb",
  "type": "LOAD_BALANCER",
  "image": "vllm/vllm-openai:v0.32.0",
  "args": "Qwen/Qwen3-8B --max-model-len 8192 --gpu-memory-utilization 0.90 --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3 --enable-prefix-caching --port 8000",
  "env": { "PORT": "8000", "PORT_HEALTH": "8000", "HEALTH_CHECK_PATH": "/health" },
  "ports": ["8000/http"],
  "disk": 50,
  "gpu": { "pools": ["AMPERE_24"], "count": 1, "minCudaVersion": "13.0" },
  "workers": { "min": 1, "max": 1, "idleTimeout": 60 },
  "scaling": { "type": "REQUEST_COUNT", "requestCount": 4 },
  "flashboot": "FLASHBOOT",
  "timeout": 600000
}
```

- `args` are the `vllm serve` arguments, as on a Pod. `--port 8000` matches `PORT`.
- `disk`: the weights download to the container disk; size it for the weights plus about 30 GB.
- `workers.min: 1` makes the first worker start now, so the boot can be watched before traffic arrives. Set it back to 0 after the test unless the user wants a warm worker (it bills around the clock).
- Multi-GPU workers: set `gpu.count` and `--tensor-parallel-size` to the same value, and add `NCCL_NVLS_ENABLE=0` to `env` if the boot dies in NCCL init ([boot-log-triage.md](boot-log-triage.md)).
- Gated weights: `HF_TOKEN` in `env`.

## Call it

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://<endpoint-id>.api.runpod.ai/v1",
                api_key=os.environ["RUNPOD_API_KEY"])
```

Then run [`scripts/test_endpoint.py`](../scripts/test_endpoint.py) with `--wait-for-ready`.

## Failure modes

1. **Health check never passes.** Wrong `PORT`, `PORT_HEALTH` or `HEALTH_CHECK_PATH`, or the engine never finishes booting. Runpod retries an unhealthy worker, and an endpoint that keeps producing unhealthy workers is scaled down automatically ([`worker.unhealthy-scale-down`](../../runpod-usage/concepts/worker.yaml)). A boot that never passes the health check therefore never serves. Read `stream-worker-logs`: a vLLM log that reaches `Application startup complete` means the health settings are wrong; one that stops earlier is a boot failure.
2. **Boot too slow.** Large models spend minutes in download and `torch.compile`. In order of effort: add `--enforce-eager` (no compile and no CUDA graphs: faster boot, slower first requests); keep the weights and `VLLM_CACHE_ROOT` on a network volume (`HF_HOME=/runpod-volume/hf`, `VLLM_CACHE_ROOT=/runpod-volume/vllm-cache`) so later boots are warm; or serve from a Pod, which has no health window.
3. **More workers listed than `workers.max`, and transient 502s.** A test endpoint with `workers.max` 1 listed 3 workers (1 `RUNNING`, 2 `INITIALIZING`). A request can also reach a worker that is still starting. Clients retry; read `list-endpoint-workers` before you treat a single 5xx as a model failure, and after a test.
4. **Config change during a test.** An image, `args` or env change cuts a new release and replaces the workers with cold ones. Worker counts, scaling and timeout apply without a restart.

## Exact rules

- [serverless-endpoint](../../runpod-usage/concepts/serverless-endpoint.yaml) · [worker](../../runpod-usage/concepts/worker.yaml) · [endpoint-autoscaling](../../runpod-usage/concepts/endpoint-autoscaling.yaml)
