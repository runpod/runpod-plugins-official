---
name: runpod-migrate
description: >-
  Migrate a codebase from the Runpod GraphQL API or REST v1 to REST v2 — inventory
  which parts use which API version, rewrite the call sites, flag breaking changes,
  and verify. Use when someone asks to move to v2, asks what v2 would change, or
  asks which Runpod API their code is on. For managing infrastructure rather than
  migrating code, use runpod-mcp or runpodctl.
user-invocable: true
allowed-tools: Bash(python3:*), Bash(curl:*), Bash(rg:*), Bash(git:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.1.2" # x-release-please-version
license: Apache-2.0
---

# Migrate to Runpod REST v2

Moves a codebase off the **GraphQL API** (`api.runpod.io/graphql`) and **REST v1**
(`rest.runpod.io/v1`) onto **REST v2** (`api.runpod.io/v2`).

**Why the user should want this** — lead with these, they are the payoff, not trivia:

- **You can see stock before you rent.** `GET /v2/catalog/gpus?include=AVAILABILITY`
  returns a per-datacenter availability level for every GPU. v1 had no catalog at all;
  GraphQL had `lowestPrice.stockStatus` one GPU at a time. Capacity retry loops stop
  being blind.
- **Endpoints hand you their own job URLs.** `endpoint.requestUrls.run` — no more
  string-concatenating `api.runpod.ai/v2/<id>/run`.
- **Real pod lifecycle states.** `PROVISIONING → STARTING → RUNNING → EXITED/ERROR`,
  plus an `actions` list of the transitions that are legal right now. v1's
  `desiredStatus` had three values and could not express "still coming up" or "failed",
  so wait-loops had to time out instead of failing fast.
- **Live worker/rollout visibility.** Per-worker status, an `isStale` flag during a
  rolling update, a `summary` histogram, and endpoint release history with a diff.
- **Streaming logs over SSE** for pods and workers, instead of polling.
- **The catalog is not frozen in the spec.** v1 hardcoded GPU and datacenter IDs as
  enums, so new hardware needed a spec release. v2 takes open strings and you discover
  values from `/v2/catalog`.
- **Mistakes fail loudly, and correctly.** Every v2 request body rejects unknown fields
  (via `additionalProperties: false`, or `unevaluatedProperties: false` on the composed
  Create/Update schemas), so a half-finished migration 422s with the offending fields
  listed by name instead of silently ignoring them. Errors are structured
  (`{title, status, detail, errors[]}`) with honest status codes — a bad image tag that
  v1 answered with `500 {"error": "..."}` is a `422` in v2, so retry logic stops
  retrying user errors.

Full list, mapped to what the user's code already does: **[reference/unlocks.md](reference/unlocks.md)**.

## Before you touch any code

**Ask for scope if it is not already clear** — it changes the plan materially:

| The user says | Scope |
| --- | --- |
| "migrate to v2" / nothing specific | `all` — REST v1 **and** GraphQL |
| "just the REST stuff", "leave GraphQL alone" | `rest` — REST v1 only |
| "get us off GraphQL" | `graphql` — GraphQL only |

Some things **have no v2 equivalent and must stay on GraphQL regardless of scope**:
account/billing identity (`myself`), secrets, spot/interruptible pods, cluster
create/delete. A "full" migration still leaves those calls in place — say so up front
rather than letting the user discover it at the end.

**Never rewrite the serverless job API.** `https://api.runpod.ai/v2/<endpointId>/run`,
`/runsync`, `/status`, `/stream`, `/cancel` is a *different API* that happens to have
`v2` in its path. It is unchanged and out of scope. The inventory reports it separately
so you do not touch it.

## The workflow

### 1. Inventory — never migrate what you have not counted

The scanner ships **beside this file**, in the installed skill directory — not in the
user's repo. Resolve its path first; your working directory is their project:

```bash
# 1. Claude Code plugin installs expose the plugin root:
SCAN="$CLAUDE_PLUGIN_ROOT/skills/runpod-migrate/scripts/rp_api_inventory.py"
# 2. Otherwise substitute the directory you loaded this SKILL.md from — you know it:
[ -f "$SCAN" ] || SCAN="<directory containing this SKILL.md>/scripts/rp_api_inventory.py"
# 3. Last resort, search the usual install roots:
[ -f "$SCAN" ] || SCAN=$(find ~/.claude ~/.agents ~/.codex ~/.config -name rp_api_inventory.py 2>/dev/null | head -1)
python3 "$SCAN" --help >/dev/null || echo "scanner not found — resolve it before continuing"
```

Then, from the root of the user's repo:

```bash
python3 "$SCAN" . > runpod-api-inventory.md
python3 "$SCAN" . --json > runpod-api-inventory.json   # if you want to drive edits from it
python3 "$SCAN" . --scope rest                          # REST-only migrations
```

`runpod-api-inventory.md` lands in the user's repo — mention it, and remove it or
gitignore it before you hand the migration back.

Stdlib-only Python, no install. It reports every call site bucketed by generation —
GraphQL, REST v1, v1/GraphQL **field names**, REST v2 **already**, serverless job API,
SDK/CLI wrappers — plus a suggested file-by-file order.

**Show the user the inventory table before editing anything.** Users routinely do not
know what they are on: an agent picked a version for them months ago and wrote it down
nowhere. "3 files on v1, 2 on GraphQL, 1 already on v2, 2 on the job API — leave those
alone" is often the single most useful output of this whole skill.

#### What it detects, and what it cannot

It is regex line-scanning, but the classification is what makes it usable — plain
`grep -r runpod` gets two things actively wrong:

- **`api.runpod.ai/v2` vs `api.runpod.io/v2`.** One letter apart. `.ai` is the serverless
  job API and must not be touched; `.io` is the control plane you are migrating to.
  Grepping for `v2` tells you the codebase is "already migrated" when it is not.
- **Names legal in both versions.** `/pods` is a v1 path *and* a v2 path; `["pods"]` is
  v2 envelope-unwrapping; `idleTimeout` is top-level in v1 and nested under `workers` in
  v2. The scanner suppresses a hit when the same line carries v2 context, so it reports
  work that remains rather than every occurrence of a word.

It also looks for **field names, not just URLs**, which is what catches the files that
never spell "runpod": a module reading `p["costPerHr"]` off a wrapper's return value has
no URL, no import, no operation name — and is exactly what a v2 rename breaks silently.

Four things it genuinely cannot resolve. Check them by hand, every time:

| Blind spot | How to close it |
| --- | --- |
| **Base URL lives in config**, not code (`settings.yaml`, `.env`, a ConfigMap, Terraform) | The scanner does read those files, so the URL surfaces — but the *call sites* using it are elsewhere. Grep for whoever reads that config key. |
| **Paths assembled by a helper** — `_url("pods", pod_id, "stop")` | Reported under *possible indirect call sites*. Advisory, because `resp.json()["pods"]` looks identical. Open each one. |
| **SDK wrappers** (`import runpod`) | The API generation is a property of the installed *version*, not the code. Check `requirements.txt` / lockfile and the SDK's own release notes. |
| **Generated clients** | The OpenAPI/GraphQL document is the real source. Regenerate from the v2 spec instead of editing generated files. |

Then read the code the scanner flagged. It finds call sites; it does not understand your
wrappers. Trace who calls them — a renamed response field like `costPerHr → cost` breaks
every caller, not just the request builder. This is the one step where a code-graph or
LSP index earns its keep, if one is already available.

### 2. Brief the breaking changes — before the diff, not after

Read **[reference/breaking-changes.md](reference/breaking-changes.md)** and tell the
user which ones actually apply to *their* code. Two classes, and the second is the one
they are afraid of:

1. **Renames and moves** — loud. v2 rejects unknown request fields with `422` listing
   them by name, so a missed rename cannot slip into production silently.
2. **Same name, different meaning** — quiet, and the reason a green test suite is not
   proof. The reference enumerates every one of them; the two that bite hardest:
   `flashboot` went from boolean to a three-value enum, and v1's `/billing/endpoints`
   (serverless spend) is v2's `/billing/serverless` — v2's `/billing/endpoints` is a
   *different product* and will happily return `200` with the wrong numbers.

### 3. Plan, split into required vs cleanup

Write the plan down before editing, and keep the two buckets separate all the way
through to the final summary:

- **Required** — it does not work on v2 without this.
- **Cleanup** — it works either way, but v2 lets you delete code (hand-built job URLs,
  hand-rolled availability retry, polling loops that can now be SSE).

### 4. Migrate, one file per commit

Work in the scanner's suggested order (fewest call sites first). Per file:

- Map paths and fields with **[reference/rest-v1-to-v2.md](reference/rest-v1-to-v2.md)**
  or **[reference/graphql-to-v2.md](reference/graphql-to-v2.md)**.
- **Always request availability on catalog reads.** Any `GET /v2/catalog/gpus`,
  `/catalog/cpus`, or `/catalog/datacenters` this migration introduces gets
  `include=AVAILABILITY` (`GPU_AVAILABILITY`/`CPU_AVAILABILITY` for datacenters).
  Availability is the top-of-mind question for every Runpod user and the call costs the
  same. Do not omit it because the current code did not ask for it — v1 could not.
- Offer the **rollback flag** (`RUNPOD_API_V1=1`) while v2 is new to them:
  **[reference/rollback-flag.md](reference/rollback-flag.md)**. Worth it for a service
  in production; skip it for a one-off script.
- Never change behavior and API version in the same commit.

A full before/after of a real client — pod create with GPU fallback, endpoint create
without `templateId`, GraphQL dashboard — is in
**[reference/worked-example.md](reference/worked-example.md)**.

### 5. Verify against the live API

Static review is not enough; v2's validator is strict and its errors are precise.
Re-run the scanner to prove the call sites are gone, then exercise the real paths:

```bash
python3 "$SCAN" . --scope rest --fail-on-legacy   # exit 1 if v1 remains
```

Legacy code you kept **on purpose** — a `RUNPOD_API_V1` rollback branch, or a GraphQL
call with no v2 equivalent — gets a `# rp-migrate: keep-v1` marker (line, `start`/`end`
region, or `file`). It stays visible in the report under *kept on purpose* but drops out
of the plan, so `--fail-on-legacy` stays meaningful and can go in CI. Markers are also
how you find the rollback code again when it is time to delete it.

- **Reads** are free — list pods, endpoints, volumes, catalog. Confirm you unwrap the
  new envelope (`{"pods": [...]}`, not a bare array).
- **Writes** cost money. Create → assert → delete, on the smallest thing that proves the
  shape. Never test against resources the user already has.
- Decode `422`s with the table in
  [reference/breaking-changes.md](reference/breaking-changes.md#reading-a-422) — including
  the confusing one where a *missing required field* makes the validator report your
  *valid* fields as "additional properties not allowed".

### 6. Summarize — this is the artifact they will actually read

Most users read the summary and not the diff. Structure it exactly like this:

```
## Required for the migration
<file:line> — what changed and why it had to

## Cleanup enabled by v2
<file:line> — what got deleted or simplified

## Behavior changes to watch
the same-name-different-meaning items that applied

## Still on GraphQL (no v2 equivalent)
myself / secrets / spot pods / clusters — and why

## Unlocks: what you can build now
tied to what this codebase already does
```

That last section is the highest-value part. Do not paste a generic feature list —
look at what this user has been building and struggling with, including anything you
already know from the session, and name where v2 changes it. "Your `wait_until_running`
loop times out on failed pods; v2's `ERROR` status lets it fail in seconds" beats "v2 has
richer status values". [reference/unlocks.md](reference/unlocks.md) is organized as
*if the code does X → v2 offers Y* for exactly this.

## Tooling notes

The inventory scanner is deliberately a **grep-class script, not a code-graph index**:
API generation is a property of URL strings and field names, it must work on any
language in an arbitrary customer repo, and it has to give the same answer for every
user with zero setup. A code-intelligence index (LSP, or an MCP graph server if one is
already running) earns its keep at a different step — step 1's *blast radius* question,
"who calls this wrapper whose response field just got renamed" — not at detection.
Use one there if it is already available; do not stand one up just for this.
