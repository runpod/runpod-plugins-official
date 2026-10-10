---
lanes: [docker, runpod-mcp, runpodctl, console]
mcp: partial
concepts: [container-image, pod, cpu-pod, exposed-port, container-disk, registry-credential]
---

# Variant — application Pod

## Goal · Status · Lane(s)

Package the text-statistics HTTP app as an application-only Pod. **Not live-verified.**
Lane: runpod-build-template, then companion-clis and infra lanes when deployment is requested.

## When to use

The user wants to access an application directly. This app needs neither GPU, SSH nor
Jupyter; an interactive development template may require additional promised services.

## Prerequisites

Use [template/README.md](template/README.md) for the fixture file map and local commands.
Local Docker is optional until a local build/test is selected. A live Pod test needs
account access, a pullable registry image and cost/time bounds.

## Walkthrough

1. Preserve `app.py`/`workload.py` and use `Dockerfile.http`, `.dockerignore`, and the
   fixture README as the starting packaging. No startup script is needed: the app is
   the foreground process.
2. Build/test locally where possible, then publish only when authorized. Record the
   produced image digest and source revision.
3. Supply this configuration in the user's README using current supported CLI/API or
   Console field names. Confirm concrete syntax through the infra lane before execution.

| Setting | Fixture value | Evidence |
| --- | --- | --- |
| Compute | CPU; no CUDA/framework required | Source-inspected; live sizing unverified |
| Image | Published HTTP fixture image tag/digest | Resolve after build/push |
| Command override | None; inherit image command | Source-inspected |
| HTTP port | `8080`, app `PORT=8080` | Source-inspected; external reachability unverified |
| Persistent storage | None required by this stateless operation | Source-inspected |
| Container disk | Size from built/unpacked image plus headroom | Unresolved until measured |
| Credentials | No app credentials; private registry pull auth if used | App has no built-in authentication |

The fixture returns counts for submitted text. It is a teaching service with no app
authentication; add access controls before using sensitive text or exposing capabilities
that need them. Never imply that a public Pod proxy alone authenticates users.

## Verify

POST `{"text":"A a B"}` to `/analyze` through the external Pod URL. Require
`{"words":3,"counts":{"a":2,"b":1}}`; check `/ping`, invalid input then a valid
request, and restart. For a user app with persistence, also test fresh/reused storage
and the changed image against old user state. This stateless fixture cannot prove those.

## Gotchas

`EXPOSE` is documentation; the Pod configuration must expose the actual app port.
Binding only `localhost` would break external access. Do not add SSH just to conform
to the historical [SSH-enabled example](../22-minimal-pod-image/README.md).

## Cost & cleanup

Use a small disposable CPU Pod only when authorized; save response evidence and delete
that Pod afterward. Confirm final state and any retained storage.

## Skill gaps

Live Pod deployment and hardware/disk measurements remain unverified. Replace this
fixture with the user's real operation before claiming their application is validated.
