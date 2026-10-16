# A volume-backed model loads through VolumeCache, not straight off the mount

## Prompt

I have a Flash GPU endpoint that loads Qwen2.5-7B-Instruct with `from_pretrained`, and it
scales to zero, so every cold start re-downloads the model from HuggingFace. I attached a
network volume. How do I make cold starts faster?

## Expected behavior

The agent should:

1. Keep the HF cache on the worker's **container disk** (for example `HF_HUB_CACHE=/opt/hf-cache`),
   not under `/runpod-volume`
2. Wrap the model load in `VolumeCache(dirs=[<that dir>])` from `runpod.serverless`, inside
   the class `@Endpoint`'s `__init__` so it runs once per worker, and add `runpod>=1.12.0` to
   `dependencies`
3. Explain the mechanism: the first worker downloads from the Hub and syncs a mirror to the
   volume, and later cold starts copy the mirror onto local disk and load from there
4. Name the gotchas: errors are swallowed by default (`best_effort=False` while debugging),
   Hub access stays on because symlinks aren't copied, size the volume for the mirror,
   size the container disk for the whole model (`PodTemplate(containerDiskInGb=...)`; the
   Flash default is 64 GB), and let one worker populate the mirror first
5. Offer Model Store as the no-volume alternative for a HuggingFace model on GPU: attach it after
   `flash deploy` with `runpodctl serverless update <endpoint-id> --model-reference`, with the
   caveat that worker start waits for a host that holds the model
6. Suggest timing the whole cold request before and after, not quoting a speedup

## Assertions

- Wraps the load in `VolumeCache` and imports it from `runpod.serverless`
- Lists `runpod>=1.12.0` in the `@Endpoint` `dependencies`
- In the `VolumeCache` answer, points the HF cache at a local path, not at `/runpod-volume`
  (the Model Store alternative's `/runpod-volume/huggingface-cache/hub` is correct)
- Mentions that a failing cache falls back silently to a normal cold start
- Checks that the container disk can hold the whole local cache
- Mentions Model Store (`--model-reference`) as an alternative, with the worker-wait caveat
- Does NOT set `HF_HUB_OFFLINE=1` alongside `VolumeCache`
- Does NOT tell the user to load the model directly from `/runpod-volume` as the fast path
- Does NOT quote a fixed speedup figure as a guarantee
