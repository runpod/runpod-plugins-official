# A volume-backed model loads through VolumeCache, not straight off the mount

## Prompt

I have a Runpod SDK GPU endpoint that loads Qwen2.5-7B-Instruct with `from_pretrained`, and it
scales to zero, so every cold start re-downloads the model from HuggingFace. I attached a
network volume. How do I make cold starts faster?

## Expected behavior

The agent should:

1. Keep the HF cache on the worker's **container disk** (for example `HF_HUB_CACHE=/opt/hf-cache`),
   not under `/runpod-volume`
2. Wrap the model load in `VolumeCache(dirs=[<that dir>])` from `runpod.serverless`, inside an
   `@app.api` class's `@runpod.init` method (or a once-per-worker module-global cache in a
   queue function), with the volume mounted via `mounts={"/runpod-volume": vol}`
3. Explain the mechanism: the first worker downloads from the Hub and syncs a mirror to the
   volume, and later cold starts copy the mirror onto local disk and load from there
4. Name the gotchas: errors are swallowed by default (`best_effort=False` while debugging), Hub
   access stays on because symlinks aren't copied, size the volume for the mirror, size
   `container_disk_gb` for the whole model (the SDK default is 30 GB on GPU), and let one worker
   populate the mirror first
5. Offer `model=runpod.Model("Qwen/Qwen2.5-7B-Instruct")` as the no-volume alternative, with
   the caveat that worker start waits until the host has the weights
6. Suggest timing the whole cold request before and after, not quoting a speedup

## Assertions

- Wraps the load in `VolumeCache` imported from `runpod.serverless`
- Points the HF cache at a local path in the `VolumeCache` answer, not at `/runpod-volume`
- Mounts the volume with `mounts={"/runpod-volume": ...}`
- Mentions that a failing cache falls back silently to a normal cold start
- Raises `container_disk_gb` so the local cache fits
- Mentions `runpod.Model` as an alternative, with the worker-wait caveat
- Does NOT set `HF_HUB_OFFLINE=1` alongside `VolumeCache`
- Does NOT load the model directly from `/runpod-volume` as the fast path
- Does NOT quote a fixed speedup figure as a guarantee
- Does NOT use `runpod_flash` imports or `PodTemplate`
