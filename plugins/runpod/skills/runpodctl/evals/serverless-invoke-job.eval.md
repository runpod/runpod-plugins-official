# Invoke a serverless endpoint and get the result

## Prompt

I have a serverless endpoint `ep-abc123` running a vLLM worker. Send it
`{"prompt": "why is the sky blue?"}` and show me what it returns.

## Expected behavior

The agent should:

1. Invoke with `runpodctl serverless run ep-abc123 --input '{"prompt":"why is the sky blue?"}'`,
   which submits the job and polls until it is terminal.
2. Pass only the **handler** payload — the cli wraps it as `{"input": ...}` itself.
3. Read the job payload off stdout (it is printed even when the job fails) and report the
   worker's output or its `error`.
4. If the wait budget runs out with a `timeout` code whose message names a
   `serverless status` command, poll that command rather than re-invoking.

## Assertions

- Uses `runpodctl serverless run ep-abc123` with `--input` (or `--input-file`)
- Does NOT hand-build a `curl` to `https://api.runpod.ai/v2/ep-abc123/run` or `/runsync`, and does NOT construct an `Authorization: Bearer` header by hand
- Does NOT double-wrap the payload as `{"input":{"prompt":...}}`
- On a `timeout`, polls with `runpodctl serverless status ep-abc123 <job-id>` instead of re-submitting the job
- Treats a `job_failed` exit as the worker's failure (payload on stdout), not as a cli/auth problem
