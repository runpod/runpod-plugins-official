---
concepts: [api-key]
---

# Connecting the Runpod MCP server

> **With a user present, connect with OAuth.** "Sign in with Runpod" needs no key on disk and
> covers MCP work. OAuth authenticates the MCP *only*, so get a `RUNPOD_API_KEY` later, when
> a task reaches a CLI-only step (see the router skill's "First run").

**Hosted + OAuth (default)**: the user approves the sign-in in the browser on first connect.

```bash
# configure a single client by hand (OAuth on first connect)
claude mcp add --transport http runpod -s user https://mcp.runpod.io/   # Claude Code
codex mcp add runpod --url https://mcp.runpod.io/                       # Codex (waits for browser approval)
gemini mcp add -s user -t http runpod https://mcp.runpod.io/            # Gemini CLI
```

For Cursor, Windsurf, VS Code, opencode, Pi, and Claude Desktop, the installer writes the
config without prompts when you name the client: `npx @runpod/mcp-server@latest add --client <id>`
(`--list` shows the ids). Without `--client` and without a terminal it configures nothing.
Other clients: add an HTTP (streamable HTTP) server entry named `runpod` with URL
`https://mcp.runpod.io/` to the client's MCP config.

If sign-in fails with `redirect_uri is not allowed`, this client can't use OAuth with the
hosted server. Use an API key instead (below).

**Hosted + API key**: for no user in the loop, or a client that can't do OAuth. The same key
also unlocks runpodctl + flash:

```bash
claude mcp add --transport http runpod -s user https://mcp.runpod.io/ \
  --header "Authorization: Bearer $RUNPOD_API_KEY"
```

**Local (stdio)** — runs the server as a subprocess with your key:

```bash
claude mcp add runpod -s user -e RUNPOD_API_KEY=YOUR_KEY -- npx -y @runpod/mcp-server
```

After connecting, reconnect the client (in Claude Code, `/mcp`) and the tools
appear in the session.
