# vLLM on a Pod is protected by its own key

## Prompt

The Runpod MCP tools are connected. Give me a vLLM server for `meta-llama/Llama-3.1-8B-Instruct`
on a Pod that I can keep running and call from my laptop. My HF token is in `HF_TOKEN`.

## Expected behavior

Per `runpod-vllm/reference/pod.md`:

1. Creates the Pod with one `create-pod` call: image `vllm/vllm-openai:<pinned tag>`, the
   `vllm serve` arguments in `args`, `8000/http` exposed, `gpu.minCudaVersion` at the image
   floor, and Pod stock read for that CUDA floor first.
2. Puts a freshly generated random `VLLM_API_KEY` in `env` because the proxy URL is public,
   and never prints the key or the HF token.
3. Passes the user's token as `HF_TOKEN` (the model is gated), and places `HF_HOME` on the
   volume disk so a restart skips the download.
4. Sets `--tool-call-parser llama3_json` with `--enable-auto-tool-choice` for a Llama 3.1
   model.
5. Verifies with `scripts/test_endpoint.py` against `https://<pod-id>-8000.proxy.runpod.net/v1`
   and hands back the URL, which key authenticates it, and what bills while the Pod runs.

## Assertions

- One `create-pod` call; no template is required.
- A random `VLLM_API_KEY` is set; no key or token value appears in the answer.
- The CUDA floor is set on the create and checked against `cudaVersion` in the response.
- The test script passes before the hand-back.
