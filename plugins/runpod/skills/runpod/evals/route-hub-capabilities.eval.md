# Routing: existing Hub listings use the available control plane

This is a manual regression scenario, not an automated test. Use simulated tool
results for deployment variants; the routing check does not need paid resources.

## Prompt

The Runpod MCP tools are connected. Find an existing vLLM worker in the Runpod
Hub and show me its deployment configuration. I do not need a shell command, and
I am not asking you to deploy it yet.

## Setup

The session's live MCP tool metadata exposes Hub browsing and release
configuration reads. Use that metadata for the call shape, rather than a copied
schema in these guides.

## Expected behavior

Routes the read through runpod-mcp and its discovery journey. Reads the relevant
listing configuration and reports it without creating an endpoint, installing
runpodctl, or requesting CLI credentials. A working MCP connection is sufficient
for this request.

## Assertions

- Checks the live MCP capability before choosing a lane.
- Does not classify Hub browsing or deployment as categorically CLI-only.
- Does not create a resource for a read-only request.
- Uses the live tool schema for parameters rather than inventing a call shape.
- Does not replace browsing an existing listing with authoring a new image.

## Variants

1. **Deployment requested; MCP exposes the operation.** Consults a matching
   golden path before planning, then follows serverless-deploy through MCP,
   preserving pricing, configuration, real-job verification and cleanup steps.
   A golden path containing CLI commands does not by itself force a CLI switch.
2. **Shell-only session.** Routes browsing/deployment to runpodctl and inspects
   its live help for exact commands.
3. **Reproducible CLI command requested.** Uses runpodctl even with MCP connected.
4. **MCP lacks the requested Hub operation.** Verifies that against the live tool
   surface and hands that operation to runpodctl; does not extrapolate an absent
   operation into a claim that all Hub tasks require the CLI.
5. **Endpoint workflow guide opened first.** Follows its link to the router's
   capability matrix. The guide's CLI deployment example does not override a
   connected MCP operation or require CLI setup for an MCP-capable Hub task.
