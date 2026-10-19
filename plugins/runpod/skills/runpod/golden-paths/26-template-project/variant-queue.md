---
lanes: [docker, runpod-mcp, runpodctl, console]
mcp: partial
concepts: [container-image, serverless-handler, serverless-endpoint, worker, job, endpoint-build, template]
---

# Variant — queue worker

## Goal · Status · Lane(s)

Expose text-statistics as a submitted job. **Not live-verified on Runpod.**
Lane: runpod-build-template, then selected build and infra lanes.

## When to use

The application has a meaningful programmatic input/output operation suited to a job.
An interactive-only app first needs that operation defined; a mock handler is insufficient.

## Prerequisites

Use [template/README.md](template/README.md). `handler.py` calls the real workload;
the SDK is imported only for worker startup, so its adapter can also be tested locally
without installing the SDK. A full worker test needs the built image or SDK environment.

## Walkthrough

Build using `Dockerfile.queue`. Its pinned SDK dependency layer precedes application
code; the runtime lives at `/opt/venv`, not a volume. For eligible repositories choose
the [managed GitHub route](../../../runpod-build-template/reference/github-integration.md),
or build/push externally. Verify the chosen builder and endpoint separately.

| Setting | Fixture value | Evidence |
| --- | --- | --- |
| Target | Queue-based Serverless | Required by handler contract |
| Image/command | Queue image; inherit `python -u handler.py` | Source-inspected; record build identity |
| Input | `{"input":{"text":"A a B"}}` | Local tests cover workload/adapter |
| Output | `{"words":3,"counts":{"a":2,"b":1}}` | Expected, not a live result |
| Compute/storage | CPU; no models, secrets, persistent output or HTTP port required | Live sizing unverified |
| Worker bounds | Min 0, max 1 for a disposable test | Suggested; confirm current supported settings |
| Disk/timeouts | Determine from image size and representative workload | Unresolved until measured/current contract checked |

Document actual supported deployment commands/settings from current infra tools; use
[path 23](../23-minimal-queue-image/README.md) for the deployment ordering, not as an
authoritative snapshot of today's flags.

## Verify

Run the fixture tests and the SDK local-input mode from its README, then submit a real
job through the Runpod endpoint when authorized. Check content, not only `COMPLETED`.
Submit malformed input followed by a valid job and repeated requests. This stateless
fixture returns small JSON; applications producing files need separately verified
durable output retrieval and worker-replacement behavior.

## Gotchas

Use job `input` for the actual schema. Do not add an HTTP health server to a queue
worker. A local handler call does not test the SDK/platform lifecycle. Avoid assuming
SDK failure/cancellation behavior beyond what the selected version documents/tests.

## Cost & cleanup

Keep live test workers bounded, save job/output evidence and delete task-owned endpoint
and template resources. Account for resources left after a partial deployment.

## Skill gaps

Live endpoint execution, managed-GitHub build/update and platform sizing remain unverified.
