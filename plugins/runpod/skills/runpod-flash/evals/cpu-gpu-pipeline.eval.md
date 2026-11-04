# Build a CPU-preprocess then GPU-inference pipeline

## Prompt

With the Runpod Python SDK, build a two-stage pipeline: a CPU stage that cleans raw data
with pandas, then a GPU stage that runs inference with torch on an A100. Wire them together
and run several batches in parallel.

## Expected behavior

The agent should:

1. Define a CPU `@app.queue(cpu="cpu5c-..." or similar, dependencies=["pandas"])` function
2. Define a GPU `@app.queue(gpu="AMPERE_80" or "A100", ...)` function
3. Import `pandas`/`torch` inside the respective functions
4. Chain them: `score.remote(preprocess.remote(rows))`
5. Fan out with `.spawn()` and collect with `job.result()` (or `asyncio.gather` over `.remote.aio`)

## Assertions

- CPU stage sets `cpu=` to a CPU flavor id and does NOT set `gpu=`
- GPU stage sets `gpu=` to an A100 pool or name and does NOT set `cpu=`
- `pandas` is in the CPU stage `dependencies`; the GPU stage either lists `torch` or relies on
  the built-in GPU image's torch, and says which
- Stages exchange JSON-serializable values (lists/dicts, not DataFrames or tensors)
- Parallel calls use `.spawn()` / `.remote.aio`, not sequential `.remote()` in a loop
- Does NOT import from `runpod_flash`
