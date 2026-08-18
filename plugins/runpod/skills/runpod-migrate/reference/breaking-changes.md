# Breaking changes: v1 / GraphQL → REST v2

Three classes, in increasing order of how much they should worry you.

Everything here was checked against the live API (`api.runpod.io/v2`, verified
2026-08-18). Where the published spec and the running service disagree, the observed
behavior is what is written down — and called out as such.

The path claims and the Class-3 table are also checked mechanically against the live
spec by `hooks/check_migrate_tables.py` and `hooks/check_migrate_class3.py`, so a row
that goes stale fails CI rather than waiting to be re-read.

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
`/v2/network-volumes`. Same for `/v2/billing/network-volumes`.

**Moved is not removed.** The CUDA constraints are the case to watch: v1's top-level
`allowedCudaVersions` / `minCudaVersion` are now `gpu.allowedCudaVersions` and
`gpu.minCudaVersion` on both pod and endpoint create, deliberately nested so they are
unrepresentable on a CPU workload. Left at the top level they are a `422`; assumed
deleted, you drop a constraint the user still has. A non-empty `allowedCudaVersions` and
`minCudaVersion` are mutually exclusive (`400` if both are sent).

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
| `/billing/endpoints` | **serverless** spend | **[Runpod public endpoints](../../runpod/golden-paths/11-public-endpoints.md)** spend |
| `/billing/serverless` | — | serverless spend |

Both return `200` and neither is broken — v2's `/billing/endpoints` reports public
endpoint spend accurately. The problem is that it answers a question you did not ask.
Carry the path across unchanged and you get a correct total for the wrong product, and
if you use no public endpoints that total is `0` — which reads as "we spent nothing on
serverless" rather than "this is not the serverless route any more".

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

### 9. `stockStatus` → `availability` also flipped case (GraphQL only)

GraphQL's `lowestPrice.stockStatus` returns **`High` / `Medium` / `Low` / `None`**.
v2's `availability` returns **`HIGH` / `MEDIUM` / `LOW` / `NONE`**.

A lookup carried across verbatim — `RANK = {"High": 0, "Medium": 1, …}` or
`if stock == "High"` — stops matching every value and silently falls through to its
default branch. No error, no exception; capacity logic just quietly stops working.

### 10. `mounts` cannot be PATCHed the way `volumeInGb` could

v1 accepted a PATCH containing `volumeInGb` or `volumeMountPath` alone. v2 fixes the
mount kind at create, rejects `volumeId` changes and mount-clearing with `400`, and
requires every mount entry to carry its full schema (`422` otherwise). Migration code
that resizes or remounts storage in place needs rethinking, not translating — full table
in [rest-v1-to-v2.md](rest-v1-to-v2.md#pods--request-body).

### 11. `dockerStartCmd` → `args` collapses an argv array into one string

v1 took `["bash", "-lc", "python /app/render.py"]` — a real argv, where element
boundaries are explicit. v2's `args` is a single string. A naive `" ".join(...)` gives:

```
bash -lc python /app/render.py
```

which runs `python` **as the `-lc` script text** with `/app/render.py` as `$0` — not the
command that was intended. The container starts, so there is no `422` and no crash at
create time; it just does the wrong thing at runtime.

Quote any element that was a unit: `bash -lc 'python /app/render.py'`. Anything
containing a space, a quote, or a shell metacharacter needs the same treatment. Argv
arrays whose elements are all bare words join safely.

Related: v1's separate `dockerEntrypoint` override has no v2 field at all, so an image
that relied on overriding ENTRYPOINT *and* CMD independently cannot be expressed.

### 12. `cloudType: ALL` is gone (GraphQL only)

v2 `cloud` is `SECURE` or `COMMUNITY`. Code that asked for `ALL` to widen capacity must
now pick one, or try one and fall back.

### 13. `templateId` still works, but the link is gone

`templateId` is accepted on pod and endpoint **create** and **update**, so the field
carries across unchanged and nothing errors. What changed is what it means: v2 resolves
the template once, at request time, into the same container fields you could have spread
into the body yourself. Explicit body fields win over the template's, except `env`, which
merges per key with body values winning.

The consequence is the quiet one: **later edits to the template do not reach the
resource.** Code that edited a template to roll out a new image to existing pods or
endpoints silently stops rolling anything out. A pod's `template` response field stays
`null`, and endpoint responses have no `template`/`templateId` at all, so nothing in the
response reveals the template it came from either.

Two smaller edges, both `422`: a serverless template on a pod create, or a pod template
on an endpoint create. An unknown or inaccessible ID is a `404`.

---

## Class 3 — Capability removed: no v2 equivalent at any price

Not a translation problem. If the code depends on these, either it stays on the old API
or the behavior changes. Decide with the user; do not silently drop them.

| Capability | v1 / GraphQL | Status in v2 |
| --- | --- | --- |
| **GPU fallback list (pods)** | `gpuTypeIds: [a, b, c]` + `gpuTypePriority: availability` | a **pod**'s `gpu.id` is a single type. Move the loop into your code — see below. Endpoints keep multi-target placement: `gpu.pools` is a list and workers land on whichever listed pool has capacity, so no loop is needed there. |
| **Spot / interruptible pods** | `interruptible: true`, `podRentInterruptable`, `podBidResume` | none |
| **Savings plans** | `Pod.savingsPlans`, `adjustedCostPerHr` | not exposed |
| **Pod `reset`** | `POST /pods/{id}/reset` | `422` — actions are `start`/`stop`/`restart`/`terminate` |
| **Placement constraints** | `countryCodes`, `minRAMPerGPU`, `minVCPUPerGPU`, `minDownloadMbps`, `minUploadMbps`, `minDiskBandwidthMBps`, `supportPublicIp` | no create-time equivalent. `countryCodes` is the one with a rebuild: catalog filter → `dataCenterIds` → verify where it landed, [below](#replacing-countrycodes-and-the-rest-of-the-placement-constraints). The rest have no v2 filter at all. |
| **Entrypoint override** | `dockerEntrypoint` (array) separate from `dockerStartCmd` | only `args` (one string) |
| **Server-side list filters / expansions** | `?desiredStatus=`, `?includeMachine=`, … | filter client-side |
| **Host machine identity** | `machineId`, `machine { podHostId }` | only `dataCenterId` |
| **Account identity / balance** | `myself { email clientBalance currentSpendPerHr }` | no v2 route — keep GraphQL |
| **Secrets** | `secretCreate` / `secretDelete` | no v2 route — keep GraphQL |
| **Volume encryption flag** | `volumeEncrypted` | not exposed |

### Replacing the GPU fallback list (pods only)

The one removal that needs real code. v1 walked `gpuTypeIds` server-side; a v2 **pod**
rents one type. The replacement is *better* than what it replaces, because v2 will tell
you the stock level first — v1 made you guess:

For **endpoints**, do not write this loop. `gpu.pools` already takes a list and workers
are placed on whichever pool has capacity; narrow a pool with `gpu.excludedTypes`.

```python
PREFERENCE = ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000", "NVIDIA L40S"]
RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}

cat = session.get(f"{V2}/catalog/gpus",
                  params={"include": "AVAILABILITY", "product": "POD",
                          "count": 1, "cloud": "SECURE"}).json()["gpus"]
stock = {g["id"]: g.get("availability", "NONE") for g in cat}

last = None
for gpu_id in sorted(PREFERENCE, key=lambda g: RANK[stock.get(g, "NONE")]):
    r = session.post(f"{V2}/pods", json={**body, "gpu": {"id": gpu_id, "count": 1}})
    if r.status_code == 201:
        return r.json()
    # 422 is a bad *body*, not scarce capacity — the next GPU will fail identically.
    # During a migration this is the likeliest failure, so surface it immediately
    # instead of walking the list and blaming availability.
    if r.status_code == 422:
        raise RuntimeError(f"request rejected, not a capacity problem: {r.text}")
    last = f"{gpu_id}: {r.status_code} {r.text[:200]}"
raise RuntimeError(f"no GPU available from {PREFERENCE} — last error: {last}")
```

Keep the response body in the error. A bare "no GPU available" during a migration sends
people hunting for capacity when the real cause is usually a field they missed.

For per-datacenter placement, read `dataCenters[].availability` off the same response
instead of the top-level `availability`.

### Replacing `countryCodes` (and the rest of the placement constraints)

There **is** a migration here — say so rather than leaving the user with "removed."
`countryCodes` was one field on create, enforced by the scheduler. In v2 it becomes a
lookup plus an explicit data center list:

```python
# v1: one call, the server enforced it
session.post(f"{V1}/pods", json={**body, "countryCodes": ["FR", "DE"]})

# v2: ask which data centers are in those countries, then name them
cat = session.get(f"{V2}/catalog/gpus", params={
    "include": "AVAILABILITY", "countryCodes": "FR,DE", "product": "POD",
}).json()["gpus"]

allowed = sorted({dc["id"] for g in cat for dc in g.get("dataCenters", [])})
if not allowed:
    raise RuntimeError("no data centers in FR,DE with capacity for this GPU type")

pod = session.post(f"{V2}/pods", json={**body, "dataCenterIds": allowed}).json()
```

Let the filter do the country-to-data-center mapping. Data center IDs look like `EU-FR-1`,
so the country appears to be a parseable prefix; do not parse it, the list changes.

**`dataCenterIds` is enforced, despite the wording.** The v2 spec describes it as
*preferred* data centers, which reads like a hint the scheduler may override. It is not.
Verified 2026-08-18 against the live API: an RTX 4090 requested in `["US-KS-2","US-IL-1"]`
— two data centers where that GPU is not offered — was **refused**, not relocated,
while the same request naming `EU-RO-1` succeeded. The scheduler will not place you
outside the list to satisfy capacity. That makes it a usable basis for a data residency
requirement.

**But the refusal looks like a capacity problem, not a placement one:**

```
400 {"detail": "There are no longer any instances available with the requested
     specifications. Please refresh and try again.", "status": 400}
```

Nothing in that message mentions data centers. Over-narrow the list — one country, one
scarce GPU type — and you get a message that sends people hunting for stock when the
real fix is widening `dataCenterIds` or picking a different GPU. During a migration this
is the second-likeliest failure after a bad body, so name it in the error you raise:

```python
if r.status_code == 400 and allowed:
    raise RuntimeError(
        f"no capacity for {gpu_id} within {allowed} — widen the country list, "
        f"pick another GPU type, or drop the restriction. Original: {r.text}")
```

**What to actually ask the user.** This still belongs in the stop-and-ask bucket, but the
question is narrower than "what should I do here": *was the country restriction a
preference or a compliance requirement?* Both are satisfied by the code above, since the
restriction is enforced — what differs is the fallback. A preference can widen the
country list when capacity runs out; a compliance requirement must fail closed instead,
which is the opposite reflex to the GPU-fallback loop above and worth writing explicitly
into the code rather than leaving to whoever edits it next.

For a compliance requirement, also raise `GET /v2/catalog/datacenters`: it reports a
`compliance` array per data center (`GDPR`, `ISO_IEC_27001`, `SOC_2_TYPE_2`, `HIPAA`),
which is a sounder basis for the allowed list than a country code. Country and
certification are not the same question, and the user may have been approximating the
second with the first because v1 gave them no other way to say it.

The other placement constraints — `minRAMPerGPU`, `minVCPUPerGPU`, `minDownloadMbps`,
`minUploadMbps`, `minDiskBandwidthMBps`, `supportPublicIp` — have no equivalent recipe.
There is no v2 filter for them, so those really are accept-the-change, stay-on-v1, or
redesign.

---

## Reading a 422

| Message | What it actually means |
| --- | --- |
| `additional properties 'X' not allowed` | leftover v1/GraphQL field named `X` — rename or drop it |
| `missing property 'X'` | v2 requires `X`. Schema-required: pod create `name`; endpoint create `name`, `type`, `scaling`. `image` is not schema-required because `templateId` can supply it — a create with neither fails, so treat "`image` or `templateId`" as the real requirement. `gpu` is the field most often lost in a `gpuTypeIds` → `gpu.pools` rewrite. |
| `value must be one of '…'` | enum tightened (`action`, `flashboot`, `category`, `cloud`) |
| `missing property 'image'` **plus** `additional properties 'gpu', 'name', 'scaling', 'type' not allowed` — where those fields are obviously valid | **Look at the missing one only.** A missing required field knocks the body out of its schema branch, and the validator then reports every valid field as unexpected. Add the missing field and the rest of the noise disappears. |
| `4xx` with prose instead of a schema path | a resource-level constraint, not schema validation — e.g. a datacenter that does not support network volumes (`400`, and the message enumerates the ones that do), or a container image that is not on the registry (`422`). Read the prose; there is no `$.field` to fix. |
| `500 {"error": "…"}` | you are still talking to **v1** — v2 never uses that envelope |

That last row is a useful tell during a partial migration: the error *shape* tells you
which API answered. v1 errors are `{"error": "...", "status": …}`; v2 errors are
`{"title", "status", "detail", "errors"[]}`.
