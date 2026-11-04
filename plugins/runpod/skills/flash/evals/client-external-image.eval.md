# Serve a prebuilt vLLM worker image and call it

## Prompt

I have a prebuilt Docker image `myorg/vllm-worker:latest`. It is a complete Runpod Serverless
worker (it implements the handler) for OpenAI-style completions on an A100. Deploy it to a
Runpod serverless endpoint and send it a completion request from Python.

## Expected behavior

The agent should:

1. Recognize that a complete worker image is not an SDK app: there is no Python function to
   decorate
2. Create the endpoint with an infra lane (runpodctl or runpod-mcp) from the image, on an A100
   pool
3. Call it from Python with `runpod.Endpoint("ENDPOINT_ID").run_sync({...}, timeout=...)` or
   `.run(...)`

## Assertions

- Does NOT wrap the image in `@app.queue(image=...)` with an empty or placeholder function
- Creates the endpoint through runpodctl or the Runpod MCP tools, referencing the image
- Calls it with `runpod.Endpoint(...)` and puts the request under the client's `request_input`
  (the client sends `{"input": {...}}`)
- Raises the `run_sync` timeout or uses `run()` + `output(timeout=...)` for the first, cold request
- Does NOT import from `runpod_flash`
