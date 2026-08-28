---
name: protect-runpod
description: >-
  Use HOL Guard before mutating or cost-bearing Runpod CLI operations. Set up
  Guard for the current supported agent harness, verify protection, preview
  command-safety coverage, and only then run runpodctl changes. Read-only
  Runpod discovery can continue without this skill.
allowed-tools: Bash(hol-guard:*), Bash(runpodctl:*), Bash(pipx:*)
compatibility: Linux, macOS
metadata:
  author: hashgraph-online
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Protect Runpod operations with HOL Guard

Use this skill when a Runpod task can create, update, delete, deploy, stop,
terminate, or otherwise change billable infrastructure. It adds HOL Guard as a
pre-execution safety layer around the agent harness; it does not replace the
`runpodctl` skill or Runpod's own authorization.

## Safety boundary

Read-only commands such as `runpodctl pod list`, `runpodctl gpu list`,
`runpodctl datacenter list`, `runpodctl template search`, and resource `get`
operations can follow the normal Runpod skills.

Before a mutating or cost-bearing `runpodctl` command:

1. Verify HOL Guard is installed:
   ```bash
   hol-guard --version
   ```
   If the command is missing, install it in an isolated CLI environment:
   ```bash
   pipx install hol-guard
   ```
2. Check the local protection posture and discover supported harnesses:
   ```bash
   hol-guard status
   hol-guard detect --json
   ```
3. If the current harness is not protected, do **not** run the Runpod mutation
   yet. Install Guard for the detected harness and relaunch that harness through
   Guard:
   ```bash
   hol-guard install <harness>
   hol-guard run <harness>
   ```
   Continue the Runpod mutation only from the protected harness session.
4. Preview the exact Runpod command without executing it:
   ```bash
   hol-guard command test 'runpodctl <resource> <action> ...'
   ```
   `command test` is inspection only. It reports whether a built-in command
   safety extension recognizes the command; it is **not** proof that an
   unprotected current process is enforced. If no extension recognizes
   `runpodctl`, keep the harness-level Guard requirement above.
5. Inspect live `runpodctl ... --help`, state the resource/cost impact, then run
   the exact command only after Guard reports the harness protection is active.

## Fail closed

- If `hol-guard status` or `hol-guard detect --json` errors, stop before a
  mutating Runpod command and surface the Guard error.
- If Guard requests review, do not bypass it. Use `hol-guard approvals` and wait
  for an explicit allow decision.
- If the user declines Guard setup, do not silently execute the protected
  mutation. Offer the exact `runpodctl` command for manual review instead.
- Never claim `hol-guard command test` executed, approved, or blocked a Runpod
  action. It only inspects command coverage.
- Keep `RUNPOD_API_KEY` out of command strings and logs; `runpodctl` should read
  it from the environment.

## Example

For a request to create a GPU pod, first prepare the final `runpodctl pod
create ...` command from live help. Verify the current harness is protected as
above, run `hol-guard command test '<exact command>'`, then execute the
`runpodctl` command from the protected session. Record any Guard review or
denial before proceeding.
