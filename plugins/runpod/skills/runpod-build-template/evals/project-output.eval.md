# Complete output and transfer to another app

## Prompt

“Package this existing Node HTTP app as a Runpod Pod. Preserve my repository layout.
It reads PORT, exposes POST /convert, and writes outputs to DATA_DIR. I want files only.”
Supply a real minimal repository containing package/lock files, server code and a
representative conversion test. Independently repeat with a Python function suitable
for a queue job, and an existing HTTP application for load balancing.

## Expected behavior

Inspect actual input/operation/output and preserve app conventions. Produce a documented
Dockerfile, `.dockerignore`, required files, complete README/deployment-settings handoff
and useful-output check. Use the language's existing runtime/lock strategy. Generate only
the selected target; supporting startup/handler files depend on the real app.

## Assertions

- No forced Python, SSH, persistent venv, universal directory layout or invented YAML.
- Ports, env/secret names, mounts, command, image/hardware and worker fields as applicable
  have concrete values or explicit unresolved values and a way to resolve them.
- Container runtime is outside data mounts; required output persistence is documented.
- Tests call the provided app's real operation; no mock wrapper substitutes for it.
- A description-only/UI-only request resolves material operation ambiguity first.
- A Hub/registry user's quickstart is usable without a Docker tutorial or development
  history. Build commands remain available for a source-build route; detailed evidence
  is retained separately and material deployment limitations remain visible.
