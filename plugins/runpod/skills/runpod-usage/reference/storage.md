---
concepts: [network-volume, global-volume, container-disk, pod-volume-disk, model-store, volume-cache]
---
# Where data lives on Runpod

Pick storage based on whether data must survive a stop, be shared across
machines, and where your compute runs. There are four layers.

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
the host-side cache needs no volume, no download billing, and no
data-center pin narrowing your GPU availability. See
[Getting a model to the worker](#getting-a-model-to-the-worker) below; the default
above is about datasets, checkpoints, and everything else worth keeping.

## The four layers

### Container / ephemeral disk

- Exists only while the container runs; **wiped when the pod stops or the worker
  scales down**. Local to the machine, so it's several times faster than a
  network-backed `/workspace` and the place for heavy I/O.
- Everything a serverless handler writes goes here by default.
- On pods, editing/resetting a running pod also erases it — only `/workspace`
  survives (see below).
- Use for: OS, package installs, builds, temp files, scratch, caches you don't need
  to keep. Size `--container-disk-in-gb` for them.

### Volume disk (pods only)

- Persistent storage mounted at `/workspace`. Retained across stop/restart, but
  **deleted when the pod is terminated**. Not shareable.
- Whether it's local depends on the data center. Where the data center offers
  network volumes, expect `/workspace` to be network-backed and several times
  slower than the container disk. Where it doesn't, `/workspace` may be local or
  network-backed. Check from inside the pod with `findmnt /workspace`: `fuse`
  means network-backed, `xfs` on a device means local. Either way, install
  packages outside `/workspace` (the container disk is always local) rather
  than picking a data center for disk speed.
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
    https://api.runpod.io/v2/network-volumes` with `"type":"HIGH_PERFORMANCE"`); the tier
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

### Global volume (any data center)

A **global volume** is storage that mounts into workloads in **any** data center, so it has
no data-center constraint. It is usage-billed, so it has no size: create it with just a
`name` (REST v2 `POST https://api.runpod.io/v2/global-volumes`, or MCP
`create-global-volume`). Accounts hold a capped number; a create past the cap is `400`.

- **Pods:** at most one global volume per pod, on GPU pods and on CPU pods (CPU pods
  through the API only), under `mounts.global`. It combines with a network volume but not
  with a pod volume disk (`400`). A CPU pod created through REST v2 or MCP without a
  `path` or a network volume mounts it at `/workspace-global` (for other cases the spec
  names no default); the console's deploy flow mounts it at `/workspace` when no network
  volume is attached.
  Read `mounts.global[0].path` back rather than assuming.
  The mount is fixed at create; only its `path` can change later.
- **Serverless:** at most one per endpoint, **GPU endpoints only** (a CPU endpoint gets
  `400`), under `mounts.global`, seen by workers at `/runpod-volume`. An endpoint carries
  network volumes or a global volume, not both.
- **Delete** removes the stored data and is refused with `409` while any pod (stopped pods
  count) or endpoint mounts it.
- **Limits (beta):** object-backed, so no file locking, atomic rename, hard links or
  permission bits. A template that installs a Python environment into `/workspace` (the
  official ComfyUI template, for one) cannot use it as its primary volume; mount it at a
  second path for model files. Changes made after a pod or worker starts may not be
  visible inside it, and concurrent writes to one file are last-write-wins.
- **Billing:** stored data plus requests: Class A (writes, creates, lists) $0.005 and
  Class B (reads, metadata lookups) $0.0005 per 1,000 requests. It is permanently deleted
  15 days after the account balance reaches $0.
- Use for: model weights and other read-mostly files shared across data centers; keep
  write-heavy work (training, checkpoints) on a network volume.

Source: the REST v2 spec (`GlobalVolume`, `Mounts`, `EndpointMountsInput`,
`/v2/global-volumes`) and the public docs
([global volumes](https://docs.runpod.io/storage/globalvolume/overview)); live-verified 2026-10-29 (name-only create, CPU pod mount, `409`
delete while mounted, `400` on a CPU endpoint, `204` delete after the pod was gone).
The GPU-endpoint mount and `/runpod-volume` path were not live-run; the REST default
`/workspace-global` on a CPU pod was live-verified 2026-11-02.

### Data-center constraint (important)

A network volume is pinned to its data center, so any compute that mounts it must
be placed in that **same DC**. That narrows GPU availability. To improve
availability, attach multiple volumes from different DCs (one per DC) — but data
does **not** sync between them automatically; copy it yourself (S3 API /
runpodctl). **Do not write to one volume from multiple workers concurrently** — it can corrupt data.
For read-mostly files needed in several data centers, a
[global volume](#global-volume-any-data-center) avoids the pin, within its limits.

## Getting a model to the worker

Four ways to make a model available; choose by size, privacy, and how often it
changes. On HuggingFace and running GPU serverless → **cached model**; your own
artifact → **Model Repository** (or a volume if you want to manage the files
yourself); need a reproducible image → **bake**.

| Option | How | Best when |
| --- | --- | --- |
| Bake into image | `COPY` model files, or download during `docker build` | Small/private models not on Hugging Face; fully reproducible images |
| Cached model (HF) | Attach a Hugging Face model to the endpoint (`--model-reference`); Runpod caches it host-side | Public/gated/private HF models; fastest load once the worker runs, smaller images. Worker start waits for a host that holds the model, so time the whole cold request |
| Network volume | Pre-load the model onto a volume, mount it; in your own handler, load through `VolumeCache` so it reads local disk | Large shared models reused across many workers/pods |
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
Official workers can already integrate this location. Custom workers must configure
the loader's cache directory or pass the matching local snapshot; an HF-compatible
library alone does not establish discovery. See the public
[cached-model guide](https://docs.runpod.io/serverless/endpoints/model-caching) and
[custom-handler example](https://docs.runpod.io/serverless/development/huggingface-models).

For a standard HF cache, `HF_HOME` names the root and `HF_HUB_CACHE` names its `hub`
directory. A baked cache might use `HF_HOME=/opt/models` and
`HF_HUB_CACHE=/opt/models/hub`. A plain directory of model files is different: pass that
directory directly to a loader that accepts it. Match the layout instead of setting
`HF_HOME` to an arbitrary model directory. See
[HF environment variables](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables).

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

- Throwaway scratch, package installs and builds → container disk (local; size it
  with `--container-disk-in-gb`).
- Keep data between sessions on one pod → volume disk (`/workspace`).
- Share models/data across workers or pods, or persist past termination →
  network volume — and put your compute in the volume's DC.
- Read-mostly models/files shared across data centers → global volume (no file locking
  or permission bits).
- Public/gated HF model on serverless → cached model, not a bake.
- Big files that blow past API payload limits → network volume or external S3;
  return references, not bytes.
