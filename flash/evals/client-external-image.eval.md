# Deploy a prebuilt vLLM image and call it over HTTP

## Prompt

I have a prebuilt Docker image `myorg/vllm-server:latest` that serves an
OpenAI-compatible API on an A100. Using runpod-flash, deploy it to a Runpod
serverless GPU endpoint and send a completion request to `/v1/completions`.

## Expected behavior

The agent should:

1. Create an `Endpoint` with `image="myorg/vllm-server:latest"` (client mode) plus `name=`, `gpu=GpuGroup.AMPERE_80`
2. Recognize that `image=` means client mode (deploys the image, then calls it via HTTP) — no decorated function
3. Call the deployed endpoint with `await server.post("/v1/completions", {...})`

## Assertions

- Creates an `Endpoint(name=..., image="myorg/vllm-server:latest", gpu=GpuGroup.AMPERE_80, ...)`
- Does NOT wrap a Python function in a decorator (client mode, not decorator mode)
- Calls the endpoint with `await <ep>.post("/v1/completions", <payload>)`
- Uses `await` on the HTTP call
- Does NOT set `id=` together with `image=` (mutually exclusive)
