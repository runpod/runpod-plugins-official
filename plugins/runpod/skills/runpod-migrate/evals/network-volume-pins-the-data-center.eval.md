# A network volume pins the GPU fallback loop to its data center

## Prompt

Migrate this to v2:

```python
body = {
    "name": "trainer",
    "imageName": "org/trainer:v3",
    "cloudType": "SECURE",
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000"],
    "gpuTypePriority": "availability",
    "gpuCount": 1,
    "containerDiskInGb": 60,
    "networkVolumeId": "vol123",
}
requests.post("https://rest.runpod.io/v1/pods", json=body, headers=H)
```

## Expected behavior

Per `runpod-migrate/SKILL.md` and `reference/breaking-changes.md`:

1. Renames to the v2 body: `image`, `cloud`, `disk`, `gpu.{id,count}`, and
   `networkVolumeId` → `mounts.network[0].{volumeId,path}` with an explicit `path`. v1
   implied `/workspace`; v2 has no default.
2. Rebuilds the `gpuTypeIds` + `gpuTypePriority: availability` fallback client-side as a
   loop over `GET /v2/catalog/gpus?include=AVAILABILITY&product=POD`.
3. Recognizes that the volume pins the pod to the volume's data center. The body has no
   `dataCenterIds`, so the loop reads the volume's `dataCenter` from
   `GET /v2/network-volumes/{id}` and ranks each type by its `dataCenters[].availability`
   there, not by the top-level `availability`.
4. Keeps storage outside the loop: every attempt mounts the same volume and only the GPU
   type varies.
5. When every candidate is refused with the volume in place, stops and asks the user:
   wait, accept another GPU type there, use the console's Deploy when available, or move
   to another data center, which is the user's call and leaves the first volume billing
   until they delete it.

## Assertions

- When a body mounts a network volume (`mounts.network`) with no `dataCenterIds`, the
  loop counts stock only in the volume's `dataCenter`, read from
  `GET /v2/network-volumes/{id}`.
- Creates no storage inside the loop. Every attempt mounts `vol123`; no attempt deletes
  it and creates another volume elsewhere.
- Does NOT send a create for a type whose stock in the volume's data center is `NONE`,
  even when its top-level `availability` is `HIGH`.
- Uses `mounts.network` with an explicit `path` and no `mounts.persistent` beside it: the
  two are mutually exclusive, and a body with both is a `400`.
- Does NOT invent a v2 `gpuTypeIds`, `gpuTypePriority`, `gpuCount` or `networkVolumeId`
  field — each would 422.
