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
   - If specifying `--gpu-id`, use a GPU **pool ID** (e.g. `AMPERE_48`, `ADA_24`, `HOPPER_141`) — NOT a display name like `"NVIDIA A40"` from `runpodctl gpu list`. On the `--hub-id` path the API rejects display names with `Invalid GPU Pool ID`.

## Assertions

- Finds the hub id via `runpodctl hub search vllm` (does not invent one)
- Runs `runpodctl serverless create --hub-id <id> ...`
- Sets `--workers-min 0` and `--workers-max 2`
- If `--gpu-id` is passed at all, its value is a GPU pool ID (e.g. `AMPERE_48`), NOT a `gpu list` display name like `"NVIDIA A40"`
- Does NOT pass a `gpu list` display name to `--gpu-id` on the hub path

## Notes

This encodes the gotcha found via live testing and tracked upstream as
runpod/runpodctl#287: `serverless create --gpu-id` on the `--hub-id` path requires
GPU pool IDs, while `gpu list` (and the `--help` text) surface display names. Until
that is reconciled, the safe answer is to omit `--gpu-id` or use a pool ID.
