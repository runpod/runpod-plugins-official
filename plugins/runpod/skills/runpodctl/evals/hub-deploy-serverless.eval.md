# Deploy a vLLM serverless worker from the Runpod Hub

## Prompt

Deploy the vLLM serverless worker from the Runpod Hub. Use an available GPU, and
have it scale from 0 up to 2 workers. Give me the exact command(s).

## Expected behavior

The agent should:

1. Find the hub listing id with `runpodctl hub search vllm`
2. Create the endpoint with `runpodctl serverless create --hub-id <id> --workers-min 0 --workers-max 2`
3. Handle the GPU correctly (this is the easy thing to get wrong):
   - Preferably omit `--gpu-id` and let the hub config's default GPU apply, OR
   - Pass a GPU name from `runpodctl gpu list` (e.g. `"NVIDIA GeForce RTX 4090"`); runpodctl ≥ v2.14.0 maps it to the matching pool (`ADA_24`). On older binaries, pass the pool id itself.

## Assertions

- Finds the hub id via `runpodctl hub search vllm` (does not invent one)
- Runs `runpodctl serverless create --hub-id <id> ...`
- Sets `--workers-min 0` and `--workers-max 2`
- If `--gpu-id` is passed, its value is a real GPU name from `runpodctl gpu list` or a pool id (e.g. `ADA_24`), not an invented value
- Checks `runpodctl version` (or `--help`) before relying on GPU-name mapping on the hub path

## Notes

runpod/runpodctl#287 tracked `serverless create --gpu-id` on the `--hub-id` path rejecting
GPU display names with `Invalid GPU Pool ID`. Verified live with runpodctl v2.14.0
(2026-09-28): `--gpu-id "NVIDIA GeForce RTX 4090"` on the hub path created the endpoint
with `gpu.pools: ["ADA_24"]`. Older binaries may still need the pool id.
