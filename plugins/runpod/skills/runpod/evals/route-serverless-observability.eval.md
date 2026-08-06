# Routing: diagnosing a failing serverless job (health / status / worker logs)

## Prompt

I'm in a plain terminal — no MCP tools connected. My serverless endpoint
`ep-abc123` just returned a `FAILED` job (`job-xyz`). Walk me through finding out
why. Then tell me what changes if I *do* have the Runpod MCP connected.

## Expected behavior

Follows golden path 15 (`runpod/golden-paths/15-monitor-and-debug.md`), which
splits into three signals with different lanes:

1. **Worker/job counts → `runpodctl serverless health ep-abc123`** (v2.9.0+). Not a
   hand-built `curl` to `https://api.runpod.ai/v2/ep-abc123/health` — that is the
   fallback for an older binary or a copy-paste snippet, and the CLI returns the
   same payload verbatim.
2. **The job itself → `runpodctl serverless status ep-abc123 job-xyz`**. Reads
   `status`, `error`, `retries`, and the `delayTime` vs `executionTime` split to
   decide scaling-bound vs handler-bound, and takes `workerId` from it. Knows the
   command exits **1** with `{"code":"job_failed"}` on a terminal `FAILED` while the
   job payload is still on stdout — that is the job failing, not the CLI.
3. **Worker logs → NOT runpodctl.** There is no serverless worker-log command in
   the CLI. Shell-only, that means the v2 REST SSE path
   (`GET https://v2-rest.runpod.io/v2/serverless/ep-abc123/workers/<workerId>/logs`,
   time-bounded with `curl -m`) or the Console **Workers** tab.

With MCP connected: `endpoint-health` and `get-job-status` become reasonable
substitutes for steps 1–2, and step 3 gets a real upgrade — `list-endpoint-workers`
→ `stream-worker-logs` returns already-parsed frames instead of raw SSE. The MCP
lane is the *only* one of the two tool lanes that can read worker logs.

## Assertions

- Uses `runpodctl serverless health` and `runpodctl serverless status` rather than
  steering to raw `curl` for `/health` and `/status`.
- Does **not** claim runpodctl is limited to create/list/delete — it also invokes
  (`serverless run`), polls (`serverless status`), reports health, and edits config
  (`serverless update`).
- Correctly identifies worker logs as the one signal with no runpodctl command, and
  names the v2 REST SSE path / MCP `stream-worker-logs` / Console instead.
- Time-bounds any SSE read (`curl -m`), rather than tailing an open stream.
- Treats a non-zero exit with `job_failed` as the worker's failure, not a CLI or
  auth problem.
