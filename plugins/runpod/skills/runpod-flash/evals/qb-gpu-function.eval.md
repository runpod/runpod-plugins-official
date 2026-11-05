# Run a GPU function on Runpod serverless

## Prompt

I have a Python function that runs a PyTorch model on a GPU. I want to run it on
Runpod serverless with the Runpod Python SDK, with up to 5 workers. Write the code.

## Expected behavior

The agent should:

1. `import runpod` and create `app = runpod.App("...")`
2. Decorate the function with `@app.queue(gpu=..., workers=5 or (0, 5), dependencies=[...])`
3. Import heavy packages inside the function
4. Call it from a `@runpod.local_entrypoint` with `.remote(...)` and run it with
   `rp flash dev FILE` (or `--once`)

## Assertions

- Uses `runpod.App` and `@app.queue(...)` (queue-based)
- Sets `gpu=` (a string such as `"4090"`, a `GpuGroup`, or a list) and a worker max of 5
- Lists the function's pip packages in `dependencies=[...]`
- Calls the function with `.remote(...)` (or `await fn.remote.aio(...)`), not a bare `await fn(...)`
- Does NOT import from `runpod_flash` or use `@Endpoint` / `@remote`
- Does NOT set both `gpu=` and `cpu=`
- Arguments passed to `.remote()` are JSON-serializable
