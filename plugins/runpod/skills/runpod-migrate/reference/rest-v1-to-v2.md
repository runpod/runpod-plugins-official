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
| `…/networkvolumes` | **`…/v2/network-volumes`** | hyphenated. `/v2/networkvolumes` is a `404`. `POST …/{id}/update` alias gone — use PATCH. |
| `…/containerregistryauth` | `…/v2/registries` | |
| — | `/v2/registries/delegations` | new: ECR delegation |
| — | `/v2/catalog/gpus`, `/cpus`, `/datacenters` | new: v1 had no catalog |
| `GET /billing/pods` | `GET /v2/billing/pods` | |
| `GET /billing/endpoints` | **`GET /v2/billing/serverless`** | ⚠ see below |
| `GET /billing/networkvolumes` | **`GET /v2/billing/network-volumes`** | hyphenated, like the resource path |
| — | `GET /v2/billing`, `/v2/billing/clusters` | new |

⚠ **`/billing/endpoints` is the trap.** In v1 it meant *serverless* spend. In v2 that is
`/v2/billing/serverless`; `/v2/billing/endpoints` still exists but reports spend on
**[Runpod public endpoints](../../runpod/golden-paths/11-public-endpoints.md)**, a
different product. Both return `200` and both are correct — v2 just answers a different
question under the same path, so an unchanged call quietly reports the wrong product's
total (`0`, if you run no public endpoints).

Billing responses also changed shape: v1 returned a bare array of records; v2 returns
`{"records": [...], "metadata": {"query", "recordCount", "totals"}}`, and adds `lastN`
(e.g. `?bucketSize=day&lastN=30`) as an alternative to `startTime`/`endTime`. v1's
`grouping` parameter is gone — v2 emits one record per resource per bucket.

**The money field was renamed too: `amount` → `totalAmount`.** Records now break the
figure down (`gpuAmount`, `cpuAmount`, `diskAmount`, `feeAmount`, `totalAmount`), and
`metadata.totals` carries the same shape across the whole window. Porting
`sum(r["amount"] for r in resp.json())` to v2 without this is a `KeyError` — noisy, but
easy to miss because it sits one line away from the far quieter `/billing/endpoints`
trap above.

```python
# v1
total = sum(r["amount"] for r in resp.json())
# v2 — per record, or just read the precomputed total
total = sum(r["totalAmount"] for r in resp.json()["records"])
total = resp.json()["metadata"]["totals"]["totalAmount"]
```

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
`interruptible`, `locked` (PATCH only), `gpuTypePriority`, `dataCenterPriority`,
`cpuFlavorPriority`, `countryCodes`, `supportPublicIp`, `minRAMPerGPU`, `minVCPUPerGPU`,
`minDownloadMbps`, `minUploadMbps`, `minDiskBandwidthMBps`.

**Moved, not dropped** — do not delete these:

| v1 pod create | v2 |
| --- | --- |
| `allowedCudaVersions` | `gpu.allowedCudaVersions` (GPU pods only — a CPU pod has no `gpu` block, and ignores a template's constraint) |
| `templateId` | `templateId`, still accepted — but resolved once at create time, with no link retained. See [breaking-changes.md Class 2 §13](breaking-changes.md#13-templateid-still-works-but-the-link-is-gone). |

(`minCudaVersion` was never a v1 *pod* create field — it is a v1 **endpoint** create
field, and in v2 it is `gpu.minCudaVersion` on both. It is mutually exclusive with a
non-empty `allowedCudaVersions` (`400` if both are sent). `countryCodes` survives only as
a `/v2/catalog/gpus` read filter, not a create-time constraint. `volumeEncrypted` was a
v1 Pod **response** field, not an input.)

### CPU pods

`computeType: "CPU"` + `cpuFlavorIds: [...]` + `vcpuCount` becomes one `cpu` object.
Send `gpu` **or** `cpu`, never both.

```jsonc
// v1                                    // v2
{                                        {
  "name": "ingest-worker",                 "name": "ingest-worker",
  "imageName": "python:3.11-slim",         "image": "python:3.11-slim",
  "computeType": "CPU",                    // implied by using `cpu` instead of `gpu`
  "cpuFlavorIds": ["cpu3c", "cpu5c"],      "cpu": {"id": "cpu3c", "vcpuCount": 2},
  "cpuFlavorPriority": "availability",     // no fallback list — loop client-side
  "vcpuCount": 2,
  "containerDiskInGb": 20,                 "disk": 20
  "volumeInGb": 20,                        // mounts.persistent is DISALLOWED on CPU
  "volumeMountPath": "/workspace"          // pods — use mounts.network instead
}                                        }
```

Two CPU-only traps beyond the rename:

- **`mounts.persistent` is rejected on CPU pods.** A literal `volumeInGb` translation
  fails. Persist to a network volume instead.
- **`vcpuCount` must be a power of two** and within the flavor's `vcpu.min`..`vcpu.max`.

Valid flavor IDs and their vCPU ranges come from the catalog — never hardcode them:

```bash
curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
  'https://api.runpod.io/v2/catalog/cpus?include=AVAILABILITY&product=POD' \
| python3 -c 'import json,sys; [print(c["id"].ljust(10), c["vcpu"], c["availability"]) for c in json.load(sys.stdin)["cpus"]]'
```

### Pod lifecycle actions

Four separate v1 endpoints collapse into one, with the verb in the body:

```python
# v1 — one path per verb
SESSION.post(f"{V1}/pods/{pod_id}/stop")
SESSION.post(f"{V1}/pods/{pod_id}/start")
SESSION.post(f"{V1}/pods/{pod_id}/restart")
SESSION.post(f"{V1}/pods/{pod_id}/reset")      # no v2 equivalent

# v2 — one path, action in the body, returns the updated pod
SESSION.post(f"{V2}/pods/{pod_id}/action", json={"action": "stop"})
SESSION.post(f"{V2}/pods/{pod_id}/action", json={"action": "start"})
SESSION.post(f"{V2}/pods/{pod_id}/action", json={"action": "restart"})
SESSION.delete(f"{V2}/pods/{pod_id}")          # "terminate" is also a valid action
```

The old paths are `404`, and `{"action": "reset"}` is a `422` listing the four legal
values. Before acting, `pod["actions"]` tells you which transitions are legal *right
now* — v1 had no equivalent, so code guessed and handled the error.

### The same create in curl

For codebases that aren't Python, the minimal shape:

```bash
# v1
curl -X POST https://rest.runpod.io/v1/pods \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"trainer","imageName":"runpod/pytorch:latest","gpuTypeIds":["NVIDIA GeForce RTX 4090"],
       "gpuCount":1,"containerDiskInGb":50,"volumeInGb":20,"volumeMountPath":"/workspace"}'

# v2
curl -X POST https://api.runpod.io/v2/pods \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"trainer","image":"runpod/pytorch:latest",
       "gpu":{"id":"NVIDIA GeForce RTX 4090","count":1},"disk":50,
       "mounts":{"persistent":{"size":20,"path":"/workspace"}}}'
```

### Listing pods

```python
# v1 — server-side filters, bare array
pods = SESSION.get(f"{V1}/pods", params={"computeType": "GPU",
                                         "desiredStatus": "RUNNING"}).json()

# v2 — envelope, and the filters are yours. Unknown params are IGNORED, not
# rejected, so a filter you forget to port silently returns everything.
pods = [p for p in SESSION.get(f"{V2}/pods").json()["pods"]
        if p["status"] == "RUNNING" and p.get("gpu")]
```

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
  "templateId": "tpl123",                  "templateId": "tpl123",         // ⚠ still accepted, but
                                           //   resolved once — template edits no longer
                                           //   reach the endpoint. Or inline the fields:
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
  'https://api.runpod.io/v2/catalog/gpus?include=AVAILABILITY&product=SERVERLESS' \
| python3 -c 'import json,sys; [print(g["pool"].ljust(16), g["id"]) for g in json.load(sys.stdin)["gpus"] if g["pool"]]'
```

Endpoint responses now carry **`requestUrls`** — `run`, `runSync`, `status`, `stream`,
`cancel`, `retry`, `purgeQueue`, `health` for `QUEUE` endpoints, or `base` + `health` for
`LOAD_BALANCER`. Delete any code that builds `https://api.runpod.ai/v2/<id>/run` by hand.

Other endpoint response changes: `templateId`/`template` gone from the **response** (the
config is inline, even when you created from a template), `workers[]` (full pod objects) →
`GET /v2/serverless/{id}/workers`, `version` → `GET /v2/serverless/{id}/releases`,
`scalerType`/`scalerValue` → `scaling`, `computeType` → presence of `gpu` vs `cpu`.

CPU endpoints are writable in v2: send `cpu` instead of `gpu`, as a list of eligible
`{id, vcpuCount}` configurations (flavor IDs from `GET /v2/catalog/cpus`; `vcpuCount` must
be a power of two and valid for the flavor). Memory is derived from the flavor's catalog
RAM multiplier. Exact duplicate configurations are rejected, though the same flavor may
be listed at different vCPU counts. Note the CUDA constraints live under `gpu`
specifically so they are unrepresentable here.

## Templates

| v1 | v2 |
| --- | --- |
| `imageName` | `image` |
| `containerDiskInGb` | `disk` |
| `volumeInGb` / `volumeMountPath` | `mounts.persistent.{size,path}` (no `network` on templates — `422`) |
| `volumeInGb: 0` | **omit `mounts` entirely.** Zero meant "no volume" in v1; `{"size": 0}` is invalid in v2 (10 GB floor) and there is no `path` to supply. |
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

Three changes land at once here — the hyphenated path, the `dataCenterId` → `dataCenter`
field, and the response envelope:

```python
# ── v1 ────────────────────────────────────────────────────────────────────
def ensure_volume(name, size_gb, dc):
    for vol in SESSION.get(f"{V1}/networkvolumes").json():        # bare array
        if vol["name"] == name:
            return vol
    return SESSION.post(f"{V1}/networkvolumes",
                        json={"name": name, "size": size_gb,
                              "dataCenterId": dc}).json()

# ── v2 ────────────────────────────────────────────────────────────────────
def ensure_volume(name, size_gb, dc):
    listing = SESSION.get(f"{V2}/network-volumes").json()["networkVolumes"]  # envelope
    for vol in listing:
        if vol["name"] == name:
            return vol
    return SESSION.post(f"{V2}/network-volumes",
                        json={"name": name, "size": size_gb,
                              "dataCenter": dc,            # renamed
                              "type": "HIGH_PERFORMANCE"}  # new, optional, immutable
                        ).json()
```

`/v2/networkvolumes` (unhyphenated) is a `404`, and `dataCenterId` is a `422` — so both
of those fail loudly. The envelope is the quiet one: `for vol in resp.json()` iterates
the dict's *keys* instead of raising.

**Attaching a volume to a pod** changed shape as well, and `path` is now mandatory:

```python
# v1 — one field, mount path implied (/workspace by default)
body["networkVolumeId"] = vol["id"]

# v2 — an array of mounts, each needing an explicit path
body["mounts"] = {"network": [{"volumeId": vol["id"], "path": "/workspace"}]}
```

## Container registry auth → registries

`POST /v2/registries` `{name, username, password}` → `{id, name}`. Credentials are
write-only in both versions. Deleting is rejected if a pod is using it; templates that
reference it silently drop to `registry: null` instead of blocking the delete.

The request body is unchanged — only the path, the list envelope, and the field that
references the credential from a pod or template:

```python
# ── v1 ────────────────────────────────────────────────────────────────────
auth = SESSION.post(f"{V1}/containerregistryauth",
                    json={"name": "dockerhub", "username": u, "password": p}).json()
all_auths = SESSION.get(f"{V1}/containerregistryauth").json()          # bare array
pod_body["containerRegistryAuthId"] = auth["id"]

# ── v2 ────────────────────────────────────────────────────────────────────
auth = SESSION.post(f"{V2}/registries",
                    json={"name": "dockerhub", "username": u, "password": p}).json()
all_auths = SESSION.get(f"{V2}/registries").json()["registries"]        # envelope
pod_body["registry"] = auth["id"]                                       # renamed
```

## Templates — a worked pair

The endpoint example above spreads a template into a create body. Standalone, the
template itself converts like this:

```python
# ── v1 ────────────────────────────────────────────────────────────────────
tpl = SESSION.post(f"{V1}/templates", json={
    "name": "sdxl-worker",
    "imageName": "org/worker:v3",
    "containerDiskInGb": 20,
    "volumeInGb": 40,
    "volumeMountPath": "/workspace",
    "dockerStartCmd": ["python", "-u", "handler.py"],
    "env": {"MODEL_ID": "stabilityai/sdxl-turbo"},
    "ports": ["8888/http"],
    "isServerless": True,
    "isPublic": False,
    "readme": "## SDXL worker",
}).json()

# ── v2 ────────────────────────────────────────────────────────────────────
tpl = SESSION.post(f"{V2}/templates", json={
    "name": "sdxl-worker",
    "image": "org/worker:v3",
    "disk": 20,
    "mounts": {"persistent": {"size": 40, "path": "/workspace"}},
    "args": "python -u handler.py",     # one string; quote any element with spaces
    "env": {"MODEL_ID": "stabilityai/sdxl-turbo"},
    "ports": ["8888/http"],
    "serverless": True,
    "public": False,
    "category": "NVIDIA",               # same enum and default as v1
    # "readme" has no v2 field — drop it, or keep the text in your own repo
}).json()
```

Templates accept only `mounts.persistent`; a `network` key is a `422`. And v2 refuses to
delete a template while a pod references it or an endpoint is bound to it.
