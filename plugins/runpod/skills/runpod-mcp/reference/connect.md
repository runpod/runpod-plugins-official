---
concepts: [api-key]
---

# Connecting the Runpod MCP server

> **If you also use runpodctl/flash, connect the hosted MCP with your API key (Bearer),
> not OAuth.** OAuth authenticates the MCP *only* — the CLIs stay unauthed. A single
> `RUNPOD_API_KEY` used as a Bearer header auths the MCP **and** unlocks runpodctl + flash.
> See the router skill's "First run" for the full auth order.

**Hosted + API key (recommended for full-tool access)** — one key drives everything:

```bash
claude mcp add --transport http runpod -s user https://mcp.getrunpod.io/ \
  --header "Authorization: Bearer $RUNPOD_API_KEY"
```

**Hosted + OAuth** — no key on disk, but MCP-only (CLIs stay unauthed). Fine if you only
need the MCP this session:

```bash
# guided installer — detects your agents and configures them (OAuth on first connect)
npx @runpod/mcp-server@latest add

# or configure a single client by hand (Claude Code shown)
claude mcp add --transport http runpod -s user https://mcp.getrunpod.io/
```

**Local (stdio)** — runs the server as a subprocess with your key:

```bash
claude mcp add runpod -s user -e RUNPOD_API_KEY=YOUR_KEY -- npx -y @runpod/mcp-server
```

After connecting, reconnect the client (in Claude Code, `/mcp`) and the tools
appear in the session.
