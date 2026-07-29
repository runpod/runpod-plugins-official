# Tie-break: runpod-mcp vs runpodctl on overlapping infra CRUD

## Prompt

The Runpod MCP tools are connected in my session. Two things: (a) list my pods,
and (b) create a pod from my saved template `tmpl-abc` with a CPU flavor. Which
tool for each, and why?

## Expected behavior

Per the capability matrix in `runpod/SKILL.md` (choose by capability first,
environment second):

1. **(a) list pods → runpod-mcp** — a simple structured read, and MCP is connected.
2. **(b) create a pod from a template *with* a CPU flavor → runpodctl** — MCP's
   `create-pod` supports `templateId` and `computeType: "CPU"` individually, but not
   together: a template deploy is GPU-and-v2-only, so the combination returns a 400.
   `runpodctl pod create --template-id … --compute-type cpu` does it in one call.
   This is the "hand pod creation to runpodctl when it needs a capability MCP lacks"
   rule — note the capability is the *combination*, not either half.

## Assertions

- Routes the **list** to runpod-mcp (MCP connected → prefer it for simple reads/CRUD).
- Routes the **template + CPU pod create** to runpodctl, explicitly because MCP rejects that combination — not because it lacks `templateId` or CPU support, which it has.
- Does NOT blanket-route everything to MCP just because it's connected.
