# 21 · Network volume storage tiers — standard vs high-performance

**Goal:** launch a **standard** vs a **high-performance** network volume and attach it to a
pod / serverless endpoint. (Provisioning only — no perf benchmarking.)

**Status:** DOCUMENTED — launch paths verified against `runpodctl … --help`, the v1 REST +
v2 REST OpenAPI specs, and the `runpod/runpod-mcp` source (2026-07-29). Not a full live run:
a high-performance volume needs the MCP `create-network-volume` tool's `volumeType`, a raw
**v2 REST** call, or a ⚡ data center in the console — `runpodctl` has no tier flag (see
Skill gaps).

**Lane(s):** runpod-mcp or Runpod **REST v2** (either tier) · console (⚡ toggle) · runpodctl (standard create + attach)

## When to use

Persistent storage shared across pods/workers, or a faster tier for I/O-bound work.

- **Standard** — general persistence, most workloads.
- **High-performance** — up to ~3× throughput / 4× IOPS; reach for it when I/O read/write is
  the bottleneck: streaming/loading training data, many small files, checkpoint-heavy runs,
  faster model load / lower cold-start. Details:
  [high-performance storage docs](https://docs.runpod.io/storage/high-performance-storage).

For choosing bake-in vs volume in the first place, see
[building-images.md](../../runpod-usage/reference/building-images.md).

## Prerequisites

- `runpodctl` ≥ v2.4.0 (`runpodctl version`); `RUNPOD_API_KEY` set.
- For high-performance: console access to a ⚡ data center, **or** the ability to call the v2 REST API.

## Walkthrough

### Standard network volume (runpodctl / v1 REST)

```bash
runpodctl network-volume create --name std-vol --size 50 --data-center-id US-KS-2   # → volume id
```

### High-performance network volume

The MCP `create-network-volume` tool takes `volumeType` (`STANDARD` |
`HIGH_PERFORMANCE`), so it can request high-performance directly — prefer it when MCP is
connected. `runpodctl` (v1) still sends only `name`/`size`/`dataCenter`, so it gets the
data center's **default** tier. Without MCP, two ways to get it:

**A. Runpod REST v2 (`type: HIGH_PERFORMANCE`)** — the programmatic path:

```bash
curl -s -X POST https://v2-rest.runpod.io/v2/network-volumes \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"hp-vol","dataCenter":"US-KS-2","size":50,"type":"HIGH_PERFORMANCE"}'
# type ∈ {STANDARD, HIGH_PERFORMANCE}; omit → the data center's default tier.
```

**B. Console** — pick a data center marked with the ⚡ icon; a "High-performance storage"
toggle appears (on by default). Recommend this to the user when no programmatic path is available.

### Attach to compute (both tiers, same mechanism)

```bash
# Pod — attach at creation (network volume replaces /workspace):
runpodctl pod create --template-id <id> --gpu-id "NVIDIA GeForce RTX 4090" --network-volume-id <vol-id>

# Serverless — attach (mounts at /runpod-volume):
runpodctl serverless create --name my-ep --template-id <id> --network-volume-id <vol-id>
```

## Verify

- `runpodctl network-volume get <vol-id>` (or `list`) shows the volume.
- On a pod the volume is at `/workspace`; on serverless at `/runpod-volume`.
- `runpodctl` doesn't surface the tier — confirm high-performance in the console or via the v2 API response.

## Gotchas

- **Tier is immutable** — you can't convert standard ↔ high-performance; create a new volume and copy the data (S3 API / `runpodctl`).
- **`runpodctl` can't request high-performance** — it has no tier flag. Use the MCP tool's `volumeType`, the v2 REST `type` field, or the console.
- **Per-DC pinning** — a volume lives in one data center and compute must run there. For multi-region serverless, attach one volume per DC (`--network-volume-ids`); data does **not** auto-sync.
- **Small files / S3 API** — over the S3 access path, listing/syncing >10k files or >10 GB degrades, and single-object `PUT` caps at 500 MB (use multipart above).
- **Concurrent writes** — don't write the same volume from multiple workers at once (corruption).

## Cost & cleanup

- Standard ≈ $0.07/GB-mo (first 1 TB), $0.05 beyond; high-performance is a per-GB premium that **varies by data center** — check the console (no fixed public number). Volumes bill for as long as they exist.
- Delete when done: `runpodctl network-volume delete <vol-id>` (remove any pod using it first).

## Skill gaps

- `runpodctl network-volume create` has no `--type` flag, so the CLI still can't pick a tier. Worth an upstream request. The MCP gap here is closed: `create-network-volume` forwards `volumeType` as the v2 `type` field as of `@runpod/mcp-server` 3.0.0.
