# Call an existing Runpod endpoint by ID

## Prompt

I already have a Runpod serverless endpoint with ID `abc123xyz`. Using the Runpod Python SDK,
send it a synchronous job `{"prompt": "hello"}` and print the output. The first request may
cold-start and take longer than a minute.

## Expected behavior

The agent should:

1. Create `runpod.Endpoint("abc123xyz")` — no provisioning
2. Submit with `run_sync({"prompt": "hello"}, timeout=...)` and a timeout that covers a cold
   start, or `run(...)` then `job.output(timeout=...)`
3. Print the result

## Assertions

- Uses `runpod.Endpoint("abc123xyz")`
- Passes `{"prompt": "hello"}` as the input (the client wraps it in `{"input": ...}`; the agent
  does NOT double-wrap it as `{"input": {"prompt": ...}}`)
- Sets a timeout above 60 seconds or uses `run()` + `output(timeout=...)`
- Does NOT create an `App` or decorate a function for this
- Does NOT import from `runpod_flash`
