# Runpod

One entrypoint for AI agents to manage GPU workloads on Runpod — pods, serverless
endpoints, jobs, templates, and volumes — via the Runpod MCP server, `runpodctl`,
and `flash`, with conceptual guidance and worked golden paths.

This plugin bundles seven skills, the hosted Runpod MCP server config
([`.mcp.json`](.mcp.json)), and reference material.

## Which skill?

Start with **`runpod`** — the router. It reads your task and points to the right
lane below. If you already know the lane, go straight to it.

| Skill | Use it for |
| --- | --- |
| [`runpod`](skills/runpod/SKILL.md) | Router / entrypoint. Start here when the right skill is unclear. |
| [`runpod-mcp`](skills/runpod-mcp/SKILL.md) | Manage infra (pods, endpoints, jobs, templates, volumes, catalog, billing) via the Runpod **MCP server**'s structured tool calls. |
| [`runpodctl`](skills/runpodctl/SKILL.md) | Manage infra from the **CLI**, plus Hub deploys, file transfer (`send`/`receive`), SSH, and `doctor` setup. |
| [`flash`](skills/flash/SKILL.md) | **Write and deploy your own code** on Runpod serverless — `@remote`/`@Endpoint`, `flash dev`, `flash deploy`. |
| [`companion-clis`](skills/companion-clis/SKILL.md) | Prerequisite CLIs: `hf` (models), `docker` (images), `gh` (repos/releases), `aws` (S3 to volumes). |
| [`runpod-usage`](skills/runpod-usage/SKILL.md) | **Concepts** — how pods/serverless work, building containers, storage, GPU selection, gotchas. |
| [`runpod-migrate`](skills/runpod-migrate/SKILL.md) | **Migrate code** from the GraphQL API or REST v1 to REST v2 — inventory, rewrite, flag breaking changes. |

The migration flow also has a slash command: **`/runpod:migrate [scope] [path]`**
runs the `runpod-migrate` workflow directly, e.g. `/runpod:migrate rest src/`.

**runpod-mcp vs runpodctl:** both drive the same Runpod API for the same infra
CRUD. Prefer `runpod-mcp` when its tools are connected in your session; use
`runpodctl` for the terminal, Hub, file transfer, SSH, or `doctor`.

## The development loop

Any "get X running on Runpod" task follows one loop (in `runpod-usage`): **decide
pod vs serverless → prefer a prebuilt template/Hub worker over from-scratch →
provision → verify with a real request ("Running" ≠ "ready") → deliver → cost-guard
+ teardown.** See [`skills/runpod-usage/reference/development-loop.md`](skills/runpod-usage/reference/development-loop.md).

The [`skills/runpod/golden-paths/`](skills/runpod/golden-paths/) folder holds
worked, end-to-end reference tasks (Ollama, ComfyUI, Whisper, …) — acceptance
scenarios, not installed skills (they have no `SKILL.md`, so agents don't load
them). They live under the `runpod` router skill that indexes them, so they
travel with it on a single-skill install.

## Setup

Everything unifies on a single **`RUNPOD_API_KEY`**
(https://runpod.io/console/user/settings):

```bash
runpodctl doctor          # CLI: store the key + SSH
```

The hosted MCP server (bundled in [`.mcp.json`](.mcp.json)) is the exception — it
uses the "Sign in with Runpod" OAuth flow, so no key is stored on disk (see
[`runpod-mcp`](skills/runpod-mcp/SKILL.md)). Companion CLIs (`hf`, `gh`, `docker`,
`aws`) use their own credentials.

## Usage

For one-off actions, just ask — the router picks the lane:

- "Create a pod with an RTX 4090"
- "Deploy a serverless endpoint from this image"
- "Which GPU should I use for a 13B model?"
- "Write an `@remote` function and run it on a GPU"
- "Download a model, containerize it, and deploy it"

For anything you're **designing** rather than executing, add *"and look at the
examples first"*:

- "Use the Runpod plugin skills and look at the examples. I want to build a speech
  translator: audio in, translated text out. Plan it out."
- "Use the runpod-migrate skill to move this repo to REST v2. Show me the inventory
  before you change anything."
- "Use the Runpod skills and check the examples — deploy this handler to serverless."

The golden paths carry no `SKILL.md`, so they are never auto-loaded, and
`reference/*.md` opens only on demand — asking is what pulls them in. Worth adding
either way: *"verify it with a real request"*, per
[`skills/runpod-usage/reference/development-loop.md`](skills/runpod-usage/reference/development-loop.md).

## URLs

- **Pod:** `https://<pod-id>-<port>.proxy.runpod.net` (e.g. `https://abc123xyz-8888.proxy.runpod.net`)
- **Serverless:** `https://api.runpod.ai/v2/<endpoint-id>/{run|runsync|health|status/<job-id>}`

More in [`skills/runpod-usage/reference/networking.md`](skills/runpod-usage/reference/networking.md).

## Structure

```
skills/
  runpod/            router / entrypoint
    golden-paths/    worked end-to-end reference tasks (indexed by the router)
  runpod-mcp/        Runpod MCP server (structured tool calls)
  runpodctl/         Runpod CLI (+ Hub, transfer, SSH, doctor)
  flash/             write & deploy your own code (@remote)
  companion-clis/    hf / gh / docker / aws prerequisites
  runpod-usage/      concepts + reference/*.md
  runpod-migrate/    GraphQL / REST v1 -> REST v2 migration + inventory scanner
.mcp.json            hosted Runpod MCP server config
```

## License

Apache-2.0
