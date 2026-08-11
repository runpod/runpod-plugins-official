# REST v1 → REST v2 mapping

Base URL: `https://rest.runpod.io/v1` → **`https://api.runpod.io/v2`**
Auth is unchanged: `Authorization: Bearer $RUNPOD_API_KEY`.

Authoritative specs — diff them yourself when in doubt:
`https://rest.runpod.io/v1/openapi.json` · `https://api.runpod.io/v2/openapi.json`

## Two global changes that touch every call site

**1. Every list response is wrapped.** v1 returned a bare JSON array; v2 returns an
object with a named key. `for pod in resp.json()` silently iterates the *keys* of a dict
instead of failing, so this one can pass a smoke test and corrupt behavior.

| v1 | v2 |
| --- | --- |
| `GET /pods` → `[ … ]` | `GET /v2/pods` → `{"pods": [ … ]}` |
| `GET /endpoints` → `[ … ]` | `GET /v2/serverless` → `{"endpoints": [ … ]}` |
| `GET /templates` → `[ … ]` | `GET /v2/templates` → `{"templates": [ … ]}` |
| `GET /networkvolumes` → `[ … ]` | `GET /v2/network-volumes` → `{"networkVolumes": [ … ]}` |
| `GET /containerregistryauth` → `[ … ]` | `GET /v2/registries` → `{"registries": [ … ]}` |

**2. List filtering is client-side now.** v1's `GET /pods` accepted `computeType`,
`desiredStatus`, `gpuTypeId`, `name`, `templateId`, `include*` expansions and more. v2's
`GET /v2/pods` takes **no query parameters** — unknown ones are ignored, not rejected, so
a filter you forget to port returns *everything* with a `200`. Filter in your own code.

## Paths

| v1 | v2 | Note |
| --- | --- | --- |
| `POST /pods` | `POST /v2/pods` | `201`; body fully restructured (below) |
| `GET /pods` | `GET /v2/pods` | envelope; no filters |
| `GET /pods/{id}` | `GET /v2/pods/{id}` | |
| `PATCH /pods/{id}` | `PATCH /v2/pods/{id}` | |
| `POST /pods/{id}/update` | `PATCH /v2/pods/{id}` | the `/update` POST alias is gone (404) |
| `DELETE /pods/{id}` | `DELETE /v2/pods/{id}` | |
| `POST /pods/{id}/start` | `POST /v2/pods/{id}/action` `{"action":"start"}` | |
| `POST /pods/{id}/stop` | `POST /v2/pods/{id}/action` `{"action":"stop"}` | |
| `POST /pods/{id}/restart` | `POST /v2/pods/{id}/action` `{"action":"restart"}` | |
| `POST /pods/{id}/reset` | **no equivalent** | `reset` is not a v2 action (`422`). Closest is `restart`; a true reset is stop + start. |
| — | `GET /v2/pods/{id}/logs` | new: SSE log stream |
| `POST /endpoints` | `POST /v2/serverless` | |
| `GET /endpoints` | `GET /v2/serverless` | |
| `GET|PATCH|DELETE /endpoints/{id}` | `…/v2/serverless/{id}` | |
| `POST /endpoints/{id}/update` | `PATCH /v2/serverless/{id}` | alias gone |
| — | `GET /v2/serverless/{id}/workers` | new |
| — | `GET /v2/serverless/{id}/releases` | new |
| — | `GET /v2/serverless/{id}/workers/{workerId}/logs` | new: SSE |
| `POST|GET /templates`, `…/{id}` | `…/v2/templates` | `/update` alias gone |
| `…/networkvolumes` | **`…/v2/network-volumes`** | hyphenated. `/v2/networkvolumes` is a `404`. |
| `…/containerregistryauth` | `…/v2/registries` | |
| — | `/v2/registries/delegations` | new: ECR delegation |
| — | `/v2/catalog/gpus`, `/cpus`, `/datacenters` | new: v1 had no catalog |
| `GET /billing/pods` | `GET /v2/billing/pods` | |
| `GET /billing/endpoints` | **`GET /v2/billing/serverless`** | ⚠ see below |
| `GET /billing/networkvolumes` | `GET /v2/billing/networkvolumes` | |
| — | `GET /v2/billing`, `/v2/billing/clusters` | new |

⚠ **`/billing/endpoints` is the trap.** In v1 it meant *serverless* spend. In v2 that is
`/v2/billing/serverless`; `/v2/billing/endpoints` exists but bills **Runpod public
endpoints**, a different product. Both return `200`. Nothing errors — the numbers are
just wrong.

Billing responses also changed shape: v1 returned a bare array of records; v2 returns
`{"records": [...], "metadata": {"query", "recordCount", "totals"}}`, and adds `lastN`
(e.g. `?bucketSize=day&lastN=30`) as an alternative to `startTime`/`endTime`. v1's
`grouping` parameter is gone — v2 emits one record per resource per bucket.

## Pods — request body

```jsonc
// v1                                    // v2
{                                        {
  "name": "trainer",                       "name": "trainer",              // required in v2
  "imageName": "org/img:tag",              "image": "org/img:tag",         // required in v2
  "containerDiskInGb": 60,                 "disk": 60,
  "volumeInGb": 100,                       "mounts": {"persistent": {"size": 100, "path": "/workspace"}},
  "volumeMountPath": "/workspace",
  "networkVolumeId": "vol123",             "mounts": {"network": [{"volumeId": "vol123", "path": "/workspace"}]},
  "gpuTypeIds": ["A", "B"],                "gpu": {"id": "A", "count": 1}, // single type — see breaking-changes
  "gpuCount": 1,
  "cloudType": "SECURE",                   "cloud": "SECURE",
  "containerRegistryAuthId": "auth1",      "registry": "auth1",
  "dockerStartCmd": ["python","x.py"],     "args": "python x.py",          // string, not array
  "env": {"K": "v"},                       "env": {"K": "v"},              // unchanged
  "ports": ["8888/http"],                  "ports": ["8888/http"],         // unchanged, but no default now
  "dataCenterIds": [...]                   "dataCenterIds": [...]          // unchanged
}                                        }
```

`mounts.persistent` and `mounts.network` are **mutually exclusive** (`400` if both).
`mounts.network[].path` is **required** — v2 has no `/workspace` default.

⚠ **`mounts.persistent` is deprecated in v2**, and a literal `volumeInGb` →
`mounts.persistent` translation inherits that. It is host-local storage pinned to one
machine — *data does not survive a host failure* — it is disallowed on CPU pods, and
`size` has a 10 GB floor. For anything the user cannot recreate, migrate `volumeInGb` to
a **network volume** (`mounts.network`) instead and say why you changed the shape.

**`mounts` is far less malleable on PATCH than v1's `volumeInGb`/`volumeMountPath` were.**
v1 let you PATCH either field alone; v2 enforces:

| PATCH attempt | Result |
| --- | --- |
| omit `mounts`, or send `{}` | existing mount unchanged |
| `network: []` to clear mounts | `400` — clearing is unsupported |
| add a mount kind not present at create (incl. any mount on a mountless pod) | `400` — kind is fixed at create |
| change a network mount's `volumeId` | `400` — immutable |
| partial entry (e.g. `path` without `size`/`volumeId`) | `422` — every entry needs its full schema |

Dropped from pod create with no v2 equivalent: `computeType` (implied by `gpu` vs `cpu`),
`templateId`, `interruptible`, `locked` (PATCH only), `gpuTypePriority`,
`dataCenterPriority`, `cpuFlavorPriority`, `countryCodes`, `supportPublicIp`,
`minRAMPerGPU`, `minVCPUPerGPU`, `minDownloadMbps`, `minUploadMbps`,
`minDiskBandwidthMBps`, `allowedCudaVersions`.

(`minCudaVersion` was never a v1 *pod* create field — it is a v1 **endpoint** create
field, and survives in v2 only as a `/v2/catalog/gpus` availability filter.
`volumeEncrypted` was a v1 Pod **response** field, not an input.)

CPU pods: `computeType: "CPU"` + `cpuFlavorIds: [...]` + `vcpuCount` becomes
`cpu: {"id": "cpu3c", "vcpuCount": 2}`. Send `gpu` **or** `cpu`, never both.

## Pods — response

| v1 | v2 |
| --- | --- |
| `desiredStatus` (`RUNNING`/`EXITED`/`TERMINATED`) | `status` (`PROVISIONING`/`STARTING`/`RUNNING`/`EXITED`/`ERROR`/`TERMINATED`) |
| `costPerHr`, `adjustedCostPerHr` | `cost` (savings-plan adjustment is not exposed) |
| `imageName` | `image` |
| `containerDiskInGb` | `disk` |
| `machine {...}`, `machineId` | **gone** — only `dataCenterId` survives |
| `publicIp`, `portMappings` | `runtime.ports[] {private, public, type, ip}` (null unless RUNNING) |
| `networkVolume {...}` | `mounts.network[]` |
| `savingsPlans[]` | **gone** |
| `gpu {...}` (pricing blob) | `gpu {id, count}` |
| — | `actions[]` — transitions legal right now |
| — | `runtime {uptime, gpus[], cpu, memory, ports[]}` |
| — | `globalNetworking {enabled, ip, internalDns}` |

## Serverless endpoints

```jsonc
// v1                                    // v2
{                                        {
  "name": "sdxl",                          "name": "sdxl",
  "templateId": "tpl123",                  // ⚠ REJECTED (422). Inline the container fields:
                                           "image": "org/worker:tag", "disk": 20,
                                           "env": {...}, "args": "python -u handler.py",
                                           "type": "QUEUE",                // required, new
  "gpuTypeIds": ["NVIDIA GeForce RTX 4090"],
  "gpuCount": 1,                           "gpu": {"pools": ["ADA_24"], "count": 1},  // POOL ids
  "workersMin": 0, "workersMax": 5,        "workers": {"min": 0, "max": 5, "idleTimeout": 10},
  "idleTimeout": 10,
  "scalerType": "QUEUE_DELAY",             "scaling": {"type": "QUEUE_DELAY", "queueDelay": 4},
  "scalerValue": 4,                        //  or {"type": "REQUEST_COUNT", "requestCount": N}
  "executionTimeoutMs": 600000,            "timeout": 600000,              // still milliseconds
  "flashboot": true,                       "flashboot": "FLASHBOOT",       // enum, not boolean
  "networkVolumeId" / "networkVolumeIds",  "networkVolumes": ["vol1"],
  "dataCenterIds": [...]                   "dataCenterIds": [...]
}                                        }
```

**`gpu.pools` takes pool IDs, not GPU type IDs.** `"NVIDIA GeForce RTX 4090"` is not a
valid pool. Resolve it at runtime — never hardcode the table, it grows:

```bash
curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
  'https://api.runpod.io/v2/catalog/gpus?include=AVAILABILITY' \
| python3 -c 'import json,sys; [print(g["pool"].ljust(16), g["id"]) for g in json.load(sys.stdin)["gpus"] if g["pool"]]'
```

Endpoint responses now carry **`requestUrls`** — `run`, `runSync`, `status`, `stream`,
`cancel`, `retry`, `purgeQueue`, `health` for `QUEUE` endpoints, or `base` + `health` for
`LOAD_BALANCER`. Delete any code that builds `https://api.runpod.ai/v2/<id>/run` by hand.

Other endpoint response changes: `templateId`/`template` gone (config is inline),
`workers[]` (full pod objects) → `GET /v2/serverless/{id}/workers`, `version` →
`GET /v2/serverless/{id}/releases`, `scalerType`/`scalerValue` → `scaling`,
`computeType` → presence of `gpu` vs `cpu`. CPU serverless is **read-only** in v2 — you
cannot create or update a CPU endpoint.

## Templates

| v1 | v2 |
| --- | --- |
| `imageName` | `image` |
| `containerDiskInGb` | `disk` |
| `volumeInGb` / `volumeMountPath` | `mounts.persistent.{size,path}` (no `network` on templates — `422`) |
| `dockerStartCmd` / `dockerEntrypoint` | `args` (string) |
| `containerRegistryAuthId` | `registry` |
| `isServerless` | `serverless` |
| `isPublic` | `public` |
| `category` | `category` — unchanged (already `CPU`/`NVIDIA`/`AMD`, default `NVIDIA`, in v1) |
| `readme`, `earned`, `isRunpod`, `runtimeInMin` | **gone** |

Templates are still worth keeping as a config preset — but v2 pods and endpoints do not
reference one by ID. Fetch the template and spread its container fields into the create
body. Deleting a template is rejected while a pod references it or an endpoint is bound
to it.

## Network volumes

| v1 | v2 |
| --- | --- |
| `POST /networkvolumes` `{name, size, dataCenterId}` | `POST /v2/network-volumes` `{name, size, dataCenter, type?}` |
| response `dataCenterId` | `dataCenter` |
| — | `type`: `STANDARD` \| `HIGH_PERFORMANCE`, set at create, immutable |

`size` can still only grow. Not every datacenter supports volumes — a bad one returns
`400` and **the error message lists the datacenters that do**. Check
`GET /v2/catalog/datacenters` → `networkVolumeTypes` first.

## Container registry auth → registries

`POST /v2/registries` `{name, username, password}` → `{id, name}`. Credentials are
write-only in both versions. Deleting is rejected if a pod is using it; templates that
reference it silently drop to `registry: null` instead of blocking the delete.
