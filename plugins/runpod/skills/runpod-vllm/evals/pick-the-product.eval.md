# Pick the vLLM product from the model and the Hub worker's vLLM version

## Prompt

The Runpod MCP tools are connected. Deploy `Qwen/Qwen3-8B` with vLLM so my app can call
it through the OpenAI SDK. Traffic is bursty and I don't want to pay when it's idle.

## Expected behavior

Per `runpod-vllm/SKILL.md` steps 1–3:

1. Reads the Hub worker live (`list-hub-repos`, `runpod-workers/worker-vllm`,
   `includeConfig:true`) and the model's size before choosing; does not quote a worker or vLLM
   version from memory.
2. The Hub worker's vLLM supports a Qwen3 dense model and the user wants scale-to-zero, so it
   picks the **queue endpoint** (`deploy-hub-repo`) and says why it did not pick a Pod or a
   load-balancing endpoint.
3. Shows the sizing arithmetic (about 8 B parameters × 2 bytes ≈ 16 GB in bf16, plus KV cache)
   and picks a 24 GB pool with stock, passing `gpuIds` from its own sizing rather than the
   release default.
4. Sets `MAX_MODEL_LEN`, `TOOL_CALL_PARSER`, `ENABLE_AUTO_TOOL_CHOICE` and `REASONING_PARSER`
   for the model, and states the hourly price before the deploy.
5. Verifies with `scripts/test_endpoint.py` against `https://api.runpod.ai/v2/<id>/openai/v1`
   using the Runpod API key, with `--wait-for-ready` for the cold start.

## Assertions

- Chooses the queue endpoint from the Hub worker-vllm release for this request.
- Reads the release config live before the deploy.
- Passes `gpuIds` explicitly on `deploy-hub-repo`.
- States the hourly price before creating anything.
- Does not report success before the test script passes, and quotes its results.
- Workers min stays 0 (scale-to-zero), as the user asked.
