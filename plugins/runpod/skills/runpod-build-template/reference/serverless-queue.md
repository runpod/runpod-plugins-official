---
concepts: [serverless-handler, serverless-endpoint, worker, job, container-image]
---

# Queue worker contract

Run the application's real operation through a handler registered with
`runpod.serverless.start({"handler": handler})`. Use the current
[handler documentation](https://docs.runpod.io/serverless/workers/handler-functions)
and selected SDK version for exact local test, streaming and concurrency behavior.
Do not add an HTTP server or SSH just because the Pod variant has one.

Define the input schema, operation, output shape and a representative request before
writing the adapter. Validate types/ranges/required fields and surface failures through
the supported job error mechanism. Do not swallow exceptions and return a success
object. Avoid wrapping a UI with a handler that never executes the requested workload.

Initialize reusable models once per worker process. Keep per-job temporary files and
mutable inputs isolated, clean owned temporary data after both success and failure,
and avoid accumulating output tensors or global request state. Start with conservative
concurrency; async code alone does not make a model or shared GPU safe to run concurrently.

Worker-local disk/memory is disposable. Write required durable outputs to a supported
external destination and return retrievable identifiers/URLs. Check current payload
limits and avoid embedding large binary results in JSON. Runtime storage/auth choices
must match the target; inspect [Serverless storage](https://docs.runpod.io/serverless/storage/overview).
Make retry-sensitive writes idempotent when the workload has side effects; treat
cancellation/interruption as possible partial completion, not guaranteed rollback.

## Verify

1. Invoke the real handler with representative input, then verify output correctness.
2. Submit through the Runpod endpoint when authorized; capture request/job identity,
   observed status/error and actual output retrieval. A worker listed ready is insufficient.
3. Run repeated jobs, an invalid job followed by a valid one, and relevant cancellation
   or concurrency cases; watch memory and disk accumulation.
4. Replace/scale a worker and verify needed outputs survive and independent workers
   do not corrupt shared model downloads or mutable environments.

Record source/image/SDK identity, GPU/memory requirements, container disk, environment
and secret names, model/output locations, and suggested/measured worker and scaling
bounds. Separate queue delay, initialization and execution where observable. Never
equate total request delay with proven image-pull or cold-cache time.
