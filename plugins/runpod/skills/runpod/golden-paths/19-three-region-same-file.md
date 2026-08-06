# Golden path 19 — three-region same-file endpoint (prove the HA promise with a real served payload)

**Goal:** take the multi-region HA pattern from golden path
[10](10-multi-region-ha-serverless.md) and *prove the whole point of it*: **one**
serverless endpoint attached to **three** network volumes in **three** data centers,
the **same file** synced to all three, serving the **same request identically** no
matter which DC handles it. Path 10 established the mechanism (multi-volume attach +
manual S3 sync) and verified it across **two** DCs; this path scales it to **three**
and closes the loop with a burst that actually lands on **all three** DCs and returns
**byte-identical** output every time.
**Status:** ✅ **COVERED — live-verified 2026-07-13** end to end. Created **three** 10 GB
volumes (`gp19-euro` in **EU-RO-1**, `gp19-eucz` in **EU-CZ-1**, `gp19-euris` in
**EUR-IS-1** — all S3-supported), **S3-synced the identical `gp19-data/` to all three**
(`aws s3 ls` byte-identical: 23 B marker + 106 B payload on each), deployed **one CPU
endpoint** attached to **all three** volumes via the GraphQL `saveEndpoint` path, and
sent a **32-request concurrent burst**: **32/32 `COMPLETED`, served by 10 workers spread
across all three DCs** (EU-RO-1 ×4, EU-CZ-1 ×5, EUR-IS-1 ×1), each worker reading its
**co-located** volume, and **every response byte-identical** (1 distinct marker + 1
distinct payload across all 32). Image `<your-registry>/gp19-3region:v2` (`python:3.11-slim`
+ `runpod`). All three volumes + endpoint + templates were deleted afterward.
**Lane(s):** `runpodctl` (volumes) + `aws`/S3 API (sync, see
[companion-clis → AWS CLI](../../companion-clis/SKILL.md#aws-cli)) + GraphQL
`saveEndpoint` (multi-volume attach — required on runpodctl < v2.4.0; see
[10](10-multi-region-ha-serverless.md))

## When to use

Reach for this when you need to *demonstrate* — not just assert — that a multi-region
endpoint serves consistent results. Path [10](10-multi-region-ha-serverless.md) is the
canonical HA reference (mechanism, the three sync methods, the operating discipline).
This path is the **end-to-end proof with a served payload**: a handler that reads the
synced file off `/runpod-volume` and reports which DC/worker answered, so you can watch
requests fan out across three DCs and confirm each one returns the same bytes. Use it as
a template for a smoke test you run after every re-sync.

## The thesis, restated

| | What you attach | Where workers schedule | What a request sees |
| --- | --- | --- | --- |
| One volume | 1 volume, 1 DC | only that DC | one disk — always consistent, but hostage to one DC |
| **Three volumes (this path)** | 1 volume per DC × 3 DCs | **any of the 3 DCs** | **three independent disks** — consistent **only if you keep them byte-identical** |

The availability win (3× the GPU/CPU pools) is free once you attach three volumes. The
*correctness* is the work: because **volumes do not sync automatically**, a request that
lands in EU-CZ-1 reads the EU-CZ-1 disk, a request in EUR-IS-1 reads the EUR-IS-1 disk,
and if those disks differ your one endpoint silently returns different answers. This path
proves the disks match by serving the file and comparing the bytes returned from every DC.

## Prerequisites

- `runpodctl` (any version — single-volume create + volume management). Multi-volume
  attach here uses the GraphQL `saveEndpoint` fallback because this run was on **runpodctl
  v2.3.0**, which can't attach multiple volumes; on **≥ v2.4.0** you can attach all three
  in one `runpodctl serverless create --network-volume-ids v1,v2,v3` instead (see
  [10 step 4](10-multi-region-ha-serverless.md#4-attach-all-volumes-to-one-endpoint-one-per-dc)).
- `aws` CLI with a profile holding your Runpod **S3 API keys** (access key = Runpod
  `user_...`, secret = `rps_...`). These are **Console-only** to create (Settings → S3 API
  Keys) — an agent can't self-provision them; see
  [companion-clis → AWS CLI](../../companion-clis/SKILL.md#aws-cli).
- Docker + a registry (here `<your-registry>`). Build `--platform linux/amd64`.
- Three DCs that all expose the **S3 API** (so sync needs no compute):
  **EU-RO-1, EU-CZ-1, EUR-IS-1** are all supported.

## Walkthrough

> **Placeholders below are threaded through the S3 sync loops, the GraphQL attach, the
> verify, and cleanup.** Capture each id as the command returns it and reuse the matching
> placeholder throughout: the three volumes as `<vol-ro>`/`<vol-cz>`/`<vol-is>` (per DC),
> the template as `<template-id>`, the endpoint as `<endpoint-id>`. Same placeholder = same
> resource everywhere.

### 1. Create one 10 GB volume per DC

```bash
runpodctl network-volume create --name gp19-euro  --size 10 --data-center-id EU-RO-1
runpodctl network-volume create --name gp19-eucz  --size 10 --data-center-id EU-CZ-1
runpodctl network-volume create --name gp19-euris --size 10 --data-center-id EUR-IS-1
```
✅ Live output (each id becomes both the S3 bucket name and an attach arg):
```json
{ "dataCenterId": "EU-RO-1",  "id": "<vol-ro>", "name": "gp19-euro",  "size": 10 }
{ "dataCenterId": "EU-CZ-1",  "id": "<vol-cz>", "name": "gp19-eucz",  "size": 10 }
{ "dataCenterId": "EUR-IS-1", "id": "<vol-is>", "name": "gp19-euris", "size": 10 }
```
> You pay storage **per volume** — three volumes = 3× the GB bill ($0.07/GB/mo to 1 TB).
> Size only for the data you replicate.

### 2. Sync the SAME file to all three (S3 API, no compute)

One canonical local source → every volume. The bucket is the volume id; `--region` is the
DC id; the endpoint host is the DC id lower-cased.

```bash
mkdir -p gp19-data
printf 'gp19 shared payload v1\nThe same bytes must be served from every DC.\nchecksum-anchor: 3region-identical-42\n' > gp19-data/payload.txt
printf 'gp19-3region-marker-v1\n' > gp19-data/marker.txt

for pair in "EU-RO-1:<vol-ro>" "EU-CZ-1:<vol-cz>" "EUR-IS-1:<vol-is>"; do
  DC=${pair%%:*}; VOL=${pair##*:}
  aws s3 sync ./gp19-data/ --profile runpod --region "$DC" \
    --endpoint-url "https://s3api-$(echo "$DC" | tr 'A-Z' 'a-z').runpod.io/" \
    "s3://$VOL/gp19-data/"
done
```

### 3. Verify the three disks are byte-identical (this is the point)

```bash
for pair in "EU-RO-1:<vol-ro>" "EU-CZ-1:<vol-cz>" "EUR-IS-1:<vol-is>"; do
  DC=${pair%%:*}; VOL=${pair##*:}
  echo "=== $DC ($VOL) ==="
  aws s3 ls --profile runpod --region "$DC" \
    --endpoint-url "https://s3api-$(echo "$DC" | tr 'A-Z' 'a-z').runpod.io/" "s3://$VOL/gp19-data/"
done
```
✅ **Live 2026-07-13** — identical file set + sizes on all three independent disks:
```
=== EU-RO-1 (<vol-ro>) ===
2026-07-13 11:32:49         23 marker.txt
2026-07-13 11:32:49        106 payload.txt
=== EU-CZ-1 (<vol-cz>) ===
2026-07-13 11:32:51         23 marker.txt
2026-07-13 11:32:51        106 payload.txt
=== EUR-IS-1 (<vol-is>) ===
2026-07-13 11:32:53         23 marker.txt
2026-07-13 11:32:53        106 payload.txt
```

### 4. A tiny handler that serves the file + reports who answered

`handler.py` reads the synced file from `/runpod-volume/gp19-data` and returns its
contents plus the identity of the worker/DC that served the request (`RUNPOD_DC_ID` is
the clean per-request DC identifier; `RUNPOD_VOLUME_ID` proves each worker mounted its
*own* DC's volume). An optional `hold` keeps a worker busy so a burst forces scale-out
(see Verify):

```python
import os, socket, time, runpod
VOL = "/runpod-volume/gp19-data"

def _read(name):
    try:
        with open(os.path.join(VOL, name)) as f:
            return f.read().strip()
    except Exception as e:
        return f"<error reading {name}: {e}>"

def handler(event):
    hold = float((event.get("input") or {}).get("hold", 0))
    if hold:
        time.sleep(hold)                      # keep this worker busy → force scale-out
    return {
        "marker":  _read("marker.txt"),
        "payload": _read("payload.txt"),
        "served_by": {
            "hostname":         socket.gethostname(),
            "RUNPOD_DC_ID":     os.environ.get("RUNPOD_DC_ID"),
            "RUNPOD_VOLUME_ID": os.environ.get("RUNPOD_VOLUME_ID"),
        },
    }

runpod.serverless.start({"handler": handler})
```
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir runpod
COPY handler.py .
CMD ["python", "-u", "handler.py"]
```
```bash
docker build --platform linux/amd64 -t <your-registry>/gp19-3region:v2 .
docker push <your-registry>/gp19-3region:v2
```

### 5. Create the CPU endpoint and attach all three volumes (GraphQL `saveEndpoint`)

Make a template, create the endpoint with **one** volume (REST/CLI accept the singular
field), then attach the **full set of three** with `saveEndpoint`:

```bash
runpodctl template create --name gp19-tpl --serverless \
  --image <your-registry>/gp19-3region:v2 --container-disk-in-gb 10     # → template id <template-id>

# create with one volume + all three DCs
curl -s -X POST https://rest.runpod.io/v1/endpoints \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"templateId":"<template-id>","name":"gp19-3region",
       "networkVolumeId":"<vol-ro>","dataCenterIds":["EU-RO-1","EU-CZ-1","EUR-IS-1"],
       "workersMin":0,"workersMax":12}'                              # → endpoint id <endpoint-id>
```
Now attach all three. `networkVolumeIds` takes **objects**, and `api.runpod.io/graphql`
needs a browser-ish `User-Agent` (Cloudflare returns 403/1010 otherwise). To pin the
endpoint to **CPU**, pass `instanceIds` (a CPU flavor, e.g. `cpu3c-2-4`) and an empty
`gpuIds` — `EndpointInput` has **no `computeType` field**, so CPU is expressed via
`instanceIds`:

```bash
curl -s -X POST "https://api.runpod.io/graphql?api_key=$RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' -H 'User-Agent: Mozilla/5.0' \
  -d '{"query":"mutation($input:EndpointInput!){saveEndpoint(input:$input){id name computeType instanceIds}}",
       "variables":{"input":{"id":"<endpoint-id>","name":"gp19-3region","templateId":"<template-id>",
         "instanceIds":["cpu3c-2-4"],"gpuIds":"",
         "dataCenterIds":["EU-RO-1","EU-CZ-1","EUR-IS-1"],
         "networkVolumeIds":[{"networkVolumeId":"<vol-ro>"},
                             {"networkVolumeId":"<vol-cz>"},
                             {"networkVolumeId":"<vol-is>"}],
         "workersMin":0,"workersMax":12,"scalerType":"QUEUE_DELAY","scalerValue":1,"idleTimeout":5}}}'
```
✅ **Live 2026-07-13** — returned `"computeType":"CPU","instanceIds":["cpu3c-2-4"]`, and
`GET /v1/endpoints/<endpoint-id>` confirmed all three attached:
`"networkVolumeIds":["<vol-is>","<vol-ro>","<vol-cz>"]`.

> On **runpodctl ≥ v2.4.0** you can skip the GraphQL step entirely:
> `runpodctl serverless create --template-id <template-id> --compute-type CPU
> --network-volume-ids <vol-ro>,<vol-cz>,<vol-is> --data-center-ids
> EU-RO-1,EU-CZ-1,EUR-IS-1 --workers-min 0 --workers-max 12`. Check `runpodctl version`.

### 6. Verify — one endpoint, three DCs, one payload ✅ live 2026-07-13

The scheduler favors whichever DC has capacity, so a small burst of an instant handler
concentrates on **one** DC. To make it *fan out*, send a **concurrent** burst with a
`hold` so workers stay busy and the autoscaler must bring up more workers **in parallel
across DCs**. A 32-request concurrent burst (`hold=35`, `workersMax=12`), polled to
completion:

```
STATUS:            {'COMPLETED': 32}                          # 32/32 succeeded
DC distribution:   {'EU-RO-1': 12, 'EU-CZ-1': 16, 'EUR-IS-1': 4}   # served from ALL THREE DCs
DISTINCT markers:  1   ('gp19-3region-marker-v1')             # identical regardless of DC
DISTINCT payloads: 1   ('gp19 shared payload v1 … checksum-anchor: 3region-identical-42')
```
Ten distinct workers answered, each reading its **co-located** volume — the same
`/runpod-volume/gp19-data` on every worker resolves to *that worker's DC's* disk:
```
DC=EU-CZ-1   VOL=<vol-cz>   (gp19-eucz)   × 5 workers
DC=EU-RO-1   VOL=<vol-ro>   (gp19-euro)   × 4 workers
DC=EUR-IS-1  VOL=<vol-is>   (gp19-euris)  × 1 worker
```
This is the whole thesis proven at three-region scale: **every worker landed in one of
three DCs and mounted that DC's own independent volume** (`RUNPOD_VOLUME_ID` = the
co-located volume), yet **every one of the 32 responses was byte-identical** because all
three disks carried the same synced file. Drift on any one volume would have shown up as
a second distinct payload from that DC's workers.

> **Getting the spread.** A first, sequential burst of 18 instant requests all landed on
> **one** DC (warm workers get reused). Raising `workersMax`, submitting **concurrently**,
> and adding a `hold` is what forced scale-out: 24 concurrent → 2 DCs, 32 concurrent →
> all 3. If you only need to prove *parity* (not spread), even one DC's workers reading
> the synced file is a valid check — but to exercise HA, drive real concurrency.

## Keeping the three volumes in sync (operating discipline)

Same rules as [10](10-multi-region-ha-serverless.md#keeping-volumes-in-sync-operating-discipline),
now across three disks:
- **One source of truth** (a canonical local dir or your own bucket) → push to **all
  three** volumes. Never edit a volume ad hoc.
- **Re-sync to all three on every data change**, then re-run the step-6 burst as a smoke
  test. A model bump that lands on 2 of 3 volumes = ~1/3 of traffic serving stale data.
- **Verify after every sync** — compare `aws s3 ls` sizes across all three (checksums if
  you can), and confirm the served burst returns a single distinct payload.
- **Volumes are read-only data planes.** Writes go through your sync pipeline, not the
  handler — concurrent worker writes can corrupt a volume.

## Gotchas

- **No auto-sync** — the entire reason this path exists. Three independent disks; drift on
  any one → that DC's workers serve different bytes. Prove parity with a served burst, not
  a claim.
- **One volume per DC** — you can't stack two volumes in the same DC. Each of the three
  DCs gets exactly one; each worker's `RUNPOD_VOLUME_ID` = its own DC's volume.
- **Traffic concentrates without concurrency** — the scheduler prefers one DC's capacity.
  Instant handlers + sequential requests reuse one DC's warm workers. Force spread with
  concurrent submission + a `hold` + higher `workersMax` (step 6).
- **Multi-volume attach needs runpodctl ≥ v2.4.0** for the one-shot
  `--network-volume-ids v1,v2,v3`; on older CLIs use the GraphQL `saveEndpoint` object
  shape (step 5). The Console UI (Edit Endpoint → Advanced → Network Volumes) also works.
- **GraphQL `saveEndpoint` needs `User-Agent: Mozilla/5.0`** on `api.runpod.io/graphql`.
- **`EndpointInput` has no `computeType`** — express CPU via `instanceIds` (a CPU flavor
  like `cpu3c-2-4`) + empty `gpuIds`. Omit both and the endpoint stays GPU.
- **S3 API is DC-limited** — EU-RO-1, EU-CZ-1, EUR-IS-1, US-KS-2 and
  [others](https://docs.runpod.io/storage/s3-api) expose it; for a DC without S3, populate
  its volume with a CPU pod (see [10 Method 2](10-multi-region-ha-serverless.md#method-2--cpu-pod-in-dc-no-gpu)).
- **Cost scales with N** — three volumes = 3× the storage bill; size minimally.
- **S3 access key ≠ API key** — the AWS "access key" is your Runpod `user_...` id, secret
  is the `rps_...` S3 key (Console-only), not `RUNPOD_API_KEY`.

## Cost & cleanup

```bash
runpodctl serverless delete <endpoint-id>        # endpoint (drops the 3-volume attach)
runpodctl template delete   <template-id>            # template(s)
runpodctl network-volume delete <vol-ro>        # gp19-euro  (EU-RO-1)  — billed separately
runpodctl network-volume delete <vol-cz>        # gp19-eucz  (EU-CZ-1)
runpodctl network-volume delete <vol-is>        # gp19-euris (EUR-IS-1)
runpodctl serverless list && runpodctl network-volume list && runpodctl pod list   # confirm clean
```
✅ All deletions returned `{"deleted": true}` on the live run; lists came back with only
pre-existing resources. Scale-to-zero (`workersMin 0`) + tiny CPU workers kept the
compute bill near $0; the three 10 GB volumes were the only meaningful cost and were
deleted immediately. The pushed image `<your-registry>/gp19-3region:v2` (a ~150 MB
`python:3.11-slim` + `runpod` handler) was **left public** so this doc references a real,
pullable tag; it costs nothing.

## Relation to other paths & skill gaps

- **[10 (multi-region HA serverless)](10-multi-region-ha-serverless.md)** is the canonical
  HA reference — the mechanism, the three ways to populate/sync each volume, and the
  operating discipline. **19 is 10's proof at three-region scale**: same file → three DCs →
  a real served burst that lands on all three and returns identical bytes.
- **[07 (network-volume handoff)](07-network-volume-handoff.md)** is the single-volume
  pod↔serverless base case; for a DC without the S3 API, its pod+volume pattern is how you
  populate that DC's disk.
- **[05](05-model-to-endpoint-pipeline.md)/[08](08-finetune-to-serverless.md)** produce
  the artifact you then replicate across DCs here.
- **Skill gap:** the CPU-via-`instanceIds` shape for `saveEndpoint` (no `computeType`
  field) is worth folding into
  [endpoint-workflows.md](../../runpod-usage/reference/endpoint-workflows.md) alongside
  the multi-volume version note from 10.
