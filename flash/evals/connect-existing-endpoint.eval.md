# Call an existing Runpod endpoint by ID

## Prompt

I already have a Runpod serverless endpoint with ID `abc123xyz`. Using
runpod-flash, send it a synchronous job `{"prompt": "hello"}` and print the
output. The first request may cold-start and take longer than a minute.

## Expected behavior

The agent should:

1. Create `Endpoint(id="abc123xyz")` — connects to the existing endpoint, no provisioning
2. Submit the job with `runsync`, raising the timeout above the 60s default to survive cold start
3. Print `job.output`

## Assertions

- Creates `Endpoint(id="abc123xyz")` (no `name=`, `gpu=`, or `image=` needed)
- Uses `await ep.runsync({"prompt": "hello"}, timeout=...)` with a timeout > 60 (e.g. 120) OR uses `await ep.run(...)` + `await job.wait()` to avoid the 60s cap
- Accesses the result via `job.output`
- Uses `await` on the call
- Does NOT pass `id=` together with `image=` (`id=` + `name=` is legal and harmless)
