# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Overview

This is a **plugin marketplace** for AI agents (Claude Code, Codex, Gemini,
opencode, Cursor, Copilot, etc.) to work with Runpod. It contains no application
code — only a plugin whose skills (`SKILL.md`) plus supporting reference docs teach
agents how to manage GPU workloads across several backends and how Runpod works
conceptually.

Two install paths read the **same** `.claude-plugin/marketplace.json`:
- **Plugin:** `/plugin marketplace add runpod/runpod-plugins-official` then `/plugin install runpod@runpod`
  (native, auto-updating; in Claude Code also wires the hosted MCP via
  `plugins/runpod/.mcp.json` — Codex/Gemini may need it added separately).
- **skills.sh:** `npx skills add runpod/runpod-plugins-official` (skills.sh reads the marketplace
  manifest and installs the declared skill paths).

## Repository layout

```
.claude-plugin/marketplace.json   Claude Code / skills.sh manifest (plugin + skills paths)
.agents/plugins/marketplace.json  Codex manifest
plugins/runpod/                   THE plugin
  .claude-plugin/plugin.json      Claude Code plugin manifest
  .codex-plugin/plugin.json       Codex plugin manifest
  gemini-extension.json           Gemini manifest
  .mcp.json                       hosted Runpod MCP server config
  README.md  CHANGELOG.md
  skills/                         the nine skills (below)
  golden-paths/                   worked end-to-end reference tasks (no SKILL.md)
hooks/                            validate_marketplace / check_versions / check_runpod_branding / check_links / check_cli_absence_claims / check_migrate_scanner / check_migrate_tables / check_migrate_class3
                                  gen_cli_surface.py regenerates the runpodctl snapshot
testdata/runpod-migrate/          fixture repos the scanner regression check runs against
testdata/runpod-migrate/v2-openapi.json   vendored v2 spec snapshot the two spec checks gate against
testdata/runpodctl/command-surface.json   vendored runpodctl command surface the absence check gates against
.github/workflows/validate.yml    runs the hooks + the ComfyUI workflow helper unittests on PRs
.github/workflows/spec-drift.yml  weekly, non-blocking: the same spec checks against the live API + the latest runpodctl release
```

## Architecture: a router + lanes

The plugin's skills are organized as one **entrypoint** that routes to specialized
**lanes**. `skills/runpod/` is the router: an agent reads it first when the right
lane is unclear, then follows its decision table into a lane's `SKILL.md`.

```
skills/runpod/            router / entrypoint — decides the lane
skills/runpod-mcp/        manage infra via the Runpod MCP server (structured tool calls)
skills/runpodctl/         manage infra via the CLI (+ Hub, file transfer, SSH, doctor)
skills/flash/             write & deploy your own code on Runpod serverless (@remote)
skills/companion-clis/    prerequisite CLIs (hf, gh, docker, aws)
skills/runpod-usage/      conceptual knowledge ("how Runpod works") — not a tool
  reference/*.md          detailed topics, loaded on demand
skills/runpod-templates/  official prebuilt pod templates — what ships, ports, paths, gotchas
  reference/*.md          one file per template, fixed question shape
skills/runpod-migrate/    migrate a codebase from GraphQL / REST v1 to REST v2
  scripts/                the API-version inventory scanner
skills/runpod-comfyui-models/  recover verified model metadata for imported ComfyUI workflows
  scripts/                workflow inventory and reviewed metadata application
```

**runpod-mcp and runpodctl overlap** — both drive the same Runpod REST API for the
same infra CRUD. Which one wins is decided by the **capability-first, environment-second**
precedence rule, canonical in `skills/runpod/SKILL.md`'s capability matrix (roughly: runpod-mcp
for simple structured CRUD when connected, runpodctl the moment an op needs a capability MCP
lacks — Hub, `send`/`receive`, SSH, `doctor`, models, pod-from-template / CPU / multi-GPU — or
whenever the agent is shell-only). Consult the matrix there; don't rely on this summary.

## Skill file format

`SKILL.md` files use YAML frontmatter:
- `name`, `description` — skill identity. The `description` is the **routing surface**
  (always in the agent's context).
- `allowed-tools` — tool permissions (e.g., `Bash(runpodctl:*)`).
- `user-invocable` — set for skills a user invokes directly.
- `compatibility`, `metadata` (author, version), `license`.

The body is markdown the agent consumes, following **progressive disclosure** (see Contributor
rule 11): the `SKILL.md` body stays small and long tables / deep explanations live in
`reference/*.md` that the body links to and the agent opens only when needed.

## Golden paths & evals

- `golden-paths/` holds worked end-to-end reference tasks + a gap analysis each.
  They have **no `SKILL.md`**, so skills.sh never loads them as skills — they are
  acceptance scenarios/documentation. Each path's live-verification status is
  authoritative in `golden-paths/README.md`'s Status column (and restated in each
  file) — read it there.
- Each golden-path doc uses one section template: Goal · Status · Lane(s) → When to
  use → Prerequisites → Walkthrough → Verify → Gotchas → Cost & cleanup → skill gaps.
- Each skill's `evals/*.eval.md` are regression scenarios (Prompt / Expected
  behavior / Assertions). **They are not executed** — no runner exists in this repo and CI
  does not read them. They are specifications to hand-check a model against and to review
  when behavior changes; treat "an eval covers it" as documentation, not coverage.

## Contributor rules

Facts and context live in the sections above; these are the binding must-dos when
editing the repo. Each is its own checkable rule.

1. **Adding a skill** — list its path in the `skills` array of
   `.claude-plugin/marketplace.json` (that array is what skills.sh resolves).
2. **Skill `description`** —
   - Keep each `description` to 1–2 sentences.
   - If a skill overlaps another, its `description` names the sibling and states when to defer to it.
3. **`allowed-tools`** — omit this field for knowledge-only skills.
4. **Capability matrix** — the runpod-mcp vs runpodctl precedence rule is canonical
   in `skills/runpod/SKILL.md`.
   - When it changes, update `skills/runpod/SKILL.md`, `skills/runpod-mcp/SKILL.md`, and
     `skills/runpodctl/SKILL.md` in the same change.
   - State the rule only in `skills/runpod/SKILL.md`; do not restate it elsewhere.
5. **Golden paths** — they are **step 0 of routing, not an appendix**.
   `skills/runpod/SKILL.md` tells an agent to match the task against the golden-paths
   index *before* picking a lane whenever the task spans more than one resource or lane,
   provisions something billable, is shaped like "get X running", or warrants a multi-step
   plan. Keep that true, and keep the file conventions:
   - When you add or rename a path, add its row to **both** the router's "Want to…" table
     in `skills/runpod/SKILL.md` and the `golden-paths/README.md` table.
   - Every lane's `SKILL.md` links back to `golden-paths/README.md`. A new lane needs one.
   - Do not widen the trigger to "always read an example first" — a single read or single
     CRUD call should route straight to the lane. `consult-golden-path-first.eval.md`
     documents both directions and is the scenario to re-read before changing the trigger.
     Note that **nothing executes `evals/*.eval.md`** — there is no runner in this repo, so
     they are review scenarios and hand-check fixtures, not a gate. Do not describe them as
     enforcing anything.
   - Single approach → one file `NN-name.md`. Multiple variants → a folder
     `NN-name/` with a `README.md` (goal, "which variant?", shared schema/gotchas/cost)
     plus one `variant-*.md` per approach.
   - Every golden-path doc follows the section template listed under *Golden paths & evals*.
   - The per-path verification status is authoritative in `golden-paths/README.md`'s Status
     column; do not restate it in AGENTS.md (it drifts).
6. **Evals** — add or update an `evals/*.eval.md` when you add or change routing/behavior.
7. **The runpod-migrate scanner** — `rp_api_inventory.py` has a signal table of
   interacting regexes where a one-line edit breaks a
   distant case. When you change it, run `python3 hooks/check_migrate_scanner.py`, and
   add a corpus under `testdata/runpod-migrate/` plus an assertion for any new behavior.
   Every existing assertion corresponds to a defect that actually shipped — do not
   delete one to make the build green.
8. **runpod-migrate's factual claims about v2** — the reference tables assert concrete
   paths, and the Class-3 table asserts that capabilities are *absent*. Both are checked
   against `testdata/runpod-migrate/v2-openapi.json` by `check_migrate_tables.py` and
   `check_migrate_class3.py`. When a check fails, fix the doc; refresh the snapshot only
   when v2 genuinely changed, and re-read the affected rows when you do. A wrong Class-3
   row is worse than a wrong rename: SKILL.md tells the agent to stop and ask the user
   about those, so it buys an interruption over a decision that does not exist.
9. **Never claim a tool cannot do something without checking.** "runpodctl has no X
   command", "only MCP can Y", "there's no first-class Z" — these are assertions of
   **absence**, and they are the claims that rot silently. The `--help`-is-authoritative
   rule does not protect them: there is no flag to look up, so nobody reverifies, and the
   sentence reads as authoritative until the release that adds the command.
   - `hooks/check_cli_absence_claims.py` gates every such claim against
     `testdata/runpodctl/command-surface.json`. When runpodctl releases, run
     `python3 hooks/gen_cli_surface.py`, then fix whatever the check reports.
   - Prefer a positive claim ("read them with `serverless logs`") or silence. If an absence
     claim is genuinely load-bearing, give it a **version floor** ("needs ≥ v2.10.0") rather
     than an open-ended "cannot", and add it to the check's `ALLOW` list with a reason.
   - **An eval asserting a false negative is the worst case** — it trains the wrong behavior
     in rather than merely misinforming a reader. This has already happened twice: v2.9.0
     added `serverless health` and v2.10.0 added `serverless logs`/`pod logs`, each
     falsifying claims the skills stated as fact.
10. **Releases** —
   - Never hand-bump versions; release-please cuts the release (see `CONTRIBUTING.md` →
     Cutting a release).
   - Use Conventional Commits.
11. **Skill body size** — put only a decision table plus the 80% patterns in a `SKILL.md` body;
   move long tables and deep explanations into `reference/*.md` linked from the body.

## Conventions

Rules:
- **Spelling:** write "Runpod" (capital R); the CLI command is `runpodctl` (lowercase).

Reference facts (not rules):
- **Auth:** everything unifies on `RUNPOD_API_KEY`; the hosted MCP is the exception
  (OAuth "Sign in with Runpod"). Companion CLIs use their own creds.
- **License:** Apache-2.0.
