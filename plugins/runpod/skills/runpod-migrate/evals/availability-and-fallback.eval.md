# Availability is on by default, and the GPU fallback list is rebuilt

## Prompt

Migrate this to v2:

```python
body = {
    "name": "trainer",
    "imageName": "org/trainer:v3",
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090", "NVIDIA RTX A5000"],
    "gpuTypePriority": "availability",
    "gpuCount": 1,
    "containerDiskInGb": 60,
    "volumeInGb": 100,
    "volumeMountPath": "/workspace",
}
requests.post("https://rest.runpod.io/v1/pods", json=body, headers=H)
```

## Expected behavior

Per `runpod-migrate/SKILL.md` and `reference/breaking-changes.md`:

1. Renames to the v2 body: `image`, `disk`, `gpu.{id,count}`,
   `mounts.persistent.{size,path}`.
2. Recognizes that v2's `gpu.id` takes **one** GPU type, so the `gpuTypeIds` +
   `gpuTypePriority: availability` behavior must be rebuilt client-side as a loop.
3. That loop reads `GET /v2/catalog/gpus` **with `include=AVAILABILITY&product=POD`** and
   orders the preference list by the returned availability level. The include is not
   optional — it is the default for every catalog call this skill writes — and `product`
   is not optional either: the API rejects `include=AVAILABILITY` without it. `POD` is
   the right context here because the code creates pods.
4. Flags the removal in the summary rather than silently dropping to a single GPU type.

## Assertions

- Emits `include=AVAILABILITY` on the catalog request.
- **Pairs it with `product=POD`.** `include=AVAILABILITY` alone is a `400`, so an answer
  that omits `product` has written a call that cannot run. Asserted separately from the
  include so this eval cannot pass code that 400s.
- Produces a fallback loop over the original preference list; does NOT quietly reduce it
  to `gpu: {"id": "NVIDIA GeForce RTX 4090"}` with the other type discarded.
- Uses `mounts.persistent` with an explicit `path` (no reliance on a `/workspace`
  default, which v2 does not have).
- Does NOT invent a v2 `gpuTypeIds`, `gpuTypePriority`, or `gpuCount` field — all three
  would 422.
- Scopes the client-side loop to **pods**. If the same code is asked about an endpoint,
  the answer is `gpu.pools` with the preference list mapped to pool IDs — `pools` is a
  list and v2 places workers on whichever listed pool has capacity, so writing a retry
  loop around an endpoint create is rebuilding something v2 did not remove.
