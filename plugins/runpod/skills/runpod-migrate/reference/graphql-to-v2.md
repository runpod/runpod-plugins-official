# GraphQL → REST v2 mapping

`POST https://api.runpod.io/graphql` → **`https://api.runpod.io/v2/…`**

Auth: GraphQL accepts `?api_key=…` *or* `Authorization: Bearer …`. REST v2 accepts only
the header. If the code passes the key in the query string, that moves into a header —
which is also the security upgrade (keys stop landing in URLs, logs, and referrers).

GraphQL schema reference: <https://graphql-spec.runpod.io/> (introspection is disabled in
production, so use that page, not `__schema`). **That page is incomplete** — it omits
`saveEndpoint`, `deleteEndpoint`, `saveTemplate`, `deleteTemplate`, `secretCreate`,
`secretDelete`, and the network-volume mutations, all of which are real and in use. For
anything missing there, the worked examples in the Runpod docs
(`docs.runpod.io` → SDKs → GraphQL) are the better source. Do not conclude an operation
does not exist just because that page omits it.

## Operation map

| GraphQL | REST v2 |
| --- | --- |
| `podFindAndDeployOnDemand(input:)` | `POST /v2/pods` |
| `pod(input: {podId})` | `GET /v2/pods/{id}` |
| `myself { pods { … } }` | `GET /v2/pods` |
| `podStop(input: {podId})` | `POST /v2/pods/{id}/action` `{"action":"stop"}` |
| `podResume(input: {podId, gpuCount})` | `POST /v2/pods/{id}/action` `{"action":"start"}` — you cannot change GPU count on resume |
| `podTerminate(input: {podId})` | `DELETE /v2/pods/{id}` |
| `podEditJob(input:)` | `PATCH /v2/pods/{id}` |
| `myself { endpoints { … } }` | `GET /v2/serverless` |
| `saveEndpoint(input:)` — no `id` | `POST /v2/serverless` |
| `saveEndpoint(input:)` — with `id` | `PATCH /v2/serverless/{id}` |
| `deleteEndpoint(id:)` | `DELETE /v2/serverless/{id}` |
| `saveTemplate(input:)` | `POST /v2/templates` / `PATCH /v2/templates/{id}` |
| `deleteTemplate(templateName:)` | `DELETE /v2/templates/{id}` — **by ID, not name** |
| `gpuTypes` / `gpuTypes(input: {id})` | `GET /v2/catalog/gpus?include=AVAILABILITY&product=POD` — `product` is **required** with `include` (`400` without it); use `SERVERLESS` when sizing an endpoint |
| `cpuTypes` | `GET /v2/catalog/cpus?include=AVAILABILITY&product=POD` — same required pairing |
| `saveRegistryAuth(input:)` | `POST /v2/registries` |
| `createNetworkVolume(input:)` | `POST /v2/network-volumes` |
| `updateNetworkVolume(input:)` | `PATCH /v2/network-volumes/{id}` |
| `deleteNetworkVolume(input:)` | `DELETE /v2/network-volumes/{id}` |

`saveEndpoint` is an upsert keyed on `id`; REST splits that into POST and PATCH. If the
code branches on "did I pass an id", that branch becomes the method choice.

## No REST v2 equivalent — keep these on GraphQL

| GraphQL | Why it stays |
| --- | --- |
| `myself { id email clientBalance currentSpendPerHr }` | v2 has no user/account route. (Spend *history* is `/v2/billing`; live balance is not.) |
| `secretCreate` / `secretDelete` | no v2 secrets API |
| `podRentInterruptable`, `podBidResume` | v2 has no spot/interruptible pods |
| `createCluster` / `deleteCluster` | v2 exposes cluster **billing** only |

A codebase that uses these ends up bilingual after the migration. That is expected —
say so in the summary rather than leaving the user to wonder if you missed something.

## Field translation

### Pods — `podFindAndDeployOnDemand` → `POST /v2/pods`

| GraphQL input | v2 |
| --- | --- |
| `imageName` | `image` |
| `name` | `name` |
| `gpuTypeId` (single) | `gpu.id` |
| `gpuCount` | `gpu.count` |
| `containerDiskInGb` | `disk` |
| `volumeInGb` + `volumeMountPath` | `mounts.persistent.{size,path}` |
| `networkVolumeId` | `mounts.network[0].{volumeId,path}` — `path` required |
| `dockerArgs` | `args` |
| `ports: "8888/http,22/tcp"` (comma string) | `ports: ["8888/http","22/tcp"]` (array) |
| `env: [{key,value}]` | `env: {"KEY": "value"}` (map) |
| `cloudType: SECURE \| COMMUNITY` | `cloud` — **`ALL` is gone**, pick one |
| `minVcpuCount`, `minMemoryInGb` | removed — GPU pods size RAM/vCPU from the GPU type |
| `allowedCudaVersions` | `gpu.allowedCudaVersions` — moved under `gpu`, not removed (GPU pods only). Mutually exclusive with a non-empty `gpu.minCudaVersion`. |
| `startSsh`, `startJupyter` | removed — express these through `ports` / `args` / the image |
| `templateId` | `templateId` — still accepted, but resolved once with no link retained ([Class 2 §13](breaking-changes.md#13-templateid-still-works-but-the-link-is-gone)) |

A full conversion, showing the four shape changes that a field-by-field rename misses —
comma-string ports become an array, the env pair-list becomes a map, `dockerArgs`
becomes `args`, and the whole thing stops being a string template:

```js
// ── before (GraphQL) ──────────────────────────────────────────────────────
await gql(`
  mutation {
    podFindAndDeployOnDemand(input: {
      cloudType: SECURE,
      gpuTypeId: "NVIDIA RTX A6000",
      gpuCount: 1,
      name: "${name}",
      imageName: "${image}",
      containerDiskInGb: 40,
      volumeInGb: 40,
      volumeMountPath: "/workspace",
      minVcpuCount: 8,
      minMemoryInGb: 32,
      ports: "8888/http,22/tcp",
      dockerArgs: "",
      env: [{ key: "JUPYTER_PASSWORD", value: "${pw}" }]
    }) { id imageName machineId machine { podHostId } }
  }
`);

// ── after (REST v2) ───────────────────────────────────────────────────────
const res = await fetch("https://api.runpod.io/v2/pods", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.RUNPOD_API_KEY}`,
             "Content-Type": "application/json" },
  body: JSON.stringify({
    name,
    image,
    cloud: "SECURE",
    gpu: { id: "NVIDIA RTX A6000", count: 1 },
    disk: 40,
    mounts: { persistent: { size: 40, path: "/workspace" } },
    ports: ["8888/http", "22/tcp"],          // array, not a comma string
    env: { JUPYTER_PASSWORD: pw },           // map, not [{key, value}]
    // minVcpuCount / minMemoryInGb: removed, GPU type sizes the host
    // dockerArgs: "" -> omit `args` entirely rather than sending ""
  }),
});
if (!res.ok) { const e = await res.json(); throw new Error(`${e.status} ${e.title}: ${e.detail}`); }
const pod = await res.json();   // pod.id, pod.status, pod.cost — no machineId
```

Also note the interpolation disappears. GraphQL forced string-building, so a value
containing a quote could break the query; v2 takes real JSON and `JSON.stringify`
escapes for you.

Response fields: `desiredStatus` → `status`, `costPerHr` → `cost`,
`machineId` / `machine { podHostId }` → gone (`dataCenterId` remains),
`runtime.uptimeInSeconds` → `runtime.uptime`,
`runtime.gpus[].gpuUtilPercent` → `runtime.gpus[].util`,
`runtime.gpus[].memoryUtilPercent` → `runtime.gpus[].memoryUtil`,
`runtime.container.cpuPercent` / `.memoryPercent` → `runtime.cpu.util` / `runtime.memory.util`.

### Serverless — `saveEndpoint` → `POST|PATCH /v2/serverless`

| GraphQL input | v2 |
| --- | --- |
| `gpuIds: "AMPERE_16"` (comma string of pool IDs) | `gpu.pools: ["AMPERE_16"]` (array) — pool IDs carry over unchanged |
| `workersMin` / `workersMax` | `workers.min` / `workers.max` |
| `idleTimeout` | `workers.idleTimeout` |
| `scalerType` + `scalerValue` | `scaling: {"type": "QUEUE_DELAY", "queueDelay": N}` or `{"type": "REQUEST_COUNT", "requestCount": N}` |
| `flashBootType: FLASHBOOT` | `flashboot: "FLASHBOOT"` (string, same values: `OFF`/`FLASHBOOT`/`PRIORITY_FLASHBOOT`) |
| `locations: "US"` (region/country string) | `dataCenterIds: ["US-KS-2", …]` — explicit IDs |
| `templateId` | `templateId` — still accepted, but resolved once with no link retained ([Class 2 §13](breaking-changes.md#13-templateid-still-works-but-the-link-is-gone)) |
| `networkVolumeId` | `networkVolumes: ["vol1"]` |
| — | `type: "QUEUE" \| "LOAD_BALANCER"` — **required on create** |
| `executionTimeoutMs` | `timeout` (still ms) |

GraphQL's `gpuIds` already used **pool** IDs (`AMPERE_16`, `ADA_24`), so GraphQL users
get an easier ride here than REST v1 users, whose `gpuTypeIds` held individual GPU names.

`locations: "US"` has no one-to-one translation — it was a region hint, v2 takes
datacenter IDs. Enumerate them instead of hardcoding:

```bash
curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
  'https://api.runpod.io/v2/catalog/datacenters?include=GPU_AVAILABILITY' \
| python3 -c 'import json,sys; [print(d["id"], d["region"]) for d in json.load(sys.stdin)["dataCenters"]]'
```

### Templates — `saveTemplate` → `/v2/templates`

Same renames as pods (`imageName`→`image`, `containerDiskInGb`→`disk`,
`dockerArgs`→`args`, `volumeInGb`/`volumeMountPath`→`mounts.persistent`,
`env` list→map, `isServerless`→`serverless`), plus `readme` is dropped.

**`deleteTemplate` took a name; `DELETE /v2/templates/{id}` takes an ID.** Any code
holding template *names* as its handle needs to hold IDs instead — usually the largest
non-obvious change in a GraphQL template workflow.

### Catalog — `gpuTypes` → `/v2/catalog/gpus`

| GraphQL | v2 |
| --- | --- |
| `id` | `id` |
| `displayName` | `name` |
| `memoryInGb` | `memory` |
| `secureCloud` / `communityCloud` | `secure` / `community` |
| `lowestPrice(input:{gpuCount, secureCloud}).uninterruptablePrice` | `price.secure` / `price.community` |
| `lowestPrice(…).stockStatus` — `High`/`Medium`/`Low`/`None` | `availability` — **`HIGH`/`MEDIUM`/`LOW`/`NONE`**. ⚠ The case flips. A `{"High": 0, …}` rank table or `== "High"` comparison carried over stops matching *silently*. |
| `lowestPrice(…).minimumBidPrice` | gone with spot pods |
| — | `dataCenters[].availability` — per-datacenter, new |
| — | `pool` — the serverless pool this GPU belongs to |
| — | `maxCount.{secure,community}`, `manufacturer` |

One `GET /v2/catalog/gpus?include=AVAILABILITY&product=POD` replaces the N per-GPU `lowestPrice`
queries a capacity loop used to make.

## Error handling

GraphQL always answers `200` with an `errors[]` array in the body, so client code checks
`json.errors`. REST v2 uses status codes plus `{title, status, detail, errors[]}`.

```python
# before
data = resp.json()
if data.get("errors"):
    raise RuntimeError(data["errors"])
return data["data"]["podFindAndDeployOnDemand"]

# after
if not resp.ok:
    body = resp.json()
    raise RuntimeError(f"{body['status']} {body['title']}: {body['detail']}")
return resp.json()
```

Any retry logic keyed on "GraphQL returned 200 so the transport worked" needs rewriting
against real status codes — see [breaking-changes.md](breaking-changes.md#reading-a-422).
