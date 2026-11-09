---
lanes: [runpod-mcp]
mcp: partial
concepts: [pod, serverless-endpoint, container-image, exposed-port, gpu-availability, worker, hub-repo]
status: live-verified
verified: "2026-11-06"
evals: [runpod-vllm/evals/pod-api-key, runpod-vllm/evals/lb-endpoint-contract, runpod-vllm/evals/pick-the-product]
---

# Golden path 27 — serve a model with vLLM: Pod first, then a load-balancing endpoint

> **Status:** live-verified 2026-11-06 — `vllm/vllm-openai:v0.32.0` with `Qwen/Qwen3-8B`, end to end on the Runpod MCP tools plus a local Python client (`test_endpoint.py`); `test_endpoint.py` passed 5/5 on the Pod, the load-balancing endpoint and a Hub worker-vllm queue endpoint. **Evals:** [pod-api-key](../../runpod-vllm/evals/pod-api-key.eval.md) · [lb-endpoint-contract](../../runpod-vllm/evals/lb-endpoint-contract.eval.md) · [pick-the-product](../../runpod-vllm/evals/pick-the-product.eval.md). Status key: [golden-paths README](README.md#status-legend).

**Goal:** from "serve this model with vLLM", an agent proves the vLLM config on a Pod, moves the same image and arguments to a load-balancing Serverless endpoint, verifies both with a real OpenAI client, and tears down the test resources.

**Status:** COVERED — live-verified 2026-11-06
**Lane(s):** runpod-mcp, procedure in [runpod-vllm](../../runpod-vllm/SKILL.md)

## When to use this

Use this path when the model needs a specific `vllm/vllm-openai` tag: a new architecture, or a vLLM version newer than the Hub worker-vllm release. The Pod has no health window, so a slow first boot is visible and harmless. The load-balancing endpoint then serves the proven config with scale-to-zero.

When the Hub worker-vllm release already supports the model, the queue endpoint is one call: follow [runpod-vllm's queue reference](../../runpod-vllm/reference/queue-endpoint.md) (or [path 20](20-model-caching-endpoint.md) for a host-cached model with runpodctl).

## Prerequisites

- The [shared prerequisites](README.md#before-you-run-any-path-shared-prerequisites).
- `pip install openai` for [`test_endpoint.py`](../../runpod-vllm/scripts/test_endpoint.py).

## Walkthrough

1. **Size.** `Qwen/Qwen3-8B` is about 8 B parameters in bf16: about 16 GB of weights, plus KV cache for an 8192-token context. One 24 GB card fits it; the Pod used a 48 GB A40 because 24 GB Pods had no stock at the CUDA floor.
2. **Read stock at the image floor.** The image sets `NVIDIA_REQUIRE_CUDA=cuda>=13.0`. Read Pod stock with `get-capacity` (`cudaVersions:["13.2"]`, `secureCloudOnly:true`): the RTX A5000 was `Out` for Pods while the A40 had stock at $0.59/hr. Serverless stock is a separate read.
3. **Create the Pod in one call.**

   ```json
   {
     "name": "vllm-skill-gp27-pod",
     "image": "vllm/vllm-openai:v0.32.0",
     "args": "Qwen/Qwen3-8B --max-model-len 8192 --gpu-memory-utilization 0.90 --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3 --enable-prefix-caching",
     "env": { "VLLM_API_KEY": "<random>", "HF_HOME": "/workspace/hf" },
     "disk": 30,
     "mounts": { "persistent": { "size": 40, "path": "/workspace" } },
     "ports": ["8000/http"],
     "gpu": { "id": "NVIDIA A40", "count": 1, "minCudaVersion": "13.0" },
     "cloud": "SECURE"
   }
   ```

   Observed: `status: RUNNING`, `cudaVersion: "13.2"`, `dataCenterId: "CA-MTL-1"`, `cost: 0.59`, and `cmd` split from `args`.
4. **Watch the boot** with `stream-pod-logs`. Observed in order: `non-default args: {'model_tag': 'Qwen/Qwen3-8B', 'enable_auto_tool_choice': True, 'tool_call_parser': 'hermes', ... 'reasoning_parser': 'qwen3', 'gpu_memory_utilization': 0.9, 'enable_prefix_caching': True}`, `Resolved architecture: Qwen3ForCausalLM`, `Using max model len 8192`, the weight fetch, then the engine init. The API answered about 2.5 minutes after the create.
5. **Verify the Pod.**

   ```bash
   python3 test_endpoint.py --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
     --api-key-env VLLM_API_KEY --model Qwen/Qwen3-8B --thinking-switch --wait-for-ready 1500
   ```

   Observed: `chat` 33.3 tok/s, `stream` TTFT 0.28 s, `tool_call` `get_weather({"city": "Reykjavik"})`, `thinking_off` answered `391`.
6. **Create the load-balancing endpoint** with the same image and arguments, plus the health contract:

   ```json
   {
     "name": "vllm-skill-lb-test",
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

   Observed: `requestUrls.health` = `https://<endpoint-id>.api.runpod.ai/health`; the first worker (RTX A5000, EU-SE-1) started 7 s after the create, and the API answered about 2.5 minutes after the create. No vLLM API key: the gateway checks the Runpod API key.
7. **Verify the endpoint** with the Runpod API key:

   ```bash
   python3 test_endpoint.py --base-url https://<endpoint-id>.api.runpod.ai/v1 \
     --api-key-env RUNPOD_API_KEY --model Qwen/Qwen3-8B --thinking-switch --wait-for-ready 1500
   ```

   Observed: 5/5 passed, `chat` 39.5 tok/s, `stream` TTFT 0.23 s. A request without the key returned `401`.

## Verify

- `test_endpoint.py` exits 0 with `"all_passed": true` on each URL.
- `get-pod` shows `cudaVersion` at or above 13.0; `get-endpoint` shows `gpu.minCudaVersion: "13.0"` and the three health env vars.

## Gotchas

- **Pod and Serverless stock are separate reads, and both depend on the CUDA floor.** The Serverless read showed RTX A5000 stock at CUDA 13.2 while Pod creates for the same card failed on capacity.
- **vLLM 0.32.0 returns the thinking text in `reasoning`, not `reasoning_content`.** A client that reads only `reasoning_content` sees no streamed tokens until the thinking ends (a 22 s apparent TTFT on this model).
- **The load-balancing endpoint listed 3 workers with `workers.max: 1`.** `list-endpoint-workers` showed 1 `RUNNING` and 2 `INITIALIZING` (RTX PRO 6000 MIG 1g.24gb slices, also in `AMPERE_24`) during the test. Read `list-endpoint-workers` after a test and delete the endpoint or scale it down promptly.
- **A worker-count change does not restart workers.** Changing `workers.idleTimeout` left `endpointVersion` at 1 and no worker stale. An image, `args` or env change cuts a new release.
- **The Hub queue variant:** the listed worker-vllm release was v2.30.1 while GitHub had v2.30.3, and the deploy copied the release's `allowedCudaVersions: ["13.0"]`. A worker still started (RTX A5000, CA-MTL-1) and the same test passed 5/5 on `https://api.runpod.ai/v2/<id>/openai/v1`.

## Cost & cleanup

- Pod: 1× A40 Secure Cloud, $0.59/hr while running. Endpoint workers: `AMPERE_24`, $0.75/hr per running worker.
- Delete the Pod (`delete-pod`) and the endpoint (`delete-endpoint`), then confirm with `list-pods` and `list-endpoints`. A Hub deploy also leaves a template that `delete-template` refuses for up to about 90 minutes after the endpoint delete.

## Skill gaps folded back

- The CUDA floor, the Pod-vs-Serverless stock read, the `reasoning` field, the extra-worker check and the template delete delay are in [runpod-vllm](../../runpod-vllm/SKILL.md) and its references.
- `test_endpoint.py` reads both `reasoning` and `reasoning_content`, and makes the Qwen-only thinking switch opt-in (`--thinking-switch`).
