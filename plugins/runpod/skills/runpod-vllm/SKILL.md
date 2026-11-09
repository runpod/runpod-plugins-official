---
name: runpod-vllm
description: Serve a Hugging Face model with vLLM on Runpod (Hub worker-vllm queue endpoint, load-balancing
  endpoint on a vllm/vllm-openai image, or a Pod), sized, CUDA-pinned and verified with a real OpenAI client.
  Use for any "deploy/serve/test this LLM with vLLM" request or a vLLM deployment that will not boot; defer to
  runpod-serverless-deploy for non-vLLM engines and runpod-endpoint-ops for an endpoint that already works.
metadata:
  author: runpod
  version: "2.0.0" # x-release-please-version
  concepts: [serverless-endpoint, pod, hub-repo, worker, gpu-type, gpu-pool, gpu-availability, container-image, exposed-port, endpoint-release, log-stream, network-volume]
license: Apache-2.0
---

# vLLM on Runpod

You take a model id and leave the user with a working OpenAI-compatible vLLM server: the URL, the auth, a tested client snippet, what it costs per hour, and what is still billing. A create call that returned an id is not a working server. The deployment is done only when [`scripts/test_endpoint.py`](scripts/test_endpoint.py) passes against the real URL.

Creating a Pod or an endpoint bills. State the hourly price from the catalog read before each create. The generic endpoint procedure (smoke job, hold limits, hand-back fields) is [runpod-serverless-deploy](../runpod-serverless-deploy/SKILL.md)'s and the generic Pod procedure is [runpod-pod-deploy](../runpod-pod-deploy/SKILL.md)'s. This skill adds what is specific to vLLM. A worked run of the Pod and load-balancing paths is [golden path 27](../runpod/golden-paths/27-vllm-pod-to-endpoint.md); the full index is in [golden-paths/README.md](../runpod/golden-paths/README.md).

## Tool binding

If a tool named here is missing from the session's tool list, say so and use the nearest read. Never invent a result. Parameter names follow the live tool schema (`describe-tool`); the examples in the references show the settings to send, not a schema.

| Capability | Tool |
|---|---|
| Hub worker-vllm release: listed tag, image, CUDA pin, GPU pools, env schema | `list-hub-repos` (`repoOwner:"runpod-workers"`, `searchTerm:"worker-vllm"`, `includeConfig:true`) |
| GPU price and stock per product; stock at an exact GPU count and host CUDA version | `list-gpu-types` (`include:["AVAILABILITY"]`, `product:["POD"]` or `["SERVERLESS"]`); `get-capacity` (`gpuCount`, `cudaVersions`) |
| Queue endpoint from the Hub release | `deploy-hub-repo` |
| Load-balancing endpoint on a vLLM image | `create-endpoint` (`type:"LOAD_BALANCER"`) |
| Pod running `vllm serve` | `create-pod` (`args` carries the `vllm serve` arguments, `gpu.minCudaVersion` the floor) |
| CUDA floor or GPU change on an endpoint | `set-endpoint-gpus` or `update-endpoint` (`gpu`) |
| Boot progress and failures | `stream-pod-logs`; `list-endpoint-workers` + `stream-worker-logs` |
| Read back what you set | `get-pod`, `get-endpoint` |
| Teardown | `delete-pod`, `delete-endpoint` (and the template a Hub deploy created, `delete-template`) |

## Step 1: read the facts

Read these before you choose anything. Do the reads in parallel.

- **The model.** From the Hugging Face model card and `config.json`: parameter count, native dtype, context length, whether it is a reasoning model, whether it supports tool calls, whether an official quantized variant exists (FP8, AWQ, GPTQ). vLLM's GGUF support is limited and version-dependent: for a `*.gguf` repo, prefer the same model's safetensors repo on vLLM, or a GGUF engine from [runpod-serverless-deploy](../runpod-serverless-deploy/SKILL.md)'s engine table.
- **The vLLM version the model needs.** The model card or the vLLM recipe for the model (`https://github.com/vllm-project/recipes`) names a minimum vLLM version and the serving flags. If neither says, treat the first boot as the test.
- **The Hub worker.** `list-hub-repos` for `runpod-workers/worker-vllm` gives the listed release, its image and its `allowedCudaVersions`. The release notes on GitHub name the vLLM version it bundles. Read it live every time: the listed release changes, and it can lag the newest GitHub release.

## Step 2: choose the product

```
Does the Hub worker's vLLM support the model?
├── yes → Is it request/response traffic that can scale to zero?
│         ├── yes → queue endpoint (reference/queue-endpoint.md)
│         └── no, the user wants a server they keep → Pod (reference/pod.md)
└── no (new architecture, needs a newer vLLM or a nightly image)
          ├── model boots in minutes on ≤ 2 GPUs → load-balancing endpoint (reference/lb-endpoint.md)
          └── very large or slow to boot → Pod first; move to an endpoint after it passes
```

| Product | URL | Auth | Choose it when |
|---|---|---|---|
| Queue endpoint (Hub worker-vllm) | `https://api.runpod.ai/v2/<endpoint-id>/openai/v1` | Runpod API key | the Hub vLLM supports the model; scale-to-zero; no image to manage |
| Load-balancing endpoint (`vllm/vllm-openai:<tag>`) | `https://<endpoint-id>.api.runpod.ai/v1` | Runpod API key at the gateway | the model needs a vLLM version the Hub worker does not have; direct HTTP, no queue |
| Pod (`vllm/vllm-openai:<tag>`) | `https://<pod-id>-8000.proxy.runpod.net/v1` | vLLM's own API key (`VLLM_API_KEY`) | a long-running server, debugging a boot, or a model too large or slow for the endpoint health window |

For a new or very large model, prove the config on a Pod first: a Pod has no health watchdog, so a long first boot (download plus compile) is fine and the logs stay readable. Then move the same image and arguments to an endpoint.

## Step 3: size the GPUs

Show the arithmetic in the answer.

- Weights in GB ≈ parameters (billions) × bytes per parameter: bf16/fp16 2, FP8 1, 4-bit 0.5. `Qwen/Qwen3-8B` in bf16 is about 16 GB.
- Add room for the KV cache and activations: at least 20–30 % of the weights for a short context, more for a long one. Lower `--max-model-len` when the model's native context does not fit (the boot fails with a KV-cache error that names the largest length that fits).
- One card is best. When one card cannot hold the model, set the GPU count to the next of 1, 2, 4 or 8 and set tensor parallelism to that count (`--tensor-parallel-size`, or `TENSOR_PARALLEL_SIZE` on the Hub worker). Say that the cost scales with the count.
- Read stock **for the product you create** (`product:["POD"]` for a Pod, `["SERVERLESS"]` for an endpoint), **at the GPU count you will use**, and **at the host CUDA versions that meet the image floor** (`get-capacity` with `gpuCount` and `cudaVersions`). Stock for one product, count or CUDA version says nothing about another.

## Step 4: pin the host CUDA floor

`vllm/vllm-openai:v0.32.0` and the Hub worker-vllm image built on it are CUDA 13 builds (`NVIDIA_REQUIRE_CUDA=cuda>=13.0`); read that variable in the image config for any other tag. Set `gpu.minCudaVersion` to the image floor on every create. The general rule and why: [gpu-selection.md step 3](../runpod-usage/reference/gpu-selection.md#step-3-pin-the-cuda-floor).

Prefer the open floor (`minCudaVersion`) to an exact list (`allowedCudaVersions`): the CUDA version is a property of each machine's driver and differs between machines of one GPU type, so an exact list matches only the hosts that report exactly those versions. A Hub release can carry an exact list, and `deploy-hub-repo` copies it to the endpoint. Read the endpoint back after the deploy. If the workers stay at zero or throttled while the stock read shows capacity at a newer CUDA version, widen it with `set-endpoint-gpus` (`allowedCudaVersions:""`, `minCudaVersion:"13.0"`).

## Step 5: set the vLLM flags

The flags and what each one costs are in [reference/serving-flags.md](reference/serving-flags.md). The short list:

- `--max-model-len`: cap it to what the job needs and the KV cache holds.
- `--gpu-memory-utilization 0.90`: leave the default unless the boot log says otherwise.
- `--tensor-parallel-size N` = GPU count.
- Tool calls: `--enable-auto-tool-choice --tool-call-parser <parser>`. Reasoning models: `--reasoning-parser <parser>`. Take the parser names from the model card or the vLLM recipe.
- A quantized checkpoint (FP8, AWQ, GPTQ) needs no flag: vLLM reads the method from the checkpoint config.
- Gated weights: `HF_TOKEN` in the env. Never print it.

## Step 6: deploy and watch the boot

Follow exactly one reference: [queue-endpoint.md](reference/queue-endpoint.md), [lb-endpoint.md](reference/lb-endpoint.md) or [pod.md](reference/pod.md).

Watch the boot in short reads, never one long blind wait. Each read checks three things: the resource still exists, its status, and the log tail. Judge progress by forward movement (download, shard load, compile, CUDA graph capture, `Application startup complete`), not by the word ERROR: a healthy vLLM boot prints warnings. The failure signatures and their fixes are in [reference/boot-log-triage.md](reference/boot-log-triage.md). On a known crash loop, stop the spend first (delete the Pod, or set the endpoint's `workers.max` to 0), then diagnose.

The first log lines prove which settings took effect: vLLM prints `non-default args: {...}` at startup. Check it against what you set before you wait for the rest of the boot.

## Step 7: verify with a real client

```bash
pip install openai
python3 scripts/test_endpoint.py --base-url <url>/v1 --api-key-env RUNPOD_API_KEY --model <served-model-id> \
  --wait-for-ready 1800 [--thinking-switch] [--skip-tools] [--vision]
```

The key comes from the named environment variable, so it stays out of the process list: `RUNPOD_API_KEY` for an endpoint, `VLLM_API_KEY` for a Pod.

The script waits for `GET /v1/models`, then tests chat, streaming (time to first token), tool calls and, with flags, the Qwen-style thinking switch and an image input. It exits non-zero if any enabled test fails. A model that answers with garbage or repeats itself has the wrong parser or chat template: fix the server before you report anything.

The first request after a boot can be several times slower than the next one (kernels compile on first use). Quote both numbers if you quote latency.

## Step 8: hand back and clean up

The final message is standalone:

- product, model id, image or Hub release, GPU type × count, data center, hourly price;
- the sizing arithmetic and the flags you set, with the reason for each non-default flag;
- the base URL, which key authenticates it, and a working OpenAI SDK snippet that reads the key from an environment variable;
- the test result: each check, pass or fail, with the measured first-request and warm latency;
- what is billing now, and how to stop it.

Default to keeping what the user asked for. Tear down when the user framed the deployment as a test or asks for cleanup: delete the Pod or endpoint (and the template a Hub deploy created), then confirm with `list-pods` / `list-endpoints` that nothing you created is left.

## Hard rules

- Never claim the server works without a passing `test_endpoint.py` run, or the quoted failure.
- Never put a vLLM `--api-key` on a load-balancing endpoint: the gateway checks the Runpod API key, and a second key makes every request fail. A Pod is the opposite: its proxy URL is public, so it always gets a random `VLLM_API_KEY`.
- Never change the config of a warm endpoint during a test without saying it: an image or env change cuts a new release and replaces the workers with cold ones.
- Deploy only what the user asked for, and change or delete only what this conversation created.

## Contract

The cross-journey answer contract is in the `runpod-mcp` skill. If it is not loaded in this conversation, load it before the next tool call.
