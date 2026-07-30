# GPU selection

How to pick a GPU: size VRAM to the model first, then choose a tier/pool, then
worry about cloud, availability, and placement.

## Step 1: size VRAM to the model

VRAM is the usual bottleneck. Rough rules:

- **LLM inference (fp16):** ~**2 GB of VRAM per billion parameters**, plus headroom
  for the KV cache / context and activations. A 7B model ≈ ~14 GB, 13B ≈ ~26 GB,
  70B ≈ ~140 GB (needs multiple GPUs).
- **Quantization cuts this a lot.** A 4-bit quantized model needs roughly a quarter
  of the fp16 weight memory — e.g. a 4-bit 70B fits in ~35 GB.
- **Training / fine-tuning** needs far more than inference — weights + gradients +
  optimizer state + activations, often ~4x the inference figure for full fine-tuning.
  LoRA/QLoRA reduce this substantially. Memory bandwidth also matters here.
- **Image models (SDXL, Flux):** ~8 GB minimum, but 16–24 GB gives headroom for
  larger batches and LoRA training.

Always leave headroom above the raw weight size. When unsure, estimate with the
Hugging Face Model Memory calculator (`huggingface.co/spaces/hf-accelerate/model-memory-usage`)
or "Can it run LLM?" (`huggingface.co/spaces/Vokturz/can-it-run-llm`).

## Step 2: which GPU for an N-billion-param LLM (heuristic)

Sizes assume fp16 inference; quantize to drop a tier or two.

| Model size | VRAM (fp16) | Reasonable pick |
|-----------|-------------|-----------------|
| ≤ 7B | ~14 GB | `ADA_24` (RTX 4090) or `AMPERE_24` (L4/A5000/3090) |
| 13B | ~26 GB | `ADA_32_PRO` (RTX 5090) or `AMPERE_48` / `ADA_48_PRO` |
| 30–34B | ~60–70 GB | `AMPERE_80` (A100) or `ADA_80_PRO` (H100) |
| 70B | ~140 GB | 2x 80 GB, or one `HOPPER_141` (H200) / `BLACKWELL_180` (B200) |
| > 70B | 200 GB+ | multi-GPU 80 GB+, or Blackwell / H200 with `gpu_count` > 1 |

## Step 3: GPU tiers and pools

A **GPU pool** groups interchangeable GPUs by VRAM tier. Requesting a pool lets
Runpod pick any available GPU in that tier (better availability); pinning an exact
GPU type gives determinism but can be throttled when supply is tight. Pool names are
used by Serverless configs, the Runpod Hub, flash's `GpuGroup`, and the GraphQL API.

Pool reference (source of truth: `skills/flash/reference/api.md`):

| Pool | GPUs | VRAM |
|------|------|------|
| `ANY` | any available | varies |
| `AMPERE_16` | RTX A4000 / A4500 / RTX 4000 Ada / RTX 2000 Ada | 16 GB |
| `AMPERE_24` | RTX A5000 / L4 / RTX 3090 | 24 GB |
| `ADA_24` | RTX 4090 | 24 GB |
| `ADA_32_PRO` | RTX 5090 | 32 GB |
| `AMPERE_48` | A40 / RTX A6000 | 48 GB |
| `ADA_48_PRO` | RTX 6000 Ada / L40 / L40S | 48 GB |
| `AMPERE_80` | A100 (PCIe / SXM4) | 80 GB |
| `ADA_80_PRO` | H100 (PCIe / HBM3 / NVL 94 GB) | 80 GB+ |
| `HOPPER_141` | H200 | 141 GB |
| `BLACKWELL_96` | RTX PRO 6000 Blackwell | 96 GB |
| `BLACKWELL_180` | B200 | 180 GB |

Note: Serverless GPU config wants **pool IDs** (e.g. `ADA_24`), while Pod creation
and `runpodctl --gpu-id` use **GPU type IDs** (e.g. `NVIDIA A40`) — different
identifier spaces. The full per-model list (with exact display names and memory) is
in `docs/references/gpu-types.mdx`.

Rule of thumb: prefer **fewer high-end GPUs over more low-end GPUs**. One 80 GB card
usually beats two 40 GB cards for a model that fits.

## Step 4: Secure vs Community Cloud

- **Secure Cloud** — T3/T4 data centers, high redundancy, stable public IPs. Use for
  production and sensitive data. Standard pricing.
- **Community Cloud** — vetted peer-to-peer hosts, cheaper, variable reliability;
  public IPs can change on migrate/restart. Good for cost-sensitive, tolerant work.
  (No new hosts are being onboarded; existing capacity remains.)

## Step 5: availability and multi-GPU selection

`runpodctl gpu list` reports on-demand `securePricePerHr` / `communityPricePerHr` per
GPU (explicitly `null` when that cloud doesn't offer it) plus a
`dataCenterAvailability[]` breakdown, so read cost and per-region stock straight from
it rather than assuming a lower tier is cheaper. Top-level `stockStatus` is only the
best status across DCs — use the per-DC breakdown when placement matters (`runpodctl
datacenter list` gives the same view from the DC side). Two scope limits: those are **pod
on-demand** rates (serverless bills per request-second), and the per-DC breakdown doesn't
say *which cloud* has the stock, so cost and placement are two separate reads rather than
one ranked list.

GPU supply fluctuates by tier and region. To avoid throttling:

- **List multiple GPU types / pools in priority order.** If the first choice is
  unavailable, Runpod falls back to the next. On Serverless you can specify up to
  three, in priority order.
- For endpoints with **5+ workers**, Runpod spreads workers across your prioritized
  pools (most on the primary), reducing throttling. With fewer than 5 workers, all
  use the highest-priority available type.
- (flash caveat: auto GPU switching by supply only kicks in when max workers ≥ 5.)
- Use `gpu_count` > 1 (Serverless) / multi-GPU Pods when a model exceeds a single
  card's VRAM.

## Step 6: data-center placement

- Restricting an endpoint or Pod to specific data centers **shrinks the available
  GPU pool** — allow all regions for maximum availability unless you have a reason
  not to.
- Reasons to pin a region: lower latency to your users, data-residency/compliance,
  or co-locating with a **network volume** (a volume ties the workload to its data
  center). Some features (e.g. global networking) are only in a subset of regions.
- Regions span US (CA, GA, IL, KS, NC, TX, WA, etc.), EU (CZ, RO, IS, NO, SE, FR,
  NL), and others. See `docs/pods/networking.mdx` for the current data-center list
  and `companion-clis/SKILL.md` for datacenter IDs used with S3.
