# Run a GPU function on Runpod serverless

## Prompt

I have a Python function that runs a PyTorch model on a GPU. I want to run it on
Runpod serverless using runpod-flash, with up to 5 workers. Write the code.

## Expected behavior

The agent should:

1. Import `Endpoint` and `GpuGroup` from `runpod_flash`
2. Decorate the function with `@Endpoint(name=..., gpu=GpuGroup.<type>, workers=5, dependencies=["torch"])`
3. Put the `import torch` (and any other deps) INSIDE the decorated function
4. Make the function `async def`
5. Call it with `await`

## Assertions

- Uses `@Endpoint(...)` as a decorator with a `name=` (queue-based mode)
- Sets `gpu=` to a `GpuGroup` member and `workers` to 5
- Lists `torch` in `dependencies=[...]`
- The `import torch` statement is INSIDE the function body, not at module top level
- The function is `async def` and is invoked with `await`
- Does NOT use the deprecated `@remote` decorator
- Does NOT set both `gpu=` and `cpu=`
