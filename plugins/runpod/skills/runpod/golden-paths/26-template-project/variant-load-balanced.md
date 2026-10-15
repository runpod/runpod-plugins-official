---
lanes: [docker, runpod-mcp, runpodctl, console]
mcp: partial
concepts: [container-image, serverless-endpoint, worker, endpoint-build, template]
---

# Variant — load-balanced HTTP worker

## Goal · Status · Lane(s)

Keep the text-statistics application's `/analyze` route on Serverless.
**Full Runpod acceptance remains unverified.** A maintainer
[reported healthy startup on the default port](https://github.com/runpod/runpod-plugins-official/pull/78#issuecomment-6161964871);
the checks shipped here are local. Lane: runpod-build-template, then build and infra lanes.

## When to use

The user wants direct HTTP routes rather than queue jobs. The existing app already
implements the route, so no queue handler or SDK dependency is added to its image.

## Prerequisites

Use [template/README.md](template/README.md). Verify the current
[load-balanced worker contract](https://docs.runpod.io/serverless/load-balancing/build-a-worker)
before live configuration; Docker-local success does not establish platform readiness.

## Walkthrough

Use `Dockerfile.http`. Choose an eligible managed GitHub build or external image route.
Keep the foreground HTTP command and app port consistent with platform configuration.
The app reads `PORT`: Docker-local runs fall back to `8080`, while Runpod supplies
`PORT=80` by default. Use the endpoint's default for this fixture; do not copy the
local `8080` setting into the endpoint.

| Setting | Fixture value | Evidence |
| --- | --- | --- |
| Target | Load-balanced Serverless | Required by direct HTTP use |
| Image/command | HTTP image; inherit `python3 app.py` | Source-inspected; record built/deployed identity |
| App route | `POST /analyze` | Local HTTP tests included |
| App/health port | Runpod default `PORT=80`; `PORT_HEALTH` uses the same listener for `/ping` | App reads `PORT`; [platform defaults](https://docs.runpod.io/serverless/load-balancing/overview#environment-variables) |
| Readiness | `GET /ping` → 200 once this dependency-free app listens; a model app returns 204 during loading, then 200 | [Health contract](https://docs.runpod.io/serverless/load-balancing/overview#health-checks); other codes are unhealthy |
| Compute/storage | CPU; stateless, no models/persistent storage | Live sizing unverified |
| Workers | Min 0, max 1 for disposable acceptance | Suggested; check scaler/timeout fields live |

Supply the endpoint type, current port/health settings, image, secret names and disk
requirements through a supported configuration form. Refer to
[path 14](../14-load-balancing-endpoint.md) for the overall flow while confirming live
tool syntax and platform limits.

## Verify

Run local/container tests, then check the actual endpoint health and POST useful input
through its external URL with required endpoint auth. Validate expected counts, invalid
input followed by success, and relevant request concurrency. For a model app, add
model-aware readiness and measure whether web processes duplicate model memory.

## Gotchas

Runpod health-port configuration and Docker `EXPOSE` are separate. An HTTP 200 at
`/ping` does not prove `/analyze` works. This fixture has no model-loading phase;
do not reuse its immediate readiness behavior for an initializing GPU service.

## Cost & cleanup

Use bounded disposable live resources only when authorized; preserve response evidence
and verify endpoint/template cleanup.

## Skill gaps

Live load-balancer behavior, scale-to-zero/replacement and managed-build updates remain
unverified. A real model application needs its own performance and cancellation tests.
