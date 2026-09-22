# Getting a model to a serverless worker

Four ways to make model weights available to a Runpod serverless worker. Pick by
where the weights come from, how large/private they are, and how often they change.

| Method | How | Best when | Cold start |
|--------|-----|-----------|-----------|
| **Bake into image** | `COPY`/download during `docker build`, push to a registry | small/private weights; fully reproducible image | fast (in image) but bloats pulls |
| **HF model cache** (`--model-reference`) | point the endpoint at a HuggingFace model URL; Runpod caches it host-side | the model is already on HuggingFace (public/gated/private) | fastest — host-cached, no download billing |
| **Network volume** | pre-load weights onto a DC-pinned volume, mount it | large weights reused across workers; you manage the files | fast once populated; volume is pinned to one data center |
| **Model Repository** (`runpodctl model`) | upload your **own** artifacts to Runpod-managed, versioned storage | private/custom models not on HuggingFace, without image bloat or a DC-locked volume | managed + host-distributed |

Rule of thumb: on HuggingFace → **HF cache**; your own artifact → **Model Repository**
(or a network volume if you want to manage the filesystem yourself); need a fully
reproducible image or system libs baked in → **bake**. Cache vs volume is a latency
call, not a cost call — see the next section before choosing.

## Cache or network volume — it is a latency call, not a cost call

**You are not billed for model download time, cache hit or miss.** Runpod's docs are
explicit: if no host already holds the model, "the system delays starting your workers
until the model is downloaded onto the machine where your workers will run, ensuring you
still won't be charged for the download time."

So the thing a cache miss costs you is **time to first response**, not money. And the
way it shows up is easy to misread: the job **sits in the queue** while the worker start
is held back for the download. From the outside that looks like a stuck or idle
endpoint, not a download. It isn't broken — it's the miss path.

### How the cache actually works

Three tiers, nearest first ([Runpod engineering
blog](https://www.runpod.io/blog/building-runpods-model-store)): **host-local disk** →
a **data-center-scoped network volume** → the **origin** (HuggingFace). The scheduler is
locality-aware — it prefers hosts that already have the model, or can reach it from a
nearby cache. On a miss, one worker downloads and then everyone in that data center
reads the shared copy. Runpod's own writeup says quota and eviction policy on that
DC-scoped tier are "still open problems, not solved ones", and that a full volume falls
back to origin downloads. Treat residency as best-effort, not a guarantee.

### Which to pick

| Situation | Use |
|---|---|
| **Latency-sensitive** — user-facing, tight SLA, or you scale into fresh regions often and can't absorb a first-request stall | **Network volume**, pre-loaded. Costs storage per month, but the weights are already there. |
| **Not latency-sensitive**, or the model isn't huge | **HF model cache** (`--model-reference`). Free, nothing to pre-load, and a hit is seconds. |
| Unsure | **Test both.** This is a measurable trade, not a rule — deploy each and time the cold start on your model, in your region. |

Two constraints that push large models toward a volume: the cache tiers have finite
capacity with no published quota, and a network volume is **pinned to one data center**,
so multi-region means one pre-loaded volume per DC (golden path
[10](../../runpod/golden-paths/10-multi-region-ha-serverless.md)).

To measure it, watch the worker logs on a cold start in a fresh region (`runpodctl
serverless logs <endpoint-id>`, or the MCP `stream-worker-logs`). Weight-download time in
**minutes** rather than seconds means that region isn't carrying the model for you.

### Regional availability — unknown, don't guess

**Runpod does not publish a list of data centers where the model cache is enabled.** The
[cached models docs](https://docs.runpod.io/serverless/endpoints/model-caching) state no
regional restriction, and the engineering blog only says the shared tier is
"scoped per datacenter". Third-party posts claim it is region-limited; none cite a
source. **Do not state a supported-region list to a user.**

The closest live proxy is which data centers offer network volumes at all, since the
shared cache tier is built on that per-DC storage. Read it, don't memorize it:

```bash
# MCP: list-data-centers  →  networkVolumeTypes
```

Snapshot 2026-09-22 — **17 of 33** data centers report a `networkVolumeTypes` value:
`AP-JP-1`, `CA-MTL-3`, `CA-MTL-4`, `EU-FR-1`, `EU-NL-1`, `EU-RO-1`, `EUR-IS-1`,
`EUR-IS-3`, `EUR-NO-1`, `EUR-NO-2`, `US-CA-2`, `US-CO-1`, `US-IL-1`, `US-MO-2`,
`US-NC-2`, `US-TX-3`. This is **a proxy, not the model-cache list** — say so if you use
it. If a user needs certainty for a specific region, the honest answer is to deploy there
and measure the first cold start.

### Documented limits

- **One cached model per endpoint** ([docs → Current
  limitations](https://docs.runpod.io/serverless/endpoints/model-caching)). `runpodctl`
  accepts `--model-reference` repeatedly, so the CLI will take more than one — the
  platform limit is the binding one.
- **All quantizations get downloaded.** If a HF repo holds several (4-bit AWQ, 8-bit
  GPTQ, …), the system currently pulls them all; you can't select one yet.
- The feature is **beta**.

## HF model cache — `--model-reference`

Attach a HuggingFace model to an endpoint by full URL with a ref; Runpod caches it on
the host so the worker loads it directly — no bake, no volume.

```bash
runpodctl serverless create --template-id <id> --gpu-id "NVIDIA GeForce RTX 4090" \
  --model-reference https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct:main
```

- The trailing `:main` is the branch/tag/revision.
- Weights land in the standard HF cache dir `/runpod-volume/huggingface-cache/hub/`
  (`models--{org}--{name}/snapshots/{hash}/`), so anything that reads the HF cache
  (Transformers, vLLM, …) picks it up automatically.
- The CLI flag is repeatable, but the platform currently allows **one cached model per
  endpoint** (docs → Current limitations).
- Works with `--template-id` **and** `--hub-id`, but **GPU only** (`--compute-type GPU`).
- **Requires runpodctl v2.4.0+.** Check `runpodctl version`; the Homebrew tap can lag —
  prefer the [GitHub releases](https://github.com/runpod/runpodctl/releases) binary.
- Gated/private HF models: provide an `HF_TOKEN` (endpoint env var).

You are **not billed for download time** — hit or miss. Cold starts drop to seconds on
a host that already holds the model; on one that doesn't, worker start is held back
until the download finishes, so the job sits in the queue longer. See
[Cache or network volume](#cache-or-network-volume--it-is-a-latency-call-not-a-cost-call).

## Model Repository — `runpodctl model`

Runpod-managed **storage + registry for your own model artifacts**. Upload weights once;
Runpod stores, versions, and distributes them to workers — a first-class model object
with a name, versions, metadata, and a status lifecycle (not just a file on a disk).

```bash
runpodctl model list                                  # list your models
runpodctl model list --all                            # include models you don't own
runpodctl model list --name "llama"                   # filter by name
runpodctl model list --provider "meta"                # filter by provider
runpodctl model add --name "my-model" --model-path ./model   # upload a local model directory
runpodctl model remove --name "my-model" --owner <owner>     # remove a model
```

`model add` runs a **multipart upload session** (built for large weights) — the live
`runpodctl model add --help` exposes `--create-upload`, `--part-size`, `--file-size`,
`--file-name`, `--content-type`, `--metadata key=value`, `--model-status`,
`--version-status`, and `--credential-reference`/`--credential-type` (for pulling from a
private source). Run it before relying on exact syntax — it is authoritative.

**Coming from a baked-in model?** The easiest migration is to stop `COPY`-ing weights
into the image and instead `runpodctl model add --model-path <the same dir you used to
COPY>`, then reference the uploaded model from the endpoint. This shrinks the image and
lets you version the weights independently of the code.

**vs a network volume:** a network volume is a raw filesystem you manage and is **pinned
to one data center** (workers must run there); the Model Repository is managed, versioned,
and host-distributed, so it isn't locked to a single DC. Use a volume when you want direct
filesystem control or are already populating one; use the Model Repository for a
hands-off, versioned artifact.

> **Runtime-load path — don't guess.** The command surface above (`runpodctl model add`)
> is from live `runpodctl --help` and is accurate for *uploading*. But how a worker
> *references an uploaded Model Repository artifact at runtime* is **not publicly
> documented yet** — if asked for exact runtime-load steps for a `runpodctl model add`
> artifact, say it isn't publicly documented and don't invent a path.
>
> This is distinct from the HF **model-caching** feature (the `--model-reference` flag /
> the endpoint "Model" field), whose runtime path **is** documented: the model lands in
> `/runpod-volume/huggingface-cache/hub/` and the handler resolves the local snapshot from
> there (load offline with `HF_HUB_OFFLINE=1`). See golden path 20 and the official
> example `runpod-workers/model-store-cache-example`.
