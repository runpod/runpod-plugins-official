# Routing: diagnosing a failing serverless job (health / status / worker logs)

## Prompt

I'm in a plain terminal — no MCP tools connected. My serverless endpoint
`ep-abc123` just returned a `FAILED` job (`job-xyz`). Walk me through finding out
why. Then tell me what changes if I *do* have the Runpod MCP connected.

## Expected behavior

Follows golden path 15 (`runpod/golden-paths/15-monitor-and-debug.md`), which
splits into three signals — all three now reachable from the CLI lane:

1. **Worker/job counts → `runpodctl serverless health ep-abc123`** (v2.9.0+). Not a
   hand-built `curl` to `https://api.runpod.ai/v2/ep-abc123/health` — that is the
   fallback for an older binary or a copy-paste snippet, and the CLI returns the
   same payload verbatim.
2. **The job itself → `runpodctl serverless status ep-abc123 job-xyz`**. Reads
   `status`, `error`, `retries`, and the `delayTime` vs `executionTime` split to
   decide scaling-bound vs handler-bound, and takes `workerId` from it. Knows the
   command exits **1** with `{"code":"job_failed"}` on a terminal `FAILED` while the
   job payload is still on stdout — that is the job failing, not the CLI.
3. **Worker logs → `runpodctl serverless logs ep-abc123`** (v2.10.0+), narrowed with
   `--worker <workerId>` from step 2. Output is json lines
   (`{source,line,ts,workerId}`), so it pipes to `jq`. **Not** a hand-built SSE read
   against `v2-rest.runpod.io/.../logs` and not "the CLI can't do this" — that path is
   the fallback for a pre-v2.10.0 binary, alongside the Console **Workers** tab.
   Reads `--source container` for the handler's traceback, and knows `--source system`
   with repeated "start container" and no container output means a crash loop.

With MCP connected: `endpoint-health` and `get-job-status` are reasonable substitutes
for steps 1–2, and `list-endpoint-workers` → `stream-worker-logs` for step 3 returns
already-parsed, bounded frames — a convenience over the CLI's json lines, **not** a
capability the CLI lacks. Only `stream-job` (incremental job output) is genuinely
MCP-only.

## Assertions

- Uses `runpodctl serverless health` and `runpodctl serverless status` rather than
  steering to raw `curl` for `/health` and `/status`.
- Does **not** claim runpodctl is limited to create/list/delete — it also invokes
  (`serverless run`), polls (`serverless status`), reports health, and edits config
  (`serverless update`).
- Reaches `runpodctl serverless logs` for the worker logs. Does **not** assert that
  runpodctl cannot read worker logs, and does **not** require MCP to be connected to
  get them.
- If it falls back to the raw v2 REST SSE path (older binary), time-bounds the read
  (`curl -m`) rather than tailing an open stream.
- Treats a non-zero exit with `job_failed` as the worker's failure, not a CLI or
  auth problem.
