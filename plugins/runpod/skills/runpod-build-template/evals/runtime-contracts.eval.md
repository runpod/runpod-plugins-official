# Correct runtime and recovery

## Prompt

Package three independent real apps: an application-only Pod, a queue job with durable
file output, and an HTTP model service for load balancing. Include invalid input,
missing model/credential, repeated requests, and relevant concurrency/cancellation cases.

## Expected behavior

Implement only each target's required startup. Readiness follows required initialization;
each test exercises useful output. Reuse loaded models per process while isolating
request data and bounded concurrency. Required outputs survive worker replacement.

## Assertions

- Pod does not acquire unwanted SSH/Jupyter; promised interfaces remain working.
- A development Pod keeps its base startup process running after a finite check;
  repeat the check and restart with existing reports without a crash loop or lost data.
- A batch-only Pod has an explicit result-retention and stop/terminate plan; successful
  process exit alone is not evidence that billing stopped.
- Queue starts the real SDK handler and surfaces failures; it is not an HTTP mock.
- LB keeps routes and current health/port contract, without a queue adapter.
- LB reads Runpod's `PORT` (default 80) and aligns health checks; `/ping` returns
  204 during model loading, 200 once ready, and an unhealthy code on failure.
- Queue input limits are 10 MB for `/run` and 20 MB for `/runsync`; large files use URLs.
- Invalid request followed by valid request succeeds; repeated work does not accumulate
  unintended memory/temp files; web-process model duplication is considered.
- Retry-sensitive side effects and cancellation cleanup match the actual application.
- Process lifetime, signals, permissions and LF startup scripts are checked as relevant.
