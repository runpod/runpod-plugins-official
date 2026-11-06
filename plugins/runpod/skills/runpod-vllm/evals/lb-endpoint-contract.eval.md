# Load-balancing endpoint for a model the Hub worker cannot serve

## Prompt

The Runpod MCP tools are connected. A new model came out that needs a newer vLLM than the
Hub's vLLM worker has. The vLLM project publishes a `vllm/vllm-openai` tag that supports
it. Serve it on Runpod Serverless with direct OpenAI-style HTTP, no queue.

## Expected behavior

Per `runpod-vllm/reference/lb-endpoint.md`:

1. Creates a `LOAD_BALANCER` endpoint with `create-endpoint` on the named
   `vllm/vllm-openai:<tag>` image, with the `vllm serve` arguments in `args`.
2. Sets `PORT=8000`, `PORT_HEALTH=8000` and `HEALTH_CHECK_PATH=/health`, and
   `gpu.minCudaVersion` at the image's CUDA floor.
3. Does **not** set a vLLM `--api-key` or `VLLM_API_KEY`: the gateway authenticates with the
   Runpod API key.
4. Sends `scaling` with `type: REQUEST_COUNT`, and reads back `requestUrls.health`.
5. Verifies against `https://<endpoint-id>.api.runpod.ai/v1` with the Runpod API key and
   `scripts/test_endpoint.py`.

## Assertions

- Endpoint `type` is `LOAD_BALANCER` and the image is the named vLLM tag, not the Hub worker.
- All three health env vars are set to port 8000 and `/health`.
- No vLLM API key on the endpoint.
- The CUDA floor is set on the create.
- After the test, checks `list-endpoint-workers` for extra workers before handing back.
