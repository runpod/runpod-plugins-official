---
concepts: [serverless-endpoint, worker, container-image]
---

# Load-balanced HTTP worker contract

Run the application's HTTP server directly. Preserve useful existing routes and
streaming behavior; a queue handler is not required. Verify the current
[worker contract](https://docs.runpod.io/serverless/load-balancing/build-a-worker)
before setting health ports, readiness status codes, timeouts, or routing settings.

Bind the intended interface, align the server's port with platform configuration,
and implement the required health route. Separate process liveness from application
readiness: downloading/loading a required model must not report ready. A health
response alone still does not prove a real request works.

Load reusable models once per worker process. Multiple web processes may each load
another model copy; size them deliberately. Match HTTP concurrency to safe model/GPU
capacity and return appropriate errors or backpressure. Check request timeouts,
stream disconnect/cancellation behavior and per-request temporary-file isolation.
Avoid mutable global inputs, output accumulation, and request-specific filenames
shared across concurrent callers.

Do not assume durable memory, local files or session affinity across workers. Persist
required outputs externally and document any session requirements. Check the actual
endpoint's access controls; do not add an unauthenticated administrative route.

## Verify

- Startup progresses to model-aware readiness; missing credentials/models fail clearly.
- A real request through the endpoint's external URL yields correct output.
- Invalid input returns a useful error; a subsequent valid request still works.
- Repeated and relevant concurrent requests stay within measured memory/disk limits.
- Relevant streaming/disconnect behavior cleans owned temporary work.
- Worker replacement retains required durable output and leaves shared versions intact.

Supply exact route examples, health/app port configuration, target type, image identity,
environment/secret names, storage and hardware needs, and relevant worker/scaling bounds.
Read current tool fields through the infra lanes; do not copy an old API's endpoint-type
name or assume queue-based deployment settings work for load balancing.
