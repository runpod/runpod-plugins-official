---
lanes: [docker, runpodctl, ssh]
mcp: partial
concepts: [network-volume, container-image, pod, container-disk, template]
---

# Golden path 25 — bake into the image vs mount a network volume

✅ **Live-verified** (built an image with a baked-in file → launched a CPU pod with a standard
network volume attached → showed the two live on **different filesystems** → torn down).

The single most important storage decision when building for Runpod: **what rides in the image
(local disk, fast) vs what lives on a mounted network volume (networked, slower — especially
for many small files).** This path proves the distinction is real and physical, not a
convention. It's the runnable companion to
[building-images.md → Bake in vs mount at runtime](../../../runpod-usage/reference/building-images.md)
and [golden path 21 (storage tiers)](../21-storage-tiers.md).

## Prerequisites

See the shared [Before you run any path](../README.md#before-you-run-any-path-shared-prerequisites)
block first. For this path specifically:

- **Runpod auth** — `export RUNPOD_API_KEY=<key>` (from the
  [console](https://runpod.io/console/user/settings); see
  [getting-started](../../../runpod-usage/reference/getting-started.md)).
- **Docker** running **and `docker login`** to a registry you can push to — substitute your
  namespace for `<namespace>`. See [companion-clis docker](../../../companion-clis/reference/docker.md).
- **An SSH key registered** on your account (to exec into the pod) — see
  [golden path 22](../22-minimal-pod-image/README.md#prerequisites).

## The mental model

| | Baked into the image | Mounted network volume |
| --- | --- | --- |
| Where it physically lives | host **local disk** (image layers) | **networked** storage, mounted in |
| Filesystem (observed) | `overlay` | `fuse` (MooseFS: `mfs#…runpod.net:9421`) |
| Speed | fast; no network hop | slower, esp. **many small files** |
| Persists across pods? | no — it's part of the image | **yes** — the volume outlives the pod |
| Mount path | anywhere you `COPY`/build it | pod `/workspace`, serverless `/runpod-volume` |
| Put here | packages, libs, lots of small static files | model weights, datasets, anything to persist |

> In a network-volume-enabled region, "container disk vs volume disk" is mostly fiction — the
> **only** thing truly on local disk is the image and what's baked into it. Everything written
> to the volume path is on the network mount.

## The image

[`template/`](template/) bakes a dummy 20 MB "model" into `/opt/baked-model` (stand-in for
packages/small static files), plus the from-scratch SSH `start.sh` (see
[golden path 22](../22-minimal-pod-image/README.md)) so you can exec in and inspect.

```dockerfile
RUN mkdir -p /opt/baked-model \
    && head -c 20000000 /dev/zero > /opt/baked-model/weights.bin   # baked → rides the image
```

## Build + push

```bash
cd template
docker buildx build --platform linux/amd64 -t <namespace>/rp-gp25-bake:v1 --push .
```

## Provision a **standard** network volume + attach it to a CPU pod

```bash
# standard-tier volume (high-performance tier is console / v2-REST only — see GP21)
runpodctl network-volume create --name gp25-vol --size 10 --data-center-id EU-RO-1
# → volume id, e.g. fgw5d0q0sd

# pod must be in the SAME data center as the volume; volume mounts at /workspace
runpodctl pod create --compute-type cpu --image <namespace>/rp-gp25-bake:v1 \
  --name gp25-pod --ports "22/tcp" --container-disk-in-gb 10 \
  --network-volume-id <vol-id> --volume-mount-path /workspace --data-center-ids EU-RO-1
```

For a **high-performance** volume, provision it via the Console / v2 REST (per
[GP21](../21-storage-tiers.md)) and attach with the same `--network-volume-id` — the mount
mechanics below are identical; only the underlying tier differs.

## Inspect the two side by side

```bash
runpodctl ssh info <pod-id>     # prints ip, port, and a ready-to-paste `ssh_command`
# Run this on the pod (fill -i/host/port from the ssh_command that ssh info printed) —
# it writes to the volume AND compares filesystems:
ssh -i <key-from-ssh-info> root@<ip> -p <port> '
  echo "=== BAKED (in image) ===";        ls -la /opt/baked-model
  echo "=== filesystem of each path ==="; df -hT /opt/baked-model /workspace | awk "{print \$1, \$2, \$7}"
  echo "=== write to MOUNTED volume ==="; mkdir -p /workspace/mounted-model
  echo "written to network volume at runtime" > /workspace/mounted-model/note.txt
  head -c 20000000 /dev/zero > /workspace/mounted-model/weights.bin
  ls -la /workspace/mounted-model; cat /workspace/mounted-model/note.txt
  echo "=== SUMMARY ===";  echo "baked fs:   $(stat -f -c %T /opt/baked-model)";  echo "mounted fs: $(stat -f -c %T /workspace)"
'
```

**Observed this run** (`ht837ukjrbz14v`, EU-RO-1, CPU pod, `fgw5d0q0sd` attached — trimmed for
readability; real output also lists `SOURCE.txt` and a `df` header row):

```text
=== BAKED (in image) ===        /opt/baked-model/weights.bin  20000000 bytes  (came from the image)
=== filesystem of each path ===
overlay                      overlay   /            ← baked file: image on LOCAL disk
mfs#euro-3.runpod.net:9421   fuse      /workspace   ← network volume: a NETWORK mount
=== write to MOUNTED volume ===
/workspace/mounted-model/note.txt      "written to network volume at runtime"   ← persists on the volume
/workspace/mounted-model/weights.bin   20000000 bytes
=== SUMMARY ===
baked fs:   overlayfs
mounted fs: fuse
```

The proof is the `df -hT` line: the baked file sits on **`overlay`** (the image, on the host's
local disk), while `/workspace` is **`mfs#euro-3.runpod.net:9421`** — a FUSE **MooseFS network
mount**. Same pod, two physically different storage backends. Files written to `/workspace`
survive after the pod is deleted (they're on the volume); the baked file does not (it's the
image).

## Tear down

```bash
runpodctl pod delete <pod-id>
runpodctl network-volume delete <vol-id>   # the volume bills while it exists — delete when done
```

## What this proves

- **Bake vs mount is a real filesystem boundary**, not a naming convention: `overlay` (local,
  in the image) vs `fuse`/MooseFS (network volume).
- The network volume **persists across pods** and mounts at `/workspace` (pod) — data written
  at runtime lives there, not in the image.
- Rule of thumb confirmed: bake packages/many-small-static-files (local, fast); mount
  large/persistent artifacts (weights, datasets). Tier choice (standard vs high-performance)
  is orthogonal — see [GP21](../21-storage-tiers.md).
