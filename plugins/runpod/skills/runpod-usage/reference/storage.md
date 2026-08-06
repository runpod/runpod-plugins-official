# Where data lives on Runpod

Pick storage based on whether data must survive a stop, be shared across
machines, and where your compute runs. There are three layers.

## Default: prefer a network volume

**Unless the user says otherwise, put anything worth keeping on a network
volume** — models, datasets, checkpoints, environments, caches. It survives pod
stop/terminate and serverless scale-to-zero, is reusable across pods and
endpoints, and means expensive downloads happen once. Create it (and the volume's
data center) *before* the compute, then place the compute in that same DC.

Use the faster, non-persistent layers deliberately, not by default: container /
ephemeral disk for throwaway scratch, and pod volume disk when a single pod's data
doesn't need to outlive it. When in doubt, choose the network volume.

**One exception: model weights for GPU serverless.** If the model is on HuggingFace,
the host-side cache beats a volume — faster cold starts, no download billing, and no
data-center pin narrowing your GPU availability. See
[Getting a model to the worker](#getting-a-model-to-the-worker) below; the default
above is about datasets, checkpoints, and everything else worth keeping.

## The three layers

### Container / ephemeral disk

- Exists only while the container runs; **wiped when the pod stops or the worker
  scales down**. Fastest (locally attached).
- Everything a serverless handler writes goes here by default.
- On pods, editing/resetting a running pod also erases it — only `/workspace`
  survives (see below).
- Use for: OS, temp files, scratch, caches you don't need to keep.

### Volume disk (pods only)

- Persistent local disk mounted at `/workspace`. Retained across stop/restart,
  but **deleted when the pod is terminated**. Not shareable.
- Roughly $0.10/GB/month running, $0.20/GB/month while stopped. Can be increased
  (never decreased); optionally encrypted at rest.
- Use for: models, datasets, and checkpoints you reuse across sessions on one pod.

### Network volume (shared, portable)

- Persistent storage that lives **independently of any compute**. Attachable to
  multiple pods and to serverless endpoints; survives termination/scale-to-zero.
- NVMe-backed (roughly 200–400 MB/s, higher peak). Standard and High-Performance
  tiers. Pricing ~$0.07/GB/month for the first 1 TB, ~$0.05/GB/month beyond.
  - **Picking the tier:** the runpod-mcp `create-network-volume` tool takes
    `volumeType` (`STANDARD` | `HIGH_PERFORMANCE`); omit it for the data center's default.
    `runpodctl` has no tier flag, so from the CLI request **High-Performance** via the
    console (a ⚡ data center → toggle) or a raw v2 REST call (`POST
    https://v2-rest.runpod.io/v2/network-volumes` with `"type":"HIGH_PERFORMANCE"`); the tier
    is immutable after creation. High-Performance (~3× throughput / 4× IOPS) is worth it when
    I/O is the bottleneck — training, checkpointing, many small files. Launch: golden path
    [21 — storage tiers](../../runpod/golden-paths/21-storage-tiers.md); more:
    [high-performance storage docs](https://docs.runpod.io/storage/high-performance-storage).
- **Data-center-scoped** — a volume lives in one DC. See the constraint below.
- Mount paths:
  - Pods: mounts at `/workspace`, **replacing** the volume disk. Must be attached
    at pod creation and cannot be detached later.
  - Serverless: mounts at `/runpod-volume`.
- Use for: sharing models/datasets across workers or pods, and anything that must
  outlive a single machine.

### Data-center constraint (important)

A network volume is pinned to its data center, so any compute that mounts it must
be placed in that **same DC**. That narrows GPU availability. To improve
availability, attach multiple volumes from different DCs (one per DC) — but data
does **not** sync between them automatically; copy it yourself (S3 API /
runpodctl). **Do not write to one volume from multiple workers concurrently** — it can corrupt data.

## Getting a model to the worker

Four ways to make a model available; choose by size, privacy, and how often it
changes. On HuggingFace and running GPU serverless → **cached model**; your own
artifact → **Model Repository** (or a volume if you want to manage the files
yourself); need a reproducible image → **bake**.

| Option | How | Best when |
| --- | --- | --- |
| Bake into image | `COPY` model files, or download during `docker build` | Small/private models not on Hugging Face; fully reproducible images |
| Cached model (HF) | Attach a Hugging Face model to the endpoint (`--model-reference`); Runpod caches it host-side | Public/gated/private HF models; fastest cold starts, smaller images |
| Network volume | Pre-load the model onto a volume, mount it | Large shared models reused across many workers/pods |
| Model Repository | Upload your own artifacts with `runpodctl model add`; Runpod versions + distributes them | Your own/custom models not on HF, without image bloat or a DC-pinned volume |

Full comparison + commands: [`runpodctl/reference/model-caching.md`](../../runpodctl/reference/model-caching.md).

Trade-off: baking bloats the image and slows pulls; cached models and volumes
decouple the model from the image so it loads without re-downloading, cutting cold
starts. With cached models you are **not billed** for download time, and it works
for GPU serverless endpoints.

### HuggingFace cache directory

Runpod's cached-model feature stores models in the standard HF cache layout at:

```
/runpod-volume/huggingface-cache/hub/
```

Structure follows HF conventions — `models--{org}--{name}/snapshots/{hash}/`
(slashes in the model name become `--`), e.g.
`/runpod-volume/huggingface-cache/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/<hash>/`.
Anything that reads the HF cache (Transformers, vLLM, …) picks it up automatically.
Baking into a custom image instead? Point `HF_HOME` at your model dir.

## Accessing a network volume over S3

Runpod exposes network volumes through its **own** S3-compatible API (not AWS).
The bucket name is the network volume ID. Every request needs both a region and
an endpoint URL derived from the volume's data center:

```
--region <DC>  --endpoint-url https://s3api-<DC>.runpod.io/
```

Credentials (from Console → Settings → S3 API Keys):

- `AWS_ACCESS_KEY_ID` = your Runpod **user ID** (format `user_...`)
- `AWS_SECRET_ACCESS_KEY` = an **S3 API key** you generate (format `rps_...`, shown once)

```bash
aws s3 ls \
  --region CA-2 \
  --endpoint-url https://s3api-CA-2.runpod.io/ \
  s3://NETWORK_VOLUME_ID/
```

Path mapping: `/workspace/my-folder/file.txt` on a pod ==
`s3://NETWORK_VOLUME_ID/my-folder/file.txt` over S3. (See the `companion-clis`
skill for full AWS CLI usage; each volume on the Storage page shows a pre-filled
`aws s3` command with the right region/endpoint.)

## Quick decision guide

- Throwaway scratch during a run → container disk (nothing to configure).
- Keep data between sessions on one pod → volume disk (`/workspace`).
- Share models/data across workers or pods, or persist past termination →
  network volume — and put your compute in the volume's DC.
- Public/gated HF model on serverless → cached model, not a bake.
- Big files that blow past API payload limits → network volume or external S3;
  return references, not bytes.
