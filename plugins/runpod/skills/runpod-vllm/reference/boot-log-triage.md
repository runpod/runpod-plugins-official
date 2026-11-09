---
concepts: [log-stream, worker, pod, machine]
---

# vLLM boot log triage

Judge a vLLM boot by forward progress, not by the word ERROR. Read the log in short steps with `stream-pod-logs` (Pod) or `list-endpoint-workers` then `stream-worker-logs` (endpoint).

## Progress markers

| Log line | Meaning |
|---|---|
| `non-default args: {...}` | the flags vLLM received; compare with what you set |
| `Resolved architecture: ...` | the image's vLLM knows the model |
| `Using max model len N` | the context length in effect |
| `Fetching N files` / download progress | weights downloading to `HF_HOME` |
| `Loading weights took ...` | weights in GPU memory |
| `torch.compile` / `Capturing CUDA graphs` | the slow part of the first boot; skipped by `--enforce-eager` |
| `Application startup complete.` | the API answers; `GET /v1/models` works |

## Lines that look bad but are not

- `You are sending unauthenticated requests to the HF Hub`: fine for public weights. Set `HF_TOKEN` for gated weights or higher rate limits.
- `Using default sampling params from model: ...`: the model's `generation_config.json` is the server default. Clients that need repeatable output send their own sampling values.
- Warnings about unknown or undocumented config keys from `transformers`: harmless when the boot moves on.
- `Triton kernel JIT compilation during inference` (repeated once per kernel): expected on the first requests, most of all with `--enforce-eager`. It is why the first request is slower than the next.

## Failures and fixes

| Signature | Cause | Fix |
|---|---|---|
| `ValueError` or `KeyError` naming an unknown or unsupported architecture | the image's vLLM is older than the model | use a newer `vllm/vllm-openai` tag; on the Hub worker, move to a load-balancing endpoint or a Pod with that tag |
| Container fails to start, `OCI runtime create failed`, or CUDA driver errors before any vLLM line | host CUDA older than the image | set `gpu.minCudaVersion` to the image floor (13.0 for `vllm/vllm-openai:v0.32.0`) and recreate |
| `NCCL error: unhandled cuda error` at `ncclCommInitRank`, all ranks, before the weight download, on a host whose CUDA meets the floor | NVLink SHARP init fails on the host | add `NCCL_NVLS_ENABLE=0` to the env and recreate; add `NCCL_DEBUG=INFO` only while you diagnose |
| `torch.OutOfMemoryError` during weight load | the weights do not fit | more GPUs with tensor parallelism, or a quantized checkpoint; lowering `--gpu-memory-utilization` does not help |
| KV cache error that names the largest `max_model_len` that fits | context too long for the free VRAM | lower `--max-model-len` (or use `--kv-cache-dtype fp8`) |
| state or mamba cache size error | a hybrid model sizes a fixed cache from `--max-num-seqs` | lower `--max-num-seqs` |
| `401` or `403` downloading weights | gated repo | set `HF_TOKEN`; the user must accept the model license on Hugging Face |
| `No space left on device` | disk smaller than the weights | raise `disk` (or the volume disk) to the weights plus 20–30 GB |
| vLLM banner repeats with the same `APIServer` pid | engine init retries in-process after a crash | read the lines just before each banner; the container may never restart |
| Load-balancing worker restarts again and again | health check never passed | see [lb-endpoint.md](lb-endpoint.md#failure-modes) |
| Queue job stays `IN_QUEUE` while a worker shows `RUNNING` | the worker is still booting or crash-looping | read `stream-worker-logs`; the worker status alone does not show a crash loop |

A known crash loop bills for every minute it runs. Stop it first (delete the Pod, or set the endpoint's `workers.max` to 0), then fix and recreate.

## Exact rules

- [log-stream](../../runpod-usage/concepts/log-stream.yaml) · [machine](../../runpod-usage/concepts/machine.yaml) · [worker](../../runpod-usage/concepts/worker.yaml)
