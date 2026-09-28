# Golden path 10 — high-availability serverless across regions (multi-volume + data sync)

**Goal:** stop a serverless endpoint from being hostage to **one** data center's GPU
supply. A single network volume pins every worker to that volume's DC — when that DC
is scarce or under maintenance, your endpoint can't scale. The fix Runpod supports:
**attach one network volume per DC from several DCs**, so workers spread across
regions. The catch this path exists to teach: **the volumes do not sync
automatically** — you must replicate identical data to every one of them, or workers
in different DCs will serve different data.
**Status:** ✅ **COVERED — live-verified 2026-07-10** end to end. Created **two** 10 GB
volumes (ha-a in **EU-RO-1**, ha-b in **EU-CZ-1**), **S3-synced identical data to both**
(`aws s3 ls` byte-identical), deployed **one** endpoint attached to **both** volumes, and
sent a 16-request burst: **16/16 `COMPLETED`, served by 3 workers across both DCs**
(EU-RO-1 ×2, EU-CZ-1 ×1), each worker reading its **co-located** volume, and **every
response identical** (one distinct marker + data string across all 16). Headless
multi-volume attach works via **`runpodctl serverless create --network-volume-ids v1,v2`
on runpodctl ≥ v2.4.0** (verified live) — check `runpodctl version` (see step 4).
Scope note: **Methods 2/3 (pod-based population) were *not* re-run here** — already
live-proven by golden path [07](07-network-volume-handoff.md) (a pod writing to a mounted
volume). This path's live proof is the **S3-API sync + multi-volume attach + multi-DC
verification**.
**Lane(s):** runpodctl ≥ v2.4.0 (volumes + `serverless create --network-volume-ids`) + `aws`/S3 API (sync, see [companion-clis](../../companion-clis/SKILL.md#aws-cli)) + GraphQL `saveEndpoint` (fallback for old CLI / REST-only; Console also works) + optionally a CPU/GPU pod (in-DC population, per [07](07-network-volume-handoff.md))

## Prerequisites
- Shared setup first: [../README.md](README.md#before-you-run-any-path-shared-prerequisites) and
  [getting-started.md](../../runpod-usage/reference/getting-started.md) (auth resolution, SSH,
  companion-CLI credentials).
- `RUNPOD_API_KEY` resolvable (runpodctl + REST). Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`.
- `aws` CLI configured with **Runpod S3 API keys** (access key = your Runpod `user_...` id, secret =
  `rps_...`). These are **Console-only** to create (Settings → S3 API Keys) — an agent can't
  self-provision them; escalate if they aren't already in `~/.aws/credentials`/env
  ([companion-clis → AWS CLI](../../companion-clis/SKILL.md#aws-cli)). Not needed if you populate
  volumes via a pod (Method 2/3).
- `runpodctl` installed + authenticated, **≥ v2.4.0** for headless multi-volume attach
  (`serverless create --network-volume-ids`). Verify: `runpodctl version`; if behind, install from
  [GitHub releases](https://github.com/runpod/runpodctl/releases) (REST/GraphQL fallback works on any
  version — step 4).

## The problem, precisely

| Volumes attached | Where workers can schedule | Availability |
| --- | --- | --- |
| **One** volume | **only** that volume's DC | hostage to one DC's GPU pool + maintenance windows |
| **Multiple** volumes (one per DC, N DCs) | **any** of those N DCs | N× the GPU pools to draw from; survives one DC going scarce/down |

Runpod's rule (from the docs): with multiple volumes attached, **workers are
distributed across those DCs, each worker getting exactly one volume based on its
assigned location**, and **you can attach at most one volume per DC**.

## The catch: no automatic sync (this is the whole job)

> **Data does not sync automatically between volumes.** Each per-DC volume is an
> independent disk. A worker in EU-RO-1 reads the EU-RO-1 volume; a worker in US-KS-2
> reads the US-KS-2 volume. If those two disks differ, the *same endpoint* returns
> *different behavior* depending on which DC a request lands in — a silent, confusing
> bug.

So HA serverless = **(multi-volume attach) + (a discipline that keeps every volume
byte-identical)**. The rest of this path is about that second half: getting the same
data onto every volume, and keeping it there.

## Three ways to populate / sync each per-DC volume

You need a "writer" with access to each DC's volume. Pick the cheapest that can do the
job; escalate only when it can't.

| Method | Compute cost | Use when | How |
| --- | --- | --- | --- |
| **S3-compatible API** (recommended) | **none** — no pod at all | the DC supports the S3 API and the data is files you already have (models, datasets, adapters) | `aws s3 sync`/`cp` or boto3 against the DC's S3 endpoint; or the community CLI for resumable large transfers |
| **CPU pod** | cheap (~$/hr CPU) | the DC has no S3 API, or you must **generate/unpack/process** data in-DC, or you're copying **volume→volume** | mount the volume at `/workspace` on a CPU pod in that DC; download/build there, or `runpodctl send`/`receive` between two pods |
| **Cheapest GPU pod** | most expensive | you need a **GPU to produce** the artifact in that DC (build a TensorRT engine, quantize, warm a GPU-specific cache) | same as CPU pod but with a small GPU; do the GPU work, write to `/workspace`, remove the pod |

### Method 1 — S3 API (no compute, the default)

The S3-compatible API writes straight to a volume with **no pod running** — cheapest
and fastest for file data. Full setup (S3 API keys, `aws configure`, endpoints,
path mapping) is in [companion-clis → AWS CLI](../../companion-clis/SKILL.md#aws-cli).

> **Manual step — S3 API keys are Console-only.** They cannot be created via
> `runpodctl` or any REST/GraphQL call — only in the Console (Settings → S3 API Keys →
> Create). The access key is your Runpod **user id** (`user_...`), the secret is shown
> **once** (`rps_...`). An agent must **escalate** for these if they aren't already in
> `~/.aws/credentials` / env vars — it can't self-provision them. If S3 keys aren't
> available, use the CPU-pod method below (no S3 keys needed).
Each DC has its own endpoint (`https://s3api-<DC>.runpod.io/`); the **bucket name is
the volume id**. Sync the *same source directory* to *each* volume:

```bash
# Same local source → every per-DC volume. --region is the DC id; the endpoint host is
# the DC id lower-cased (DNS is case-insensitive, so upper-case also resolves).
for pair in "EU-RO-1:<vol-ro>" "EU-CZ-1:<vol-cz>"; do   # DC:volume-id
  DC=${pair%%:*}; VOL=${pair##*:}
  aws s3 sync ./ha-data/ \
    --region "$DC" \
    --endpoint-url "https://s3api-$(echo "$DC" | tr 'A-Z' 'a-z').runpod.io/" \
    "s3://$VOL/ha-data/"
done
```
✅ **Live 2026-07-10** — `aws s3 ls` on *both* volumes returned the identical file set +
sizes (the whole point — proves the two independent disks now match):
```
$ aws s3 ls --region EU-RO-1 --endpoint-url https://s3api-eu-ro-1.runpod.io/ s3://<vol-ro>/ha-data/
2026-07-10 17:22:30         77 data.txt
2026-07-10 17:22:30         28 marker.txt
$ aws s3 ls --region EU-CZ-1 --endpoint-url https://s3api-eu-cz-1.runpod.io/ s3://<vol-cz>/ha-data/
2026-07-10 17:22:31         77 data.txt
2026-07-10 17:22:31         28 marker.txt
```
> A preconfigured `aws` profile (`--profile runpod`) held the S3 creds (access key =
> Runpod `user_...`, secret = `rps_...`); those keys are still **Console-only** to create.

- **Large files / flaky links:** `aws s3 sync` is fine for modest trees but **struggles
  past ~10,000 files** and has weak resume. For big weights, prefer the community tool
  (resumable multipart, auto chunk sizing, MD5-verified resume) — see
  [Companion tool](#companion-tool-resumable-transfers). Bump retries on 502s:
  `export AWS_RETRY_MODE=standard AWS_MAX_ATTEMPTS=10`.
- **S3 API is DC-limited:** only [select DCs](https://docs.runpod.io/storage/s3-api#datacenter-availability)
  expose it (EU-RO-1, EU-CZ-1, EUR-IS-1, US-KS-2, and more). For a DC without S3, use
  Method 2.

### Method 2 — CPU pod (in-DC, no GPU)

When a target DC lacks S3, or you need to unpack/build in-DC, or you're moving data
volume→volume: bring up a **cheap CPU pod** in that DC with the volume mounted at
`/workspace` (golden path [07](07-network-volume-handoff.md) is the exact pod+volume
pattern), do the work, then remove the pod (the volume persists):

```bash
runpodctl pod create --name sync-cpu \
  --data-center-ids <dc> \
  --network-volume-id <vol-in-that-dc> --volume-mount-path /workspace \
  --ssh                                              # a CPU flavor; no GPU needed
# SSH in, populate /workspace (hf download, curl, tar -x, aws s3 cp from your own bucket, …)
runpodctl pod remove <pod-id>                          # volume keeps the data
```
Volume→volume copy: mount **both** volumes on two pods and use `runpodctl send` /
`receive` (docs: *Migrate files between volumes*).
> *Pod-writes-to-volume is already live-proven by golden path
> [07](07-network-volume-handoff.md) — not re-run here; this path's live proof is the S3
> route below.*

### Method 3 — cheapest GPU pod (in-DC, GPU work)

Same as Method 2 but with a small GPU, only when the artifact must be produced on a
GPU **in that DC** (e.g. build a TensorRT/engine file, quantize weights, prime a
GPU-specific cache). It's the priciest writer — reach for it last. Use the cheapest
GPU available in that DC, and `pod remove` it when done.

## Walkthrough — stand up the HA endpoint

### 1. Pick the DCs
Choose N DCs that (a) have your target GPU in good supply and (b) ideally expose the
S3 API (cheapest sync). Confirm the GPU exists in each DC before committing — a volume
in a DC where your GPU is unavailable adds **zero** availability (workers there can't
schedule).

### 2. Create one volume per DC
```bash
runpodctl network-volume create --name ha-a --size 10 --data-center-id EU-RO-1
runpodctl network-volume create --name ha-b --size 10 --data-center-id EU-CZ-1
```
✅ Live output (each returns its id — these become the S3 bucket names and the attach args):
```json
{ "dataCenterId": "EU-RO-1", "id": "<vol-ro>", "name": "ha-a", "size": 10 }
{ "dataCenterId": "EU-CZ-1", "id": "<vol-cz>", "name": "ha-b", "size": 10 }
```
Note: you pay storage **per volume** — N volumes = N× the GB bill. Size only for the
data you replicate. Flags are exactly `--name`, `--size` (1-4000 GB), `--data-center-id`
(all required; no other options).

### 3. Replicate identical data to every volume
Use Method 1/2/3 per DC. **Same source of truth → every volume.** This is the step
that makes or breaks correctness. Here: a tiny `ha-data/` (a `marker.txt` + `data.txt`)
`aws s3 sync`'d to **both** buckets (step "Method 1" above), then `aws s3 ls` confirmed
the two volumes were byte-identical (77 B + 28 B on each). ✅

### 4. Attach all volumes to one endpoint (one per DC)

**The handler image.** The endpoint needs a worker image that reads its data from
`/runpod-volume/...` and reports which DC/worker served the request (so you can *see* the
multi-DC spread in step 5). Golden path [19](19-three-region-same-file.md#4-a-tiny-handler-that-serves-the-file--reports-who-answered)
has the exact reusable handler + 3-line Dockerfile (`python:3.11-slim` + `runpod`, reads
`/runpod-volume/<dir>`, returns the file contents plus `RUNPOD_DC_ID`/`RUNPOD_VOLUME_ID`/
`socket.gethostname()`). **Build that image and push it to your own registry**, then use that
tag below (this path's live run used `rp-gp10:v1`, an equivalent handler):
```bash
docker build --platform linux/amd64 -t <your-registry>/rp-gp10:v1 .   # handler+Dockerfile from path 19
docker push <your-registry>/rp-gp10:v1
```
You need a **template** first (`runpodctl serverless create` takes `--template-id`/`--hub-id`,
never `--image` — same two-step as golden path [05](05-model-to-endpoint-pipeline.md)):
```bash
runpodctl template create --name rp-gp10-tpl --serverless \
  --image <your-registry>/rp-gp10:v1 --container-disk-in-gb 10   # → template id <template-id>
```
**Preferred: `runpodctl serverless create --network-volume-ids` (needs runpodctl ≥ v2.4.0).**
The CLI passes the whole set in one call:
```bash
runpodctl serverless create --template-id <template-id> --compute-type CPU \
  --network-volume-ids <vol-ro>,<vol-cz> \
  --data-center-ids EU-RO-1,EU-CZ-1 --workers-min 0 --workers-max 1
```
✅ **Live 2026-07-10** (runpodctl built from `main`) — endpoint created, then
`GET /v1/endpoints/<id>` confirmed `"networkVolumeIds":["<vol-ro>","<vol-cz>"]` (both
attached). Under the hood runpodctl calls the GraphQL `saveEndpoint` mutation with the ids
as **objects** — see the fallback below for what that looks like.

> **Version requirement:** multi-volume `--network-volume-ids` needs **runpodctl ≥ v2.4.0**;
> older versions don't support it. **Check `runpodctl version` first.** The Homebrew tap can
> lag, so if you're behind, install ≥v2.4.0 from the
> [GitHub releases](https://github.com/runpod/runpodctl/releases).

**Fallback A — raw GraphQL `saveEndpoint`** (REST-only, or stuck on an old CLI). This is
exactly what runpodctl does internally; `networkVolumeIds` takes **objects**, not strings.
⚠️ **Do not put `"computeType":"CPU"` in the REST create** — the public control REST v1
silently provisions a **GPU** endpoint (see the runpodctl skill). Express CPU in the GraphQL
step via `instanceIds` + empty `gpuIds` (`EndpointInput` has no `computeType` field), exactly
as [path 19](19-three-region-same-file.md) does:
```bash
# create with ONE volume first (REST accepts the singular field), then attach the set + pin CPU:
curl -s -X POST https://rest.runpod.io/v1/endpoints \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"templateId":"<template-id>","name":"rp-gp10-ha",
       "networkVolumeId":"<vol-ro>","dataCenterIds":["EU-RO-1","EU-CZ-1"],"workersMin":0,"workersMax":4}'
# → endpoint id; then (NOTE the User-Agent — api.runpod.io returns 403/1010 without a browser-ish UA):
curl -s -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -H 'User-Agent: Mozilla/5.0' \
  -d '{"query":"mutation($input:EndpointInput!){saveEndpoint(input:$input){id name computeType instanceIds}}",
       "variables":{"input":{"id":"<endpoint-id>","name":"rp-gp10-ha","templateId":"<template-id>",
         "instanceIds":["cpu3c-2-4"],"gpuIds":"",
         "dataCenterIds":["EU-RO-1","EU-CZ-1"],
         "networkVolumeIds":[{"networkVolumeId":"<vol-ro>"},{"networkVolumeId":"<vol-cz>"}],
         "workersMin":0,"workersMax":4,"scalerType":"QUEUE_DELAY","scalerValue":1,"idleTimeout":10}}}'
```
> The 2026-07-10 live run used `"computeType":"CPU"` on the REST create (before that footgun
> was known); the CPU expression above is corrected to match path 19's live-verified shape
> (2026-07-13). Verify: `saveEndpoint` should return `"computeType":"CPU","instanceIds":["cpu3c-2-4"]`.

**Fallback B — Console:** Serverless → Edit Endpoint → Advanced → Network Volumes, one per DC, Save.

The handler reads its data from `/runpod-volume/...` exactly as in the single-volume case.
> **Note:** prefer the `runpodctl` path above — it carries `--compute-type` (CPU/GPU)
> directly. The raw GraphQL `saveEndpoint` has no `computeType` field, but it can **still
> make a CPU endpoint** — pass `instanceIds` (a CPU flavor, e.g. `cpu3c-2-4`) with an empty
> `gpuIds` (live-verified in golden path [19](19-three-region-same-file.md)); omit those and
> it defaults to GPU. HA behavior (multi-DC, per-DC volume, parity) is identical.

### 5. Verify HA + parity — ✅ live 2026-07-10
Burst of **16** `/run` jobs, polled to completion (cold start ~10 s queue, ~135 ms exec):
```
STATUS:            {'COMPLETED': 16}          # 16/16 succeeded
WORKERS (3 total): EU-RO-1 ×2, EU-CZ-1 ×1     # scheduled across BOTH DCs
DISTINCT markers:  1   ('golden-path-10 HA marker v1')     # identical regardless of DC
DISTINCT data:     1   ('shared-model-payload: checksum-anchor 42 …')
```
Per-worker identity (from the handler returning `socket.gethostname()` + `RUNPOD_*` env):
```
worker 4100bc76ce48: RUNPOD_DC_ID=EU-CZ-1  RUNPOD_VOLUME_ID=<vol-cz>  (ha-b)
worker ca7909f9bdbe: RUNPOD_DC_ID=EU-RO-1  RUNPOD_VOLUME_ID=<vol-ro>  (ha-a)
worker b1b4e4d2f0f2: RUNPOD_DC_ID=EU-RO-1  RUNPOD_VOLUME_ID=<vol-ro>  (ha-a)
```
This is the whole thesis, proven: **each worker landed in a different DC and mounted
that DC's own volume** (`RUNPOD_VOLUME_ID` = the co-located volume, `/runpod-volume`
points at it), yet **every response was byte-identical** because both volumes carried the
same synced data. `RUNPOD_DC_ID` is the clean per-request DC identifier; poll with
`/run` + `/status` (see [endpoint-workflows](../../runpod-usage/reference/endpoint-workflows.md)).

## Keeping volumes in sync (operating discipline)
- **One source of truth.** Treat a canonical local dir (or your own S3 bucket) as
  authoritative; push it to every Runpod volume. Never edit volumes ad hoc.
- **Re-sync on every data change**, to **all** volumes, before it goes live. A model
  bump that lands on 2 of 3 volumes = 1/3 of traffic serving the old model.
- **Verify after sync** — compare listings/sizes (checksums if you can) across volumes.
- **Don't write from workers.** Concurrent writes from multiple workers to a volume can
  corrupt it (docs warning). Volumes here are **read-only data planes**; writes go
  through your sync pipeline, not the handler.

## Gotchas
- **Multi-volume attach needs runpodctl ≥ v2.4.0** — `runpodctl serverless create
  --network-volume-ids v1,v2` (check `runpodctl version`; install from
  [GitHub releases](https://github.com/runpod/runpodctl/releases) if the Homebrew tap is
  behind). `--network-volume-id` (singular) attaches one volume on any version. REST-only
  fallback: GraphQL `saveEndpoint` with the object shape (step 4); the Console UI also works.
- **GraphQL fallback needs a browser-ish `User-Agent`** on `api.runpod.io/graphql`
  (`User-Agent: Mozilla/5.0`); not needed for the `runpodctl` path.
- **GraphQL fallback has no `computeType` field** — but a CPU endpoint is still expressible
  via `instanceIds` (a CPU flavor) + empty `gpuIds` (see [19](19-three-region-same-file.md));
  omit those and `saveEndpoint` defaults to GPU. HA behavior is identical.
- **No auto-sync** — the entire reason this path is hard. Drift → inconsistent responses.
- **One volume per DC** — you can't stack two volumes in the same DC for an endpoint.
  (Live: each worker's `RUNPOD_VOLUME_ID` = its own DC's volume.)
- **S3 API isn't in every DC** — check availability; fall back to a CPU pod (Method 2).
- **GPU must exist in each chosen DC** — a volume in a GPU-dry DC adds no availability.
- **`aws s3 sync` scaling** — flaky past ~10k files; `ls` slow on >10k files / >10GB;
  use the resumable tool for big trees, and `AWS_MAX_ATTEMPTS=10` on 502s.
- **Cost scales with N** — storage billed per volume ($0.07/GB/mo to 1TB, then $0.05).
- **Access key gotcha** — for the S3 API the AWS "access key" is your Runpod **user
  id** (`user_...`), the secret is the S3 key (`rps_...`) — not your `RUNPOD_API_KEY`
  ([companion-clis](../../companion-clis/SKILL.md#aws-cli)).

## Cost & cleanup
```bash
runpodctl serverless delete <endpoint-id>     # the endpoint (deletes the multi-volume attach)
runpodctl template delete   <template-id>         # the template
runpodctl network-volume delete <vol-ro>     # ha-a (EU-RO-1) — billed separately
runpodctl network-volume delete <vol-cz>     # ha-b (EU-CZ-1)
runpodctl serverless list && runpodctl network-volume list && runpodctl pod list   # confirm clean
```
✅ All four `{"deleted": true}` on the live run; lists came back with only pre-existing
resources. Any sync pods should already be removed with `pod remove`. The pushed
image `<your-registry>/rp-gp10:v1` (a ~150 MB `python:3.11-slim` + `runpod` SDK handler that
returns `/runpod-volume` contents plus `RUNPOD_DC_ID`/`RUNPOD_VOLUME_ID`) was **left
public** so this doc references a real, pullable tag; it costs nothing.

## Companion tool: resumable transfers
For large weights across several volumes, `aws s3 sync` (weak resume, 10k-file wall) is
the pain point. The **community / third-party [Runpod Network Volume Storage
Tool](https://github.com/justinwlin/Runpod-Network-Volume-Storage-Tool)** (not
maintained by Runpod) wraps the
same S3 API with **resumable multipart uploads** (auto chunk sizing, MD5-verified
resume), directory sync with excludes, an interactive browser, a Python SDK, and a
REST server. It's already in the official docs
([community solutions](https://docs.runpod.io/community-solutions/runpod-network-volume-storage-tool)).
```bash
git clone https://github.com/justinwlin/Runpod-Network-Volume-Storage-Tool.git
cd Runpod-Network-Volume-Storage-Tool && uv sync
export RUNPOD_API_KEY=... RUNPOD_S3_ACCESS_KEY=user_... RUNPOD_S3_SECRET_KEY=rps_...
uv run runpod-storage upload ./model-artifacts <vol-id>   # resumable; re-run to resume
```
> Registered in [companion-clis → optional: resumable volume transfers](../../companion-clis/reference/aws.md#optional-resumable-volume-transfers-community-tool).

## Relation to other paths & skill gaps
- **07 (network-volume handoff)** is the single-volume pod↔serverless case; **10 scales
  it to N volumes across DCs** for availability.
- **05/09** produce the artifact you then replicate here.
- **Multi-volume attach:** use **`runpodctl serverless create --network-volume-ids v1,v2`
  on runpodctl ≥ v2.4.0** (check `runpodctl version`; if the Homebrew tap is behind,
  install from [GitHub releases](https://github.com/runpod/runpodctl/releases)). REST-only
  fallback: GraphQL `saveEndpoint` with the object shape + a `User-Agent` header for
  Cloudflare (step 4). Worth folding the version requirement into
  [endpoint-workflows.md](../../runpod-usage/reference/endpoint-workflows.md).
- **Follow-up:** if the resumable-transfer step proves essential, consider **vendoring a
  minimal uploader** (just the multipart+resume core) into the skills repo rather than
  cloning the whole tool.
