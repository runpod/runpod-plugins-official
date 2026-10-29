# Tie-break: runpod-mcp vs runpodctl on overlapping infra CRUD

## Prompt

The Runpod MCP tools are connected in my session. Three things: (a) list my pods,
(b) create a pod from my saved template `tmpl-abc` with a CPU flavor, and (c) copy
`./data.tar` from my laptop onto that pod. Which tool for each, and why?

## Expected behavior

Per the capability matrix in `runpod/SKILL.md` (choose by capability first,
environment second):

1. **(a) list pods → runpod-mcp**: a simple structured read, and MCP is connected.
2. **(b) template + CPU pod create → runpod-mcp**: `create-pod` takes `templateId`
   together with a `cpu` object (`{id, vcpuCount}`, flavor ids from `list-cpu-types`);
   the combination was live-verified 2026-10-29, and a CPU pod skips the template's
   persistent mount and CUDA constraint. runpodctl v3 sends the same v2 create, so
   switching lanes would not help.
3. **(c) file transfer → runpodctl** (`runpodctl send` / `receive`), even though MCP
   is connected: MCP has no file-transfer tool. This is the "hand off to runpodctl
   when an operation needs a capability MCP lacks" rule.

## Assertions

- Routes the **list** to runpod-mcp (MCP connected → prefer it for simple reads/CRUD).
- Routes the **template + CPU pod create** to runpod-mcp `create-pod` with `templateId` and a `cpu` object, never a `computeType` field (v2 has none).
- Routes the **file copy** to runpodctl `send`/`receive`, explicitly because MCP has no tool for it.
- Does NOT blanket-route everything to MCP just because it's connected.
