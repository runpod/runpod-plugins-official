# When to use the MCP lane (and when to defer)

## Prompt

The Runpod MCP tools are connected. I need to: (1) list my serverless endpoints,
(2) deploy a vLLM worker from the Runpod Hub, and (3) grab a pod's recent logs.
Handle each.

## Expected behavior

Per `runpod-mcp/SKILL.md`:

1. **(1) list endpoints → runpod-mcp** — a structured read the server exposes; MCP
   is connected, so prefer it.
2. **(2) deploy from the Hub → runpod-mcp** — `deploy-hub-repo` deploys a Hub
   repo's listed release as an endpoint, so a connected MCP handles this directly;
   `list-hub-repos` finds the repo first.
3. **(3) pod logs → runpod-mcp** — the server exposes pod log streaming; a
   structured read is a good fit.

## Assertions

- Routes the endpoint **list** and the **pod logs** to runpod-mcp (connected → structured reads).
- Routes the **Hub deploy** to runpod-mcp via `deploy-hub-repo` (optionally `list-hub-repos` first).
- Does NOT claim MCP lacks Hub tools or fall back to runpodctl for the Hub deploy while MCP is connected.
