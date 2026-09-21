# Size a model against the host cache before choosing `--model-reference`

## Prompt

I'm deploying a 70B model from HuggingFace to a serverless endpoint and I'll be scaling
it across a few regions. Should I use the model cache or a network volume?

## Expected behavior

The agent should:

1. Recommend a **pre-loaded network volume** for a model this large across regions, not
   the HF model cache
2. Explain the cache's two limits: it is capped (a very large model will not reliably
   stay resident) and a hit is **per host, per region**
3. Name the failure mode explicitly — on a host or region that doesn't hold the weights,
   the worker downloads them while looking like a slow cold start, and the worker bills
   the whole time even though the download itself isn't billed
4. State the trade honestly: the cache is free, a network volume costs storage per month
   but the weights are guaranteed resident
5. Note that a network volume is **pinned to one data center**, so multi-region means one
   pre-loaded volume per DC
6. Offer a way to measure it rather than guessing — read weight-download time in the
   worker logs (`runpodctl serverless logs <endpoint-id>`); minutes rather than seconds
   means the cache is not carrying that model

## Assertions

- Recommends a network volume over the cache for this size + multi-region shape
- Says the cache is capped AND that a hit is per host/region
- Describes the invisible idle: worker up and billing while weights download
- Says the cache costs nothing and the volume costs storage
- Mentions the volume's single-data-center pinning for the multi-region case
- Does NOT claim `--model-reference` makes cold starts fast unconditionally
