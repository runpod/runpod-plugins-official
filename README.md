# Runpod Official Plugins

The **official** plugin marketplace of skills for AI agents to manage GPU workloads on Runpod —
pods, serverless endpoints, jobs, templates, and volumes — via the Runpod MCP
server, `runpodctl`, and `flash`.

This repo ships **one plugin**, [`runpod`](plugins/runpod/), with eight skills total:
one router plus seven lanes, the hosted Runpod MCP server config, and worked golden paths.

**Compatibility:** installs as a native plugin in **Claude Code, Codex, Gemini,
and opencode** (with auto-update), and as skills via **skills.sh** for Cursor,
Copilot, Windsurf, Cline, and 17+ other agents — all from the same manifest.

## Quick start

**Install** — works with every agent (Claude Code, Codex, Cursor, Copilot, Windsurf, Cline,
Gemini, opencode, +more). The first line is all you need; drop any others you won't use:

```bash
npx skills add runpod/runpod-plugins-official # the skills — any agent (essential)
curl -sSL https://cli.runpod.net | bash       # runpodctl — infra CLI (or: brew install runpod/runpodctl/runpodctl)
uv tool install runpod-flash                  # flash — deploy your own code (optional; or: pip install runpod-flash)
npx @runpod/mcp-server@latest add            # hosted MCP server — guided setup, OAuth (optional)
```

Then authenticate — one API key covers everything (from
[the console](https://runpod.io/console/user/settings)):

```bash
export RUNPOD_API_KEY=<key>      # current shell only — add to ~/.zshrc (or ~/.bashrc) to persist
# or, to save it permanently:
runpodctl doctor                 # prompts for the key and writes ~/.runpod/config.toml
```

Now just ask in plain English — the skill drives the tools for you:

> *"list my Runpod endpoints"*  ·  *"spin up an A100 pod"*  ·  *"deploy this handler to serverless"*

That's it. Notes:
- **Claude Code** can install natively instead (auto-wires the hosted **MCP server** + OAuth) —
  see [Install → Claude Code](#claude-code). MCP auth details: [Authentication](#authentication).
- Companion CLIs (`docker`/`gh`/`hf`/`aws`) install separately, per task — see
  [`companion-clis`](plugins/runpod/skills/companion-clis/SKILL.md).

## Install

Same repo, one manifest — pick your agent below. Every route installs the same
eight skills (one router plus seven lanes), plus a hosted **Runpod MCP server** for
control-plane tools.
Then [authenticate](#authentication).

### Claude Code

```
/plugin marketplace add runpod/runpod-plugins-official
/plugin install runpod@runpod
/reload-plugins
```

Installing **also wires up the hosted Runpod MCP server** (via the bundled
[`.mcp.json`](plugins/runpod/.mcp.json)) — no separate MCP setup. Authenticate it:
`/mcp` → **runpod** → *Sign in with Runpod* (OAuth; no key on disk).

**Verify:** `/plugin` shows **Runpod** under *Installed*; then ask *"list my Runpod
endpoints"* — it should call the MCP `list-endpoints` tool.

### Codex

```bash
codex plugin marketplace add https://github.com/runpod/runpod-plugins-official.git
codex /plugins        # → open the "Runpod" marketplace tab → Runpod → Install (reload if prompted)
```

Manage the source: `codex plugin marketplace list` · `… upgrade runpod` · `… remove runpod`.

Codex may **not** auto-wire the bundled MCP — if the `runpod` MCP tools don't appear
after install, add the hosted server manually:

```bash
codex mcp add runpod --transport http https://mcp.getrunpod.io/
```

**Verify:** ask a Runpod task (the skill/router should answer); once the MCP is added,
*"list my Runpod endpoints"* should call a tool.

### Everything else — Cursor, Copilot, Windsurf, Cline, opencode, Gemini (+17)

Install the skills via **skills.sh** (reads the same
[`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)):

```bash
npx skills add runpod/runpod-plugins-official
# just one skill:
npx skills add https://github.com/runpod/runpod-plugins-official/tree/main/plugins/runpod/skills/runpodctl
```

Gemini can also install natively via the bundled
[`gemini-extension.json`](plugins/runpod/gemini-extension.json) (see your client's
extension docs). For these clients, add the **MCP server** yourself — the guided
installer configures most agents:

```bash
npx @runpod/mcp-server@latest add     # detects your agent + sets up the hosted MCP (OAuth)
```

See [`runpod-mcp/SKILL.md`](plugins/runpod/skills/runpod-mcp/SKILL.md) for hosted vs
local (stdio) MCP setup and all client options.

## Authentication

Auth is needed in **two places**, and **one Runpod API key covers both**:

| What | What it needs | How |
| --- | --- | --- |
| `runpodctl` + `flash` (the CLIs) | `RUNPOD_API_KEY` (env or saved) | `export RUNPOD_API_KEY=<key>`, or `runpodctl doctor` to save it |
| Hosted **Runpod MCP** server (infra tools) | OAuth **or** the same key | `/mcp` sign-in, **or** pass the key as a Bearer header |

**Fastest path — one key, everything:**

1. **Get an API key:** [Runpod console → Settings → API Keys](https://runpod.io/console/user/settings).
2. **Make it available to the CLIs** (`runpodctl`, `flash`) — either way works:
   ```bash
   export RUNPOD_API_KEY=<key>   # this shell only; add to ~/.zshrc / ~/.bashrc to persist
   runpodctl doctor              # OR: prompts once and saves to ~/.runpod/config.toml (persistent)
   ```
3. **Authenticate the MCP server** — pick one:
   - **OAuth (easiest, no key on disk):** in Claude Code, `/mcp` → **runpod** → *Sign in with Runpod*.
   - **Reuse the key you just set:**
     ```bash
     claude mcp add --transport http runpod -s user https://mcp.getrunpod.io/ \
       --header "Authorization: Bearer $RUNPOD_API_KEY"
     ```

Codex and local-stdio MCP variants are in [`runpod-mcp`](plugins/runpod/skills/runpod-mcp/SKILL.md).
Companion CLIs (`hf`, `docker`, `gh`, `aws`) use their own credentials — see
[`companion-clis`](plugins/runpod/skills/companion-clis/SKILL.md). If nothing is set up, the
`runpod` skill detects it and walks you through this.

## Updating

The plugin is **versioned**: updates arrive when we cut a release (a version bump, see
the CHANGELOG). Claude Code pulls the new version in the background; if it hasn't picked
it up yet, force it manually:

| Client | Update command |
| --- | --- |
| **Claude Code** | `/plugin marketplace update runpod` then `/reload-plugins` |
| **Codex** | `codex plugin marketplace upgrade runpod` |
| **skills.sh** | re-run `npx skills add runpod/runpod-plugins-official` |

## Uninstall

Remove the plugin (and, where applicable, the marketplace it came from):

| Client | Uninstall |
| --- | --- |
| **Claude Code** | `/plugin uninstall runpod@runpod`, then `/plugin marketplace remove runpod` |
| **Codex** | `codex plugin marketplace remove runpod` |
| **skills.sh** | `npx skills remove runpod` |

If a command reports a name mismatch, list what's installed first —
`/plugin marketplace list` (Claude Code) · `codex plugin marketplace list` (Codex) ·
`npx skills list` (skills.sh) — and use the name shown. Removing the marketplace also drops
the bundled hosted-MCP registration it added; if you configured the MCP separately, remove
that too (Claude Code: `claude mcp remove runpod`).

## What's inside

Start with the **`runpod`** router; it points at the right lane.

| Skill | Use it for |
| --- | --- |
| [`runpod`](plugins/runpod/skills/runpod/SKILL.md) | Router / entrypoint. Start here when the right skill is unclear. |
| [`runpod-mcp`](plugins/runpod/skills/runpod-mcp/SKILL.md) | Manage infra via the Runpod **MCP server**'s structured tool calls. |
| [`runpodctl`](plugins/runpod/skills/runpodctl/SKILL.md) | Manage infra from the **CLI**, plus Hub, file transfer, SSH, `doctor`. |
| [`flash`](plugins/runpod/skills/flash/SKILL.md) | **Write and deploy your own code** on Runpod serverless (`@remote`). |
| [`companion-clis`](plugins/runpod/skills/companion-clis/SKILL.md) | Prerequisite CLIs: `hf`, `docker`, `gh`, `aws`. |
| [`runpod-usage`](plugins/runpod/skills/runpod-usage/SKILL.md) | **Concepts** — pods/serverless, containers, storage, GPU selection, gotchas. |
| [`runpod-templates`](plugins/runpod/skills/runpod-templates/SKILL.md) | **Official pod templates** — what each image ships, ports/paths, readiness, gotchas. |
| [`runpod-migrate`](plugins/runpod/skills/runpod-migrate/SKILL.md) | **Migrate code** from the GraphQL API or REST v1 to REST v2. |

See the plugin's [README](plugins/runpod/README.md) for the full guide, the
development loop, and setup. Worked end-to-end examples live in
[`plugins/runpod/skills/runpod/golden-paths/`](plugins/runpod/skills/runpod/golden-paths/).

## Ask for it by name

Plain English works for one-off actions. For anything you're **designing**, add one
clause — *"and look at the examples first"*:

- *"Use the Runpod plugin skills and look at the examples. I want to build a speech
  translator: audio in, translated text out. Plan it out."*
- *"Use the runpod-migrate skill to move this repo from GraphQL to REST v2. Show me
  the inventory before you change anything."*
- *"Use the Runpod skills to repair the missing model links in this ComfyUI workflow, then download the approved files to my Pod."*
- *"Use the Runpod skills and check the examples — deploy this handler to serverless."*
- *"Use the Runpod skills — cheapest GPU that fits a 13B model?"*
- *"Use the Runpod skills and check the examples — my endpoint returns `IN_QUEUE` forever."*

You don't need to know which example applies; the agent picks. Worth adding either
way: *"show me the plan before you change anything"* and *"verify it with a real
request"* ("Running" is not "ready").

**Why the extra clause helps.** Skills auto-load from their description, but the
[golden paths](plugins/runpod/skills/runpod/golden-paths/) deliberately have **no
`SKILL.md`**, so agents never load them on their own — and each skill's
`reference/*.md` opens only on demand. Asking is what pulls them in, and they're
where the commands that were actually run against a real account live.

## Repository layout

```
.claude-plugin/marketplace.json   Claude Code / skills.sh marketplace manifest
.agents/plugins/marketplace.json  Codex marketplace manifest
plugins/runpod/                   the plugin (skills/ incl. runpod/golden-paths/, .mcp.json, manifests)
hooks/                            marketplace, branding & link validation
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0
