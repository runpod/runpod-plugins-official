---
concepts: [endpoint-build, endpoint-release, serverless-endpoint, worker, container-image]
---

# Endpoint builds and releases

Every change to a Serverless endpoint's container becomes a **release**, and workers move
to it gradually. When the endpoint is connected to a GitHub repository, each commit can
also produce a **build**, and a completed build becomes a release.

## Releases and rolling releases

- **What creates a release:** a change to `image`, `env`, `args`, `disk`, `ports` or
  `registry`. These settings live in the endpoint's own bound template, created and deleted
  with the endpoint. Editing a template you created the endpoint *from* does not affect it.
- **How workers move:** idle workers on the old release are replaced right away. Busy
  workers finish their current job first, so the endpoint keeps serving while it rolls.
- **Tracking a rollout:** the release list's rollout summary describes the endpoint's current
  state, and each worker's `isStale` shows whether it still runs an older release. REST:
  `GET /v2/serverless/{id}/releases`. MCP: `list-endpoint-releases` and `list-endpoint-workers`.
- **Where a release came from:** `source` is `MANUAL` for a configuration change, or
  `GIT_BUILD` for a release produced by a GitHub build, which also sets `buildId`.

## Old and new versions overlap

During a rollout some workers run the old release and some the new one. When that is not
acceptable:

1. Set `workers.max` to `0` and wait for the workers to stop.
2. Update the endpoint.
3. Restore `workers.max`.

Use versioned image tags rather than `:latest`. Existing workers can keep serving a cached
`:latest` image, so pushing a new `:latest` does not guarantee they run it.

## GitHub builds

- A build runs from a commit to the connected repository and moves through `PENDING`,
  `BUILDING`, `UPLOADING` and `TESTING`.
- It ends in `COMPLETED`, `FAILED`, `CANCELLED` or `TEST_FAILED`. For `FAILED` and
  `TEST_FAILED`, the build's `error` field explains why.
- A completed build produces a release, and workers move to it the same way as any release.
- List builds newest first with `GET /v2/serverless/{id}/builds` (MCP: `list-endpoint-builds`),
  and fetch an older one by id with `GET /v2/serverless/{id}/builds/{buildId}`
  (MCP: `get-endpoint-build`).

## Exact rules

These facts come from the concept files, which cite the REST v2 spec and the public docs:
[`endpoint-release`](../concepts/endpoint-release.yaml) and
[`endpoint-build`](../concepts/endpoint-build.yaml).
