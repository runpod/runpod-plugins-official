---
concepts: [hub-repo, serverless-endpoint, worker, endpoint-release, gpu-pool]
---

# vLLM on a queue endpoint (Hub worker-vllm)

The Hub listing `runpod-workers/worker-vllm` is a prebuilt queue worker around the official vLLM image. You deploy it in one call and configure vLLM with env vars. Use it when the vLLM version in the listed release supports the model.

## Read the release first

`list-hub-repos` with `repoOwner:"runpod-workers"`, `searchTerm:"worker-vllm"`, `includeConfig:true` returns:

- `listedRelease.tagName` and `imageName`: the release the Hub deploys. The Hub can list an older release than the newest one on GitHub. The GitHub release notes and `Dockerfile` (`ARG VLLM_VERSION`) give the bundled vLLM version.
- `config.allowedCudaVersions`, `config.gpuIds`, `config.containerDiskInGb`: the defaults the deploy copies to the endpoint.
- `config.env`: every env key the worker reads, with its default.

## Deploy

The settings to send with `deploy-hub-repo` (take the exact parameter names from the live tool schema):

```text
deploy-hub-repo
  repo: runpod-workers/worker-vllm
  name: vllm-qwen3-8b
  gpuIds: AMPERE_24              # from your sizing, never the release default
  gpuCount: 1
  containerDiskInGb: 40          # weights + about 20 GB
  workersMin: 0
  workersMax: 1
  idleTimeout: 60
  flashboot: FLASHBOOT
  executionTimeoutMs: 600000
  env:
    MODEL_NAME: Qwen/Qwen3-8B
    MAX_MODEL_LEN: "8192"
    GPU_MEMORY_UTILIZATION: "0.90"
    ENABLE_PREFIX_CACHING: "true"
    ENABLE_AUTO_TOOL_CHOICE: "true"
    TOOL_CALL_PARSER: hermes
    REASONING_PARSER: qwen3
```

- **Always pass `gpuIds`.** Without it the endpoint gets the release's pools, which can be the most expensive cards.
- **Env names.** Each `vllm serve` flag maps to an env key: upper case, `-` becomes `_` (`--max-model-len` → `MAX_MODEL_LEN`). Use the keys `config.env` lists. Multi-GPU: `TENSOR_PARALLEL_SIZE` = `gpuCount`.
- **Read the endpoint back.** `get-endpoint` shows the merged env and the `gpu` block the deploy set. The deploy copies the release's `allowedCudaVersions` as an exact list. When no worker starts (`list-endpoint-workers` total 0, or throttled) and `get-capacity` shows stock only at other CUDA versions, replace the list with the open floor:

  ```text
  set-endpoint-gpus  endpointId: <id>  allowedCudaVersions: ""  minCudaVersion: "13.0"
  ```

## Call it

The worker serves the OpenAI API on the queue's OpenAI route, authenticated with the Runpod API key:

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://api.runpod.ai/v2/<endpoint-id>/openai/v1",
                api_key=os.environ["RUNPOD_API_KEY"])
```

The native queue routes (`/run`, `/runsync`) also work. Their input shape is in the worker's README.

The first request after a scale from zero waits for a worker to start and load the weights. Run [`scripts/test_endpoint.py`](../scripts/test_endpoint.py) with `--wait-for-ready` so the cold start does not fail the first check. Watch the worker with `list-endpoint-workers` and `stream-worker-logs`.

## Change settings

An env or image change cuts a new endpoint release, and workers move to it as they cycle. Worker counts, scaling and timeout changes apply without a new release. `list-endpoint-releases` shows the rollout.

## Clean up

`deploy-hub-repo` also creates a template (its id is in the deploy response). Delete the endpoint first. The template stays held by the deleted endpoint until its last worker is billed, so `delete-template` answers 400 for up to about 90 minutes; delete it after that, and tell the user if it is still pending when you hand back.

## Exact rules

- [hub-repo](../../runpod-usage/concepts/hub-repo.yaml) · [serverless-endpoint](../../runpod-usage/concepts/serverless-endpoint.yaml) · [endpoint-release](../../runpod-usage/concepts/endpoint-release.yaml)
