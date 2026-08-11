# Breaking changes: v1 / GraphQL → REST v2

Three classes, in increasing order of how much they should worry you.

Everything here was checked against the live API (`api.runpod.io/v2`, verified
2026-08-10). Where the published spec and the running service disagree, the observed
behavior is what is written down — and called out as such.

---

## Class 1 — Loud: renamed, moved, or removed request fields

v2 sets `additionalProperties: false` on every request body. A leftover v1 field is a
`422` that names it:

```json
{"detail": "Request validation failed.",
 "errors": ["$: missing property 'dataCenter'",
            "$: additional properties 'dataCenterId' not allowed"],
 "status": 422, "title": "Unprocessable Entity"}
```

**This is the good news, and worth telling the user explicitly.** No renamed request
field can silently do nothing in v2. A migration that runs is a migration whose request
bodies are right. Full tables: [rest-v1-to-v2.md](rest-v1-to-v2.md) ·
[graphql-to-v2.md](graphql-to-v2.md).

Renamed **paths** are just as loud — `/v2/networkvolumes` is a `404`; the correct path is
`/v2/network-volumes`.

The exception to "loud" is **query parameters**: `GET /v2/pods` ignores unknown ones. A
v1 filter you forget to port (`?desiredStatus=RUNNING`) does not error — it returns every
pod with a `200`. Port list filters into client-side code deliberately.

---

## Class 2 — Quiet: same name, different behavior

These pass schema validation and can pass tests. This is the class users are right to
fear, and the one to walk through explicitly.

### 1. `flashboot`: boolean → enum

v1/REST `flashboot: true` · GraphQL `flashBootType: FLASHBOOT` → v2
`flashboot: "OFF" | "FLASHBOOT" | "PRIORITY_FLASHBOOT"`.

`true` is a `422`, so the *rename* is loud — but `false` → `"OFF"` and a **default of
`OFF` when omitted** is quiet. Dropping the field during migration silently turns
FlashBoot off, and the symptom is slower cold starts, not an error.

### 2. `/billing/endpoints` means a different product

| Path | v1 | v2 |
| --- | --- | --- |
| `/billing/endpoints` | **serverless** spend | **Runpod public endpoints** spend |
| `/billing/serverless` | — | serverless spend |

Both return `200`. Nothing errors. The dashboard just shows the wrong number — usually
`0`, which reads as "we spent nothing" rather than "wrong endpoint".

### 3. `ports` lost its default

v1 pod/template create defaulted `ports` to `8888/http,22/tcp`. v2 defaults to nothing.
Observed on a v2 template created without `ports`: `"ports": []`. Code that relied on
SSH being reachable "because it always was" gets a pod with no exposed ports.

### 4. Omitting storage now means *no storage*

v1 pod create defaulted `volumeInGb: 20` at `volumeMountPath: "/workspace"` — every pod
got a persistent volume whether you asked or not. In v2, omitting `mounts` gives the pod
**no persistent storage at all**; only the ephemeral container disk exists, and it is
wiped on restart. A workload that wrote to `/workspace` keeps working right up until the
first restart, then loses the data.

Related: `mounts.network[].path` is **required**. There is no `/workspace` default to
inherit.

### 5. `idleTimeout` is now conditionally illegal

`workers.idleTimeout` is rejected on a queue endpoint scaling on `requestCount`:

```
422 {"detail": "idleTimeout does not apply to queue-based endpoints scaling on requestCount"}
```

A v1 config that set both `scalerType: REQUEST_COUNT` and `idleTimeout` was accepted.
Same two fields, now mutually exclusive.

### 6. `timeout` does not get the documented default

The v2 spec documents `timeout` defaulting to `300000` ms. **Observed behavior differs:**
an endpoint created without `timeout` comes back with `"timeout": 0`. Do not drop
`executionTimeoutMs` on the assumption that v2 fills in a sane 5-minute default — carry
the value across explicitly.

### 7. `status` reports reality, not intent

v1 `desiredStatus` was the *requested* state (3 values). v2 `status` is the *observed*
lifecycle state (6 values, adding `PROVISIONING`, `STARTING`, `ERROR`). A poll loop
written as `while pod["desiredStatus"] != "RUNNING"` translated literally to
`while pod["status"] != "RUNNING"` changes meaning: it now correctly waits for the pod to
actually be up — which is usually what you wanted, but it will also loop forever on a pod
that has gone to `ERROR` unless you add that branch.

### 8. `env` shape (GraphQL only)

`env: [{key: "K", value: "v"}]` → `env: {"K": "v"}`. A list survives JSON encoding and
fails schema validation, so this one is mostly loud — but any code that *reads* env back
and iterates `for e in env: e["key"]` breaks quietly on the map.

### 9. `cloudType: ALL` is gone (GraphQL only)

v2 `cloud` is `SECURE` or `COMMUNITY`. Code that asked for `ALL` to widen capacity must
now pick one, or try one and fall back.

---

## Class 3 — Capability removed: no v2 equivalent at any price

Not a translation problem. If the code depends on these, either it stays on the old API
or the behavior changes. Decide with the user; do not silently drop them.

| Capability | v1 / GraphQL | Status in v2 |
| --- | --- | --- |
| **GPU fallback list** | `gpuTypeIds: [a, b, c]` + `gpuTypePriority: availability` | `gpu.id` is a single type. Move the loop into your code — see below. |
| **Spot / interruptible pods** | `interruptible: true`, `podRentInterruptable`, `podBidResume` | none |
| **Savings plans** | `Pod.savingsPlans`, `adjustedCostPerHr` | not exposed |
| **Pod `reset`** | `POST /pods/{id}/reset` | `422` — actions are `start`/`stop`/`restart`/`terminate` |
| **Placement constraints** | `countryCodes`, `minRAMPerGPU`, `minVCPUPerGPU`, `minDownloadMbps`, `minUploadMbps`, `minDiskBandwidthMBps`, `supportPublicIp` | none |
| **CUDA version pinning** | `allowedCudaVersions`, `minCudaVersion` on create | create-time pinning is gone; `minCudaVersion` survives only as a `/v2/catalog/gpus` availability filter |
| **Entrypoint override** | `dockerEntrypoint` (array) separate from `dockerStartCmd` | only `args` (one string) |
| **Create from template ID** | `templateId` on pod/endpoint create | `422`. Fetch the template, spread its fields. |
| **Server-side list filters / expansions** | `?desiredStatus=`, `?includeMachine=`, … | filter client-side |
| **Host machine identity** | `machineId`, `machine { podHostId }` | only `dataCenterId` |
| **CPU serverless writes** | create/update CPU endpoints | read-only |
| **Account identity / balance** | `myself { email clientBalance currentSpendPerHr }` | no v2 route — keep GraphQL |
| **Secrets** | `secretCreate` / `secretDelete` | no v2 route — keep GraphQL |
| **Volume encryption flag** | `volumeEncrypted` | not exposed |

### Replacing the GPU fallback list

The one removal that needs real code. v1 walked `gpuTypeIds` server-side; v2 rents one
type. The replacement is *better* than what it replaces, because v2 will tell you the
stock level first — v1 made you guess:

```python
PREFERENCE = ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000", "NVIDIA L40S"]
RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}

cat = session.get(f"{V2}/catalog/gpus",
                  params={"include": "AVAILABILITY", "product": "POD",
                          "count": 1, "cloud": "SECURE"}).json()["gpus"]
stock = {g["id"]: g.get("availability", "NONE") for g in cat}

for gpu_id in sorted(PREFERENCE, key=lambda g: RANK[stock.get(g, "NONE")]):
    r = session.post(f"{V2}/pods", json={**body, "gpu": {"id": gpu_id, "count": 1}})
    if r.status_code == 201:
        return r.json()
raise RuntimeError(f"no GPU available from {PREFERENCE}")
```

For per-datacenter placement, read `dataCenters[].availability` off the same response
instead of the top-level `availability`.

---

## Reading a 422

| Message | What it actually means |
| --- | --- |
| `additional properties 'X' not allowed` | leftover v1/GraphQL field named `X` — rename or drop it |
| `missing property 'X'` | v2 requires `X` (`name`, `image`, endpoint `type`, endpoint `scaling`) |
| `value must be one of '…'` | enum tightened (`action`, `flashboot`, `category`, `cloud`) |
| `missing property 'image'` **plus** `additional properties 'gpu', 'name', 'scaling', 'type' not allowed` — where those fields are obviously valid | **Look at the missing one only.** A missing required field knocks the body out of its schema branch, and the validator then reports every valid field as unexpected. Add the missing field and the rest of the noise disappears. |
| `400` with prose listing valid values | a resource-level constraint, not schema — e.g. a datacenter that does not support network volumes. The message enumerates the ones that do. |
| `500 {"error": "…"}` | you are still talking to **v1** — v2 never uses that envelope |

That last row is a useful tell during a partial migration: the error *shape* tells you
which API answered. v1 errors are `{"error": "...", "status": …}`; v2 errors are
`{"title", "status", "detail", "errors"[]}`.
