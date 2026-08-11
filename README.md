# Runpod Official Plugins

The **official** plugin marketplace of skills for AI agents to manage GPU workloads on Runpod —
pods, serverless endpoints, jobs, templates, and volumes — via the Runpod MCP
server, `runpodctl`, and `flash`.

This repo ships **one plugin**, [`runpod`](plugins/runpod/), that bundles a router
plus seven skills, the hosted Runpod MCP server config, and worked golden paths.

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
router + seven skills, plus a hosted **Runpod MCP server** for control-plane tools.
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
| [`runpod-migrate`](plugins/runpod/skills/runpod-migrate/SKILL.md) | **Migrate code** from the GraphQL API or REST v1 to REST v2. |

See the plugin's [README](plugins/runpod/README.md) for the full guide, the
development loop, and setup. Worked end-to-end examples live in
[`plugins/runpod/skills/runpod/golden-paths/`](plugins/runpod/skills/runpod/golden-paths/).

## Ask for it by name

Plain English works — the router picks the lane. But for anything bigger than a
one-liner, **name the skill _and_ point at the worked examples**. That single
extra clause is usually the difference between a plausible plan and one built on
commands that were actually run against a real account.

Why it matters: skills auto-load from their description, but the
[golden paths](plugins/runpod/skills/runpod/golden-paths/) deliberately have **no
`SKILL.md`** — agents never load them on their own. The per-skill `reference/*.md`
files are progressive-disclosure too: opened only when the agent has a reason.
Naming them *is* the reason.

| You want to… | Say something like | What it makes the agent read |
| --- | --- | --- |
| **Plan a new service** (say, a speech translator) | *"Use the runpod plugin skill and read the golden paths before planning. I want to build a speech translator: audio in, translated text out. Which path is closest, and what would you change?"* | [golden paths index](plugins/runpod/skills/runpod/golden-paths/README.md) → [03 whisper endpoint](plugins/runpod/skills/runpod/golden-paths/03-whisper-endpoint/README.md), [05 model → endpoint](plugins/runpod/skills/runpod/golden-paths/05-model-to-endpoint-pipeline.md), [12 streaming](plugins/runpod/skills/runpod/golden-paths/12-serverless-streaming.md) |
| **Migrate off GraphQL / REST v1** | *"Use the runpod-migrate skill. Inventory this repo first and show me the table before changing anything, then check the reference mappings as you go."* | [`runpod-migrate`](plugins/runpod/skills/runpod-migrate/SKILL.md) → [breaking-changes](plugins/runpod/skills/runpod-migrate/reference/breaking-changes.md), [rest-v1-to-v2](plugins/runpod/skills/runpod-migrate/reference/rest-v1-to-v2.md), [graphql-to-v2](plugins/runpod/skills/runpod-migrate/reference/graphql-to-v2.md) |
| **Deploy code you already have** | *"Use the flash skill and follow the custom serverless dev loop golden path to deploy this handler."* | [`flash`](plugins/runpod/skills/flash/SKILL.md) → [09 dev loop](plugins/runpod/skills/runpod/golden-paths/09-custom-serverless-dev-loop/README.md), [patterns](plugins/runpod/skills/flash/reference/patterns.md) |
| **Choose a GPU / control spend** | *"Use runpod-usage and check the GPU selection reference — cheapest GPU that fits a 13B model at reasonable latency?"* | [gpu-selection](plugins/runpod/skills/runpod-usage/reference/gpu-selection.md), [storage](plugins/runpod/skills/runpod-usage/reference/storage.md) |
| **Debug something already running** | *"Use the runpod skills and follow the monitor-and-debug golden path — my endpoint returns IN_QUEUE forever."* | [15 monitor & debug](plugins/runpod/skills/runpod/golden-paths/15-monitor-and-debug.md), [gotchas](plugins/runpod/skills/runpod-usage/reference/gotchas.md) |
| **Cut cold starts / tune scaling** | *"Use the runpod skills and read the model-caching and autoscaling golden paths before you change my endpoint config."* | [20 model caching](plugins/runpod/skills/runpod/golden-paths/20-model-caching-endpoint.md), [13 autoscaling](plugins/runpod/skills/runpod/golden-paths/13-autoscaling-tuning.md), [25 bake vs mount](plugins/runpod/skills/runpod/golden-paths/25-bake-vs-mount/README.md) |

### The pattern

Any of the above is the same three parts — reuse it for whatever you're building:

> **[name the skill]** + **[tell it to read the examples first]** + **[your actual task]**

Two phrases worth keeping in the habit:

- *"…show me the plan before you change anything"* — makes the agent surface its
  inventory or design while it's still cheap to redirect.
- *"…and verify it with a real request"* — "Running" is not "ready", and the
  [development loop](plugins/runpod/skills/runpod-usage/reference/development-loop.md)
  treats that check as part of the job rather than an afterthought.

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
