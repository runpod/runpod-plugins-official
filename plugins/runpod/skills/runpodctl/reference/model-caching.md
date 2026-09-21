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
reproducible image or system libs baked in → **bake**. But check the size first — see
the next section.

## Size first: cache or network volume

The HF cache is the right default *because it costs nothing* — you don't pay for the
cached copy and you aren't billed for download time. It has two limits that decide
whether it is still the right call for a given model:

- **The per-host cache is finite.** It holds a working set, not your whole model
  library. A very large model, or several models attached to one endpoint, will not all
  stay resident.
- **A cache hit is per host, per region.** The speedup only happens on a host that
  already holds those weights. On a host or region that doesn't, the worker has to pull
  the model before it can serve.

That second point is the expensive one, and it is **invisible in the endpoint UI**: the
worker looks like it is starting normally while it sits there downloading. You are
paying for that worker the whole time, and nothing in the job status says "downloading"
— it just looks like a very long cold start. The bigger the model, the more often you
eat it, because large weights are evicted from host caches sooner and are less likely to
be pre-warmed in a region you scale into.

**So:**

| Model size vs the cache | Use |
|---|---|
| Comfortably small — fits and stays resident | **HF model cache** (`--model-reference`). Free, no download billing, seconds-fast cold start. |
| Large enough that it won't reliably stay cached, or you're scaling across regions | **Network volume**, pre-loaded once. Costs storage per month, but the weights are *there* — no per-region re-download, no idle worker burning GPU time waiting on a pull. |

The trade is plain: the cache is free but best-effort and capped; a network volume costs
money but is guaranteed-resident — and **pinned to one data center**, so multi-region
means one pre-loaded volume per DC (see golden path
[10](../../runpod/golden-paths/10-multi-region-ha-serverless.md)).

If you can't tell which side of the line a model falls on, watch the worker logs on the
first cold start in a fresh region (`runpodctl serverless logs <endpoint-id>`, or the MCP
`stream-worker-logs`). Weight-download time measured in **minutes** rather than seconds
means the cache is not carrying that model — move it to a volume.

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
- Repeatable — pass it multiple times to attach multiple models.
- Works with `--template-id` **and** `--hub-id`, but **GPU only** (`--compute-type GPU`).
- **Requires runpodctl v2.4.0+.** Check `runpodctl version`; the Homebrew tap can lag —
  prefer the [GitHub releases](https://github.com/runpod/runpodctl/releases) binary.
- Gated/private HF models: provide an `HF_TOKEN` (endpoint env var).

You are **not billed for download time** with the cache, and cold starts drop to
seconds **on a host that already holds the model**. On one that doesn't, the worker
pulls the weights first — the download itself isn't billed, but the worker is up and
billing while it waits, and nothing in the job status shows why. See
[Size first](#size-first-cache-or-network-volume).

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
