---
concepts: [api-key, ssh-key, runpodctl, flash, pod-ssh-access]
---

# Getting started (auth & first-run setup)

Before any lane can act, its credential has to resolve. Everything Runpod-side
uses **one key**, `RUNPOD_API_KEY`; the companion CLIs use their own. Do the setup
for the lane you're about to use, then follow the development loop.

## Update before the first command

Old builds keep flags that later releases fixed or removed: runpodctl before v2.12.0
accepts `pod create --stop-after` / `--terminate-after`, but the backend never enforced
them, so pods kept billing past the deadline. Update each tool you are about to use, then
use the same build for the rest of the task:

```bash
runpodctl update && runpodctl version   # runpodctl
rp update                               # Runpod SDK + rp CLI (flash lane)
```

The MCP needs no step: the hosted server is always current, and a local install started
with `npx @runpod/mcp-server@latest` fetches the latest release.

## Which credential, when (agents)

**MCP OAuth first, a key only when a task needs one.** This matches the onboarding guide
at https://agents.runpod.io/. With a user present, the hosted MCP's "Sign in with Runpod"
(OAuth, no key on disk) is the default control plane: most infra tasks (pods, endpoints,
jobs, volumes, templates) need nothing else. Don't install CLIs or create a key during
setup "just in case".

- **OAuth authenticates the MCP alone.** When a task reaches a CLI-only step
  (`send`/`receive`, SSH, `doctor`, model cache/Model Repository, an `rp flash` deploy), get a
  key **at that point**, in order:
  1. **`rp login`**: browser approval, then the user pastes the key the console shows; it
     is saved to `~/.runpod/config.toml` (runpodctl + the Runpod SDK read it). Needs a human
     and an interactive terminal.
  2. **`export RUNPOD_API_KEY=…`** (https://console.runpod.io/user/settings): the same
     key, best for headless agents.
- **No user in the loop** (CI, scheduled jobs, agent SDK runs)? Nobody can approve OAuth,
  so use `RUNPOD_API_KEY` from the start and send it to the hosted MCP as
  `--header "Authorization: Bearer $RUNPOD_API_KEY"`.
- **File authoring** with runpod-build-template needs no cloud credentials. Check auth
  only when an operation actually uses the control plane or another authenticated service.
- **Infra tasks** (pods, endpoints, jobs, volumes) need a working control plane, the
  Runpod MCP or runpodctl. Don't start and discover mid-task that nothing's set up: check
  first (`runpodctl user` succeeds ⇒ a key is set and valid; in Claude Code, `/mcp` shows
  `runpod` **Connected**). If a lane already works, use it; if none does, help the user set up rather than limping on a
  partial fallback.

Connecting the MCP itself (hosted vs stdio, the `redirect_uri is not allowed` header
fallback, verifying the connection) is owned by
[`runpod-mcp`](../../runpod-mcp/SKILL.md#connect).

## Get the tools

Install only the lane you need; full per-OS matrices + source links live in each
lane's `SKILL.md` (linked). You don't need all of them.

| Lane | Quick install | Source / docs |
| --- | --- | --- |
| **runpodctl** (CLI) | `curl -fsSL https://cli.runpod.net \| sudo bash` (or `brew install runpod/runpodctl/runpodctl`) | [source](https://github.com/runpod/runpodctl) · [`runpodctl/SKILL.md`](../../runpodctl/SKILL.md) |
| **flash** (deploy your own code) | `pip install "runpod>=2.0.0"` (or `uv add`; Python 3.10–3.14; installs the `rp` CLI) | [source](https://github.com/runpod/runpod-python) · [`runpod-flash/SKILL.md`](../../runpod-flash/SKILL.md) |
| **runpod-mcp** (hosted) | `npx @runpod/mcp-server@latest add --client <id>` (OAuth; `--list` shows ids) | [source](https://github.com/runpod/runpod-mcp) · [`runpod-mcp/SKILL.md`](../../runpod-mcp/SKILL.md) |
| **runpod-mcp** (local stdio) | `claude mcp add runpod -e RUNPOD_API_KEY=... -- npx -y @runpod/mcp-server@latest` | same as above |
| **companion CLIs** (`hf`/`gh`/`docker`/`aws`) | per-tool; see the skill | [`runpod-companion-clis/SKILL.md`](../../runpod-companion-clis/SKILL.md) |

Nothing to install for the **hosted MCP** beyond configuring your client, and the
`runpod-usage` concepts need no install. After installing, set the key below.

**Want the Runpod tools in one go?** Copy-paste (drop any line you won't use):

```bash
npx skills add runpod/runpod-plugins-official # the skills — works with any agent
curl -fsSL https://cli.runpod.net | sudo bash       # runpodctl — infra CLI (or: brew install runpod/runpodctl/runpodctl)
pip install "runpod>=2.0.0"                   # Runpod SDK + rp CLI — deploy your own code (flash lane)
npx @runpod/mcp-server@latest add --client <id> # hosted MCP server, OAuth (--list shows ids)
```

Companion CLIs (`docker`, `gh`, `hf`, `aws`) are separate and OS-specific — install only the
ones a task needs, per [`runpod-companion-clis/SKILL.md`](../../runpod-companion-clis/SKILL.md).

## The Runpod API key

Get it once at **https://console.runpod.io/user/settings** → API Keys. Then make
it resolvable for the lane. Resolution order (runpodctl, flash, and runpod-python
all use it): **`RUNPOD_API_KEY` env var → `.env` → `~/.runpod/config.toml`** (in that
file the key is the `apikey` field, TOML `apikey = '...'`). If you need the raw key
yourself (e.g. an `Authorization: Bearer` header for a direct API call), prefer
`$RUNPOD_API_KEY` and fall back to that field:
`KEY="${RUNPOD_API_KEY:-$(grep '^apikey' ~/.runpod/config.toml | sed "s/apikey = '//;s/'//")}"`.

| Lane | Set the key | Notes |
| --- | --- | --- |
| **runpodctl** | `export RUNPOD_API_KEY=...` | Non-interactive — runpodctl reads it. Best for agents/CI/scripts. |
| runpodctl (human) | `runpodctl doctor` | Interactive; stores the key **and** sets up SSH keys. Prompts, so not for agents. |
| **flash** | `export RUNPOD_API_KEY=...` | Or `rp login` — browser approval, then the user pastes the key the console shows; it is **saved to `~/.runpod/config.toml`**, which runpodctl reads too, so one login serves both. Needs a human and an interactive terminal; `rp login --api-key` stores a key without one. |
| **runpod-mcp (hosted)** | "Sign in with Runpod" OAuth on first connect | No key on disk. Or pass `Authorization: Bearer $RUNPOD_API_KEY`. |
| **runpod-mcp (local)** | `RUNPOD_API_KEY` env in the MCP client config | Forwarded to the API. |

**Rule (agents):** in automation, set the key with `export RUNPOD_API_KEY=...` (runpodctl and
flash both honor it — the closest thing to one-step setup); never run `runpodctl doctor`, which
prompts.

Context: the **hosted MCP is the exception** — it uses its own `/mcp` "Sign in with Runpod" OAuth
(or pass the same key as an `Authorization: Bearer` header). Authing the MCP does not set up the
CLIs, and the export does not authenticate the hosted MCP's OAuth.

## SSH (only needed for pods you exec into)

Pods created with `--ssh` (the runpodctl default) are reachable once you have a key
registered. **Register the key BEFORE creating the pod** — Runpod injects registered
keys at boot, so one added after the pod is running won't work until a restart.

- Check what's registered: `runpodctl ssh list-keys`.
- Register a key (do this first if none):
  - Human: `runpodctl doctor` — generates + registers a key and stores the API key.
  - Agent/scripted: `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''` then
    `runpodctl ssh add-key --key-file ~/.ssh/id_ed25519.pub` (or `--key "ssh-ed25519 …"`).
- Get connection details for a specific pod: `runpodctl ssh info <pod-id>` (prints
  the ssh command + key path; does not connect).
- Agents connect non-interactively:
  `ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p <port> root@<host> 'cmd'`.

Serverless endpoints need no SSH.

## Companion CLI credentials (separate from RUNPOD_API_KEY)

Do NOT reuse the Runpod key for these — each has its own (see the `runpod-companion-clis`
skill for details):

- **`hf`** — HuggingFace token (`hf auth login`); read scope to pull, write to push.
- **`docker`** — Docker Hub PAT (`docker login`).
- **`gh`** — GitHub auth (`gh auth login`).
- **`aws`** — Runpod **S3** keys (user id `user_…` + S3 API key `rps_…`), with
  `--region <dc> --endpoint-url https://s3api-<dc>.runpod.io/`. NOT AWS creds, NOT
  the Runpod API key.

## Verify you're set up

```bash
export RUNPOD_API_KEY=...
runpodctl user            # prints your account (confirms the key works)
runpodctl gpu list        # confirms API access
```

Then pick your workload and follow `development-loop.md`.
