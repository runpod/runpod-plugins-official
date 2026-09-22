# Cache vs network volume is a latency call, and the miss path looks like an idle queue

## Prompt

I'm deploying a 70B model from HuggingFace to a serverless endpoint and I'll be scaling
it across a few regions. Should I use the model cache or a network volume? Also, is the
cache available in every region?

## Expected behavior

The agent should:

1. Frame the choice as **latency**, not cost — download time is not billed on a cache
   hit or a miss, so the cache doesn't save money over a volume, it saves setup
2. Describe the miss path correctly: Runpod holds worker start until the model is
   downloaded, so the **job sits in the queue** and the endpoint looks idle or stuck
   when it is actually downloading
3. Lean toward a **pre-loaded network volume** for a latency-sensitive endpoint at this
   size, while saying the cache is the reasonable default when latency is not critical
4. Recommend **measuring both** on the user's own model and region rather than asserting
   a threshold — cache capacity is a share of each machine's disk, so it varies by host
   and there is no number to quote; a benchmark from elsewhere doesn't transfer
5. Note that a network volume is **pinned to one data center**, so multi-region means one
   pre-loaded volume per DC
6. On the region question: say **Runpod publishes no list** of model-cache-enabled data
   centers, and offer the network-volume-capable DC list only as a labeled proxy, or
   offer to deploy and measure

## Assertions

- Says download time is NOT billed, on hit or miss
- Describes the miss as a queued job / delayed worker start, not a billing leak
- Mentions the volume's single-data-center pinning for the multi-region case
- Suggests testing both rather than quoting a hard size cutoff
- Says capacity varies by host rather than implying a single platform-wide cache size
- Treats inconsistent cold starts across workers as expected, not as a broken endpoint
- Does NOT claim the worker bills while downloading
- Does NOT state a list of regions that support the model cache as fact
- Does NOT claim `--model-reference` makes cold starts fast unconditionally
