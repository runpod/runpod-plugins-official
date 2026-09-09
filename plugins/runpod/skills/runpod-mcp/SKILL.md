---
name: runpod-mcp
description: >-
  Manage Runpod infrastructure — pods, serverless endpoints, jobs, templates,
  network volumes, container-registry auth, GPU/CPU catalog, and billing — via
  the Runpod MCP server's structured tool calls. Use when the Runpod MCP tools
  (create-pod, list-endpoints, …) are connected in this session, or to connect
  them (hosted OAuth or local npx). Prefer this over runpodctl for plain infra
  CRUD when MCP is available; use runpodctl for the terminal, file transfer, or
  SSH setup. Connection lane only — the server itself carries its tool surface
  and its own task playbooks, so read those rather than a list kept here.
allowed-tools: Bash(npx:*), Bash(claude:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Runpod MCP

The Runpod MCP server exposes Runpod's control plane as structured tool calls,
so an MCP-capable agent can manage infrastructure without shelling out. It is the
same Runpod REST API that `runpodctl` uses — pick MCP when its tools are
connected (typed params, structured errors, no shell quoting).

**For a multi-step job, read the worked example before calling tools.** Tool calls are
easy to issue and easy to issue in the wrong order — the verified end-to-end sequences
live in [runpod/golden-paths/README.md](../runpod/golden-paths/README.md) (image →
template → endpoint, pod → volume → serverless, multi-region, autoscaling, monitoring).
They are how the job was done before, costs included. The server's own resources cover
procedure within one journey; the paths cover what order to do a whole job in.

**This skill covers connecting and lane choice only.** What the tools are and what
each one accepts comes from the connected server, not from this file — see
[The server is the source of truth](#the-server-is-the-source-of-truth). That split
is deliberate: the server ships weekly, a tool list written down here does not, and
a stale list reads as authoritative right up to the moment it is wrong.

## Connect

Connect the hosted server with **your API key as a Bearer header** if you also use runpodctl/flash — that one key auths the MCP *and* the CLIs (the 80% path):

```bash
claude mcp add --transport http runpod -s user https://mcp.getrunpod.io/ \
  --header "Authorization: Bearer $RUNPOD_API_KEY"
```

Plain **OAuth** ("Sign in with Runpod", via `npx @runpod/mcp-server@latest add`) is MCP-only — the CLIs stay unauthed, so use it only for MCP-only work. Local **stdio** runs the server as a subprocess with your key. Those variants + the key-vs-OAuth tradeoff: **[reference/connect.md](reference/connect.md)**. After connecting, reconnect the client (in Claude Code, `/mcp`) so the tools load.

**Verify it's live (do this before relying on MCP):** in Claude Code run `/mcp` —
`runpod` should show **Connected**, not *Needs authentication* (if it's the latter,
sign in there first; the bundled plugin server registers the URL but stays inert
until you authenticate). Confirm a real call works by asking for `list-endpoints`.
If the `runpod` tools aren't present at all, the server isn't connected — (re)run the
install above, or fall back to **runpodctl** for this task.

**Check the server version (which REST API it drives):** the MCP `initialize` handshake
returns it in `serverInfo.version`. `/mcp` in Claude Code shows it, or probe the hosted
server directly:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
| curl -s -X POST https://mcp.getrunpod.io/ \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -d @-
```

## The server is the source of truth

Once connected, read the server — do not reason about its tools from memory or from
this file.

1. **The tool list and every parameter** come from the client's own view of the
   connected server: `/mcp` in Claude Code, or `tools/list`. Each tool carries its
   own parameter descriptions, generated from Runpod's REST v2 contract. Check there
   before concluding a capability exists *or* doesn't — an absence you infer from a
   doc is the one claim that rots silently.
2. **The task playbooks come from the server too.** It publishes them as MCP resources
   under `runpod://skills/` — a router at `runpod://skills/runpod` plus a journey skill
   per task (serverless deploys, pod diagnosis, endpoint operations, cost audits,
   catalog discovery, API-boundary honesty). Enumerate them with `resources/list` and
   read the routed one before a multi-step job. They are versioned with the server, so
   they describe the tools you actually have.
3. **The wire contract** is the Runpod v2 OpenAPI document at
   `https://api.runpod.io/v2/openapi.json`, for fields beyond the tool surface.

Coverage, at the resource level only, so you can tell whether this lane applies at
all: pods, serverless endpoints and their workers and jobs, the Hub (browse and
deploy), public pay-per-use endpoints, templates, network volumes, container-registry
auth (including AWS ECR delegations), the GPU/CPU/data-center catalog, and billing.
Log streaming for pods, workers, and jobs is included. Anything finer than that —
which fields a create accepts, which tier is immutable, what a delete returns — read
from the live schema.

One protocol quirk worth knowing, because it looks like a bug: delete tools can return
`isError: true` with "Unexpected end of JSON input" **even on success**, since the REST
API answers 204 No Content. Confirm with a follow-up `get-`/`list-` (a deleted resource
then 404s) rather than retrying the delete.

For concepts (pods vs serverless, GPU selection, storage), read `../runpod-usage/`.
For whole multi-resource jobs, read the golden paths linked at the top of this skill.

## Use MCP vs runpodctl

- **Use runpod-mcp** when the tools are connected AND the task is infra CRUD or a
  serverless job call the server exposes. Cap large job/log output to a file.
- **Use runpodctl instead** for: **`send`/`receive`** file transfer, **SSH** key
  management, **`doctor`** setup, **model cache** — or any shell-only agent, or
  when the user wants a reproducible command.
- **Hand pod creation to runpodctl** for a **multi-GPU priority list** (v2 `create-pod`
  takes one GPU type; check the live schema before assuming, and watch for a `_warning`
  on an otherwise-successful create), or for a **template + CPU** pod together, which
  v2 does not express. Each alone is fine in MCP: `templateId` (each field you pass
  replaces the template's whole value rather than merging) or `computeType: "CPU"`.
- **Not this lane:** writing/deploying your own Python (→ flash); downloading
  models or building/pushing images (→ companion-clis).

## Source & docs

- Server source: https://github.com/runpod/runpod-mcp
- Package (npm): https://www.npmjs.com/package/@runpod/mcp-server
- Hosted endpoint: https://mcp.getrunpod.io/
- Docs: https://docs.runpod.io
