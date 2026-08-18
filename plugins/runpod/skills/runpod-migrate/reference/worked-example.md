# Worked example: a mixed v1 + GraphQL codebase

A representative "we wrote this with an agent 18 months ago" repo: a Python batch
renderer on REST v1, an ops dashboard on GraphQL, a job submitter on the serverless job
API, and one file an agent already wrote against v2 without telling anyone.

```
gpu_farm/runpod_client.py    REST v1   pods + network volumes
gpu_farm/endpoints.py        REST v1   templates + serverless + billing
dashboard/capacity.js        GraphQL   myself, gpuTypes, saveEndpoint
dashboard/provision.js       GraphQL   podFindAndDeployOnDemand, podStop/Resume/Terminate
scripts/submit_job.py        job API   ← out of scope, do not touch
ops/volumes_v2.py            REST v2   ← already migrated
```

## Step 1 — inventory

```
$ python3 scripts/rp_api_inventory.py .

| Generation                        | Call sites | Files |
| GraphQL (legacy)                  | 13         | 2     |
| REST v1 (legacy)                  | 12         | 2     |
| v1/GraphQL field names            | 71         | 4     |
| REST v2 (current)                 | 1          | 1     |
| Serverless job API (out of scope) | 3          | 2     |
```

The two facts the user did not know: `ops/volumes_v2.py` was already on v2, and
`scripts/submit_job.py` is a different API that must not be rewritten.

## Step 2 — pod creation, with the fallback list replaced

The `gpuTypeIds` fallback is the only removal that needs new code.

```python
# ── before (v1) ───────────────────────────────────────────────────────────
body = {
    "name": name,
    "imageName": image,
    "cloudType": "SECURE",
    "computeType": "GPU",
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000", "NVIDIA L40S"],
    "gpuTypePriority": "availability",       # server walked the list for us
    "gpuCount": 1,
    "containerDiskInGb": 60,
    "volumeInGb": 100,
    "volumeMountPath": "/workspace",
    "dockerStartCmd": ["bash", "-lc", "python /app/render.py"],
    "minRAMPerGPU": 16, "minVCPUPerGPU": 4,  # no v2 equivalent
    "interruptible": False,                   # no v2 equivalent
}
resp = SESSION.post(f"{V1_BASE}/pods", json=body)
```

```python
# ── after (v2) ────────────────────────────────────────────────────────────
body = {
    "name": name,
    "image": image,
    "cloud": "SECURE",                        # computeType is implied by gpu vs cpu
    "gpu": {"id": GPU_PREFERENCE[0], "count": 1},
    "disk": 60,
    "mounts": {"persistent": {"size": 100, "path": "/workspace"}},
    "args": "bash -lc 'python /app/render.py'",
    "dataCenterIds": DATA_CENTERS,
}

# v1's gpuTypePriority=availability is now ours — and we can see stock first.
stock = SESSION.get(f"{V2_BASE}/catalog/gpus", params={
    "include": "AVAILABILITY", "product": "POD", "count": 1, "cloud": "SECURE",
}).json()["gpus"]
rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
levels = {g["id"]: g.get("availability", "NONE") for g in stock}

for gpu_id in sorted(GPU_PREFERENCE, key=lambda g: rank[levels.get(g, "NONE")]):
    body["gpu"] = {"id": gpu_id, "count": 1}
    resp = SESSION.post(f"{V2_BASE}/pods", json=body)
    if resp.status_code == 201:
        return resp.json()
raise RuntimeError(f"no GPU available from {GPU_PREFERENCE}")
```

The wait loop gets strictly better, because v2 can say a pod has failed:

```python
# before: only three states, so a broken pod burns the whole timeout
if pod["desiredStatus"] == "RUNNING" and pod.get("publicIp"):
    return pod

# after: fail in seconds instead of ten minutes
if pod["status"] == "RUNNING":
    return pod
if pod["status"] == "ERROR":
    raise RuntimeError(f"pod {pod_id} entered ERROR")
```

And list filtering moves client-side — easy to miss, because forgetting it still returns
`200`:

```python
# before: server filtered
SESSION.get(f"{V1_BASE}/pods", params={"computeType": "GPU", "desiredStatus": "RUNNING"}).json()

# after: envelope + filter here
pods = SESSION.get(f"{V2_BASE}/pods").json()["pods"]
[p for p in pods if p["status"] == "RUNNING" and p.get("gpu")]
```

## Step 3 — the endpoint, where `templateId` stops meaning a link

```python
# ── before (v1): create template, reference it by id ──────────────────────
template_id = SESSION.post(f"{V1_BASE}/templates", json={
    "name": name, "imageName": image, "containerDiskInGb": 20,
    "isServerless": True, "dockerStartCmd": ["python", "-u", "handler.py"],
}).json()["id"]

SESSION.post(f"{V1_BASE}/endpoints", json={
    "name": name, "templateId": template_id,
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090"], "gpuCount": 1,
    "workersMin": 0, "workersMax": 5, "idleTimeout": 10,
    "scalerType": "QUEUE_DELAY", "scalerValue": 4,
    "executionTimeoutMs": 600000, "flashboot": True,
})
```

```python
# ── after (v2): container config is inline; GPUs are named by POOL ────────
CONTAINER = {"image": image, "disk": 20, "args": "python -u handler.py",
             "env": {"MODEL_ID": "stabilityai/sdxl-turbo"}}

# "NVIDIA GeForce RTX 4090" is not a pool — resolve it, never hardcode.
gpus = SESSION.get(f"{V2_BASE}/catalog/gpus",
                   params={"include": "AVAILABILITY", "product": "SERVERLESS"}).json()["gpus"]
pool = next(g["pool"] for g in gpus if g["id"] == "NVIDIA GeForce RTX 4090")   # -> "ADA_24"

endpoint = SESSION.post(f"{V2_BASE}/serverless", json={
    **CONTAINER,
    "name": name,
    "type": "QUEUE",                                    # required, new in v2
    "gpu": {"pools": [pool], "count": 1},
    "workers": {"min": 0, "max": 5, "idleTimeout": 10},
    "scaling": {"type": "QUEUE_DELAY", "queueDelay": 4},
    "timeout": 600000,                                  # carry it: v2 does not default it
    "flashboot": "FLASHBOOT",                           # enum, not boolean
}).json()
```

`templateId` is still a legal v2 field, so the shortest possible migration keeps it. This
example inlines the container config instead, for a reason worth stating to the user: v2
resolves a template **once**, at request time, and retains no link to it. If anything in
this codebase edited a template to roll a new image out to existing endpoints, passing
`templateId` across unchanged leaves that rollout silently doing nothing. Inlining makes
the config's real source visible in the code. See
[breaking-changes.md Class 2 §13](breaking-changes.md#13-templateid-still-works-but-the-link-is-gone).

Two deletions fall out of this file for free:

```python
# before — hand-built, and wrong the day the host changes
def endpoint_run_url(endpoint_id):
    return f"https://api.runpod.ai/v2/{endpoint_id}/run"

# after
def endpoint_run_url(endpoint):
    return endpoint["requestUrls"]["run"]
```

```python
# before: v1 /billing/endpoints meant serverless
SESSION.get(f"{V1_BASE}/billing/endpoints", params={"bucketSize": "month", "grouping": "endpointId"})
# after: that name now means a different product — serverless moved
SESSION.get(f"{V2_BASE}/billing/serverless", params={"bucketSize": "month", "lastN": 1}
    ).json()["metadata"]["totals"]["totalAmount"]
```

## Step 4 — the GraphQL dashboard, which stays partly GraphQL

```js
// stays on GraphQL — no v2 equivalent for account identity/balance
export async function accountSummary() {
  return gql(`query { myself { id email currentSpendPerHr clientBalance } }`);
}

// N per-GPU lowestPrice queries -> one catalog call
export async function gpuPrices() {
  const r = await fetch(`${V2}/catalog/gpus?include=AVAILABILITY&product=POD`, { headers });
  return (await r.json()).gpus;   // price.secure, availability, dataCenters[].availability
}

// myself { pods } -> GET /v2/pods
export async function runningPods() {
  const r = await fetch(`${V2}/pods`, { headers });
  return (await r.json()).pods.filter((p) => p.status === "RUNNING");
  //   desiredStatus -> status, costPerHr -> cost,
  //   runtime.uptimeInSeconds -> runtime.uptime,
  //   runtime.gpus[].gpuUtilPercent -> runtime.gpus[].util,
  //   machineId -> gone
}
```

## Step 5 — the summary the user reads

```markdown
## Required for the migration
- gpu_farm/runpod_client.py — pod create rewritten (image/disk/gpu/mounts); the
  gpuTypeIds fallback became an availability-ordered loop; list filtering moved
  client-side; start/stop now POST /action.
- gpu_farm/endpoints.py — container config inlined instead of templateId (still
  legal, but v2 resolves it once and keeps no link); GPU named by pool ADA_24;
  scaling/workers nested; flashboot is an enum; billing moved to
  /billing/serverless.
- dashboard/provision.js — 4 GraphQL pod mutations → REST v2.
- dashboard/capacity.js — gpuTypes/saveEndpoint/deleteEndpoint → REST v2.

## Cleanup enabled by v2
- Deleted endpoint_run_url(): endpoints return requestUrls.run.
- Deleted 3 per-GPU lowestPrice queries: one catalog call replaces them.
- wait_until_running() now fails fast on status ERROR instead of a 10-min timeout.

## Behavior changes to watch
- flashboot: true → "FLASHBOOT". Omitting it means OFF, i.e. slower cold starts.
- timeout: v2 does not apply the documented 300000 default (observed 0) — carried
  the v1 value explicitly.
- /billing/endpoints in v1 meant serverless. In v2 that is /billing/serverless;
  the old path still returns 200, correctly billing public endpoints instead.
- Dropped with no v2 equivalent: minRAMPerGPU, minVCPUPerGPU, interruptible.
  Pods are now on-demand only — confirm that is acceptable.

## Still on GraphQL (no v2 equivalent)
- dashboard/capacity.js accountSummary() — myself { email, clientBalance }.

## Unlocks: what you can build now
- Your renderer retries pod creation blind. /v2/catalog/gpus?include=AVAILABILITY&product=POD
  returns stock per GPU per datacenter, so it can pick a GPU that exists instead of
  discovering capacity by failing.
- Worker health during a rollout: /v2/serverless/{id}/workers gives a status
  histogram and an isStale flag, which is the "did my deploy land" question you were
  answering by eye.
```

## Untouched, deliberately

`scripts/submit_job.py` (`api.runpod.ai/v2/<id>/run`) and `ops/volumes_v2.py` (already
v2). Both appear in the inventory, neither is edited. Say this in the summary — "I did
not touch these, here is why" is what stops the user re-opening the migration later.
