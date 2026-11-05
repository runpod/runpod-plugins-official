# Golden path 18: raise per-worker throughput with a concurrent handler

## Prompt

Each of my serverless jobs mostly waits on an external HTTP API. Can one worker handle
several jobs at once instead of me paying for more workers?

## Expected behavior

Follows [golden path 18](../golden-paths/18-concurrent-handler.md): an `async` handler
with real `await` points **and** a `concurrency_modifier` returning N; either one alone
still runs one job at a time. Says this suits I/O-bound work only (CPU/GPU-bound jobs
time-slice and can exhaust VRAM), that concurrency ramps up over the first polls after a
cold start, and that module-level state is now shared across jobs. Points at golden path
13 for scaling out instead.

## Assertions

- Requires both `async` + `await` and `concurrency_modifier`
- Limits the advice to I/O-bound work
- Warns that shared state is touched concurrently
- Warms the worker before measuring throughput
