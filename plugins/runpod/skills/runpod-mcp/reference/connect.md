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
# configure a single client by hand (OAuth on first connect)
claude mcp add --transport http runpod -s user https://mcp.getrunpod.io/   # Claude Code
codex mcp add runpod --url https://mcp.getrunpod.io/                       # Codex
gemini mcp add -s user -t http runpod https://mcp.getrunpod.io/            # Gemini CLI
```

Other clients (Cursor, VS Code, Windsurf, Cline, opencode): add an HTTP server entry
named `runpod` with URL `https://mcp.getrunpod.io/` to the client's MCP config.

The guided installer, `npx @runpod/mcp-server@latest add`, is an interactive wizard for a
person at a terminal (Claude Code, Cursor, Windsurf, Claude Desktop, VS Code). An agent
should not run it: in a non-interactive shell it can't take input. Ask the user to run it
instead.

**Local (stdio)** — runs the server as a subprocess with your key:

```bash
claude mcp add runpod -s user -e RUNPOD_API_KEY=YOUR_KEY -- npx -y @runpod/mcp-server
```

After connecting, reconnect the client (in Claude Code, `/mcp`) and the tools
appear in the session.
