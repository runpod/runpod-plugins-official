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

**The payoff, in one line each** — you deliver these to the user at step 6, matched to
their actual code. Don't recite them now:

- **See stock before you rent** — `GET /v2/catalog/gpus?include=AVAILABILITY&product=POD`. v1 had no
  catalog at all, so every capacity retry loop was blind.
- **Endpoints return their own job URLs** — `requestUrls.run`, no more string-building.
- **Real lifecycle states** — `PROVISIONING`/`STARTING`/`ERROR` and an `actions` list, so
  wait-loops fail fast instead of timing out.
- **Mistakes fail loudly** — unknown request fields are rejected by name, with structured
  errors and honest status codes.

The full set, organized as *if their code does X → v2 offers Y*:
**[reference/unlocks.md](reference/unlocks.md)** — open it at step 6.

## Before you touch any code

**Infer the scope, state it, and move** — do not open with a questionnaire:

| The user says | Scope |
| --- | --- |
| "migrate to v2" / nothing specific | `all` — REST v1 **and** GraphQL |
| "just the REST stuff", "leave GraphQL alone" | `rest` — REST v1 only |
| "get us off GraphQL" | `graphql` — GraphQL only |

The table resolves every phrasing, so scope is not the thing to interrupt for. Say which
row you matched and carry on. **The question that does need asking comes later** — at
step 3, when the inventory shows the code depends on a capability v2 removed. That one
is a real fork and you cannot answer it for them.

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
   (serverless spend) is v2's `/billing/serverless` — v2's `/billing/endpoints` bills a
   *different product* (public endpoints) and answers `200` with a correct total for
   that product, which is not the one the caller asked for.

### 3. Plan, split into required vs cleanup

Write the plan down before editing, and keep these buckets separate all the way through
to the final summary:

- **Required** — it does not work on v2 without this.
- **Cleanup** — it works either way, but v2 lets you delete code (hand-built job URLs,
  hand-rolled availability retry, polling loops that can now be SSE).
- **Decisions the user must make** — the code depends on something v2 removed outright:
  spot/interruptible pods, savings plans, `dockerEntrypoint`, placement constraints
  (`countryCodes`, `minRAMPerGPU`, …), pod `reset`, per-pod GPU fallback. See
  [breaking-changes.md](reference/breaking-changes.md) Class 3 — and check it rather
  than working from memory, because things leave this bucket as v2 grows. CUDA pinning,
  `templateId` and CPU endpoint writes all used to be here and are not any more.

**Stop and ask before writing code in that third bucket** — but bring the replacement
with you. Some of these have a working rebuild and some genuinely have nothing, and the
difference decides what you are asking. Where a rebuild exists (`countryCodes` →
[catalog filter + `dataCenterIds` + a placement
assert](reference/breaking-changes.md#replacing-countrycodes-and-the-rest-of-the-placement-constraints),
per-pod GPU fallback → [an availability-ordered
loop](reference/breaking-changes.md#replacing-the-gpu-fallback-list-pods-only)), show it
and ask the one question that changes it — for `countryCodes`, whether the restriction
was a preference or a compliance requirement. Where nothing exists, the options are
accept the behavior change, keep that call on v1/GraphQL, or redesign around it, and only
the user can pick.

Either way, do not present a removal as a dead end when a rebuild exists — that pushes
the user into keeping a v1 call they did not need to keep. And never drop the field with
a `# no v2 equivalent` comment: that is the failure mode this bucket exists to prevent,
because it silently changes what their infrastructure does. If the bucket is empty, say
so — that is reassuring and takes one line.

### 4. Migrate, one file per commit

Work in the scanner's suggested order (fewest call sites first) — **with one override:
if several call sites share a transport helper, migrate the helper first**, whatever its
count. The scanner orders by call-site count and cannot see imports, so it will happily
put a consumer ahead of the module it imports its client from. Migrating a consumer
first means writing against an interface you are about to change.

Per file:

- Map paths and fields with **[reference/rest-v1-to-v2.md](reference/rest-v1-to-v2.md)**
  or **[reference/graphql-to-v2.md](reference/graphql-to-v2.md)**. If a field isn't in
  the tables, or the API disagrees with them, check the spec directly —
  [Ground truth](#ground-truth-check-the-spec-yourself).
- **`gpuTypeIds` + `gpuTypePriority` on a *pod* means you are writing new code, not
  renaming fields.** A v2 pod takes one GPU type, so the server-side fallback becomes a
  client-side loop over the catalog. Working implementation:
  [breaking-changes.md → Replacing the GPU fallback list](reference/breaking-changes.md#replacing-the-gpu-fallback-list-pods-only).
  **Endpoints need no loop** — `gpu.pools` is already a list and workers land on
  whichever listed pool has capacity.
- **Always request availability on catalog reads — with `product`.** Any
  `GET /v2/catalog/gpus`, `/catalog/cpus`, or `/catalog/datacenters` this migration
  introduces gets `include=AVAILABILITY` (`GPU_AVAILABILITY`/`CPU_AVAILABILITY` for
  datacenters). Availability is the top-of-mind question for every Runpod user and the
  call costs the same. Do not omit it because the current code did not ask for it — v1
  could not.

  **`include=AVAILABILITY` alone is a `400`.** On `/catalog/gpus` and `/catalog/cpus`,
  `product` is required with it and invalid without it — `400` either way. There is no
  default, deliberately: the same GPU can be scarce for `POD` and plentiful for
  `SERVERLESS`, so the context has to be stated. Pick the one matching what you are
  creating (`POD`, `SERVERLESS`, or `CLUSTER`; CPUs take `POD` or `SERVERLESS`):

  ```
  GET /v2/catalog/gpus?include=AVAILABILITY&product=POD
  ```
- Offer the **rollback flag** (`RUNPOD_API_V1=1`) while v2 is new to them:
  **[reference/rollback-flag.md](reference/rollback-flag.md)**. Worth it for a service
  in production; skip it for a one-off script.
- **Never change behavior and API version in the same commit** — including the
  improvements v2 makes possible. Failing fast on `status == "ERROR"` instead of timing
  out is a genuine win and it belongs in the *next* commit; folding it into the
  migration commit means a rollback has to give up both. Land those in the **cleanup**
  bucket, separately.

A full before/after of a real client — pod create with GPU fallback, endpoint create
with the container config inlined, GraphQL dashboard — is in
**[reference/worked-example.md](reference/worked-example.md)**.

### 5. Verify against the live API

Static review is not enough; v2's validator is strict and its errors are precise.
Re-run the scanner to prove the call sites are gone, then exercise the real paths:

```bash
python3 "$SCAN" . --scope rest --fail-on-legacy   # exit 1 if v1 remains
```

Two markers, and they mean different things — do not reach for the wrong one:

| Marker | Use it for |
| --- | --- |
| `rp-migrate: keep-v1` | legacy code kept **on purpose** — a `RUNPOD_API_V1` rollback branch, or a GraphQL call with no v2 equivalent. Reported under *kept on purpose*. |
| `rp-migrate: ignore` | a **false positive** on code that is already correct. Says "this isn't legacy", not "this is legacy I'm keeping". Reported under *marked false positives*. |

Both accept `line`, `start`/`end` region, or `file` scope, and both drop out of the plan
and out of `--fail-on-legacy`. Using `keep-v1` to silence a false positive records a lie
in the report — reach for `ignore` there.

**Where the gate can still be wrong.** The same blind spots from step 1 invert after a
migration: before, they hide v1 code; after, they can flag correct v2 code. The scanner
handles the two common cases — trailing `# was imageName` annotations, and a base URL
held in a constant (`f"{BASE}/pods"` where `BASE` is a v2 URL defined anywhere in the
file). Beyond those — a base URL imported from another module, or built at runtime from
config — it can still misread correct code as legacy. Read the flagged lines before
believing the exit code, and mark true false positives with `ignore` rather than
weakening the gate.

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

## Ground truth: check the spec yourself

The mapping tables in `reference/` were verified against the live API on **2026-08-10**.
v2 is actively developed, so treat them as a fast path, not as the authority. Both specs
are public and need no auth:

```bash
curl -s https://api.runpod.io/v2/openapi.json  -o /tmp/rp-v2.json
curl -s https://rest.runpod.io/v1/openapi.json -o /tmp/rp-v1.json
```

**What a request body actually accepts, and what is required** (`*`). Worth running
before writing any create call — it resolves `allOf` composition, which a naive read of
the raw JSON misses:

```bash
python3 - CreateEndpointRequest <<'PY'
import json, sys
S = json.load(open("/tmp/rp-v2.json"))["components"]["schemas"]
def merge(n, acc=None):
    acc = acc if acc is not None else {"props": {}, "req": set()}
    if "$ref" in n: return merge(S[n["$ref"].split("/")[-1]], acc)
    for sub in n.get("allOf", []): merge(sub, acc)
    acc["props"].update(n.get("properties", {})); acc["req"].update(n.get("required", []))
    return acc
def kind(v):
    if "$ref" in v: return v["$ref"].split("/")[-1]
    if "allOf" in v: return kind(v["allOf"][0])
    return v.get("type", "?")
m = merge(S[sys.argv[1]])
for k, v in sorted(m["props"].items()):
    print(f"  {'*' if k in m['req'] else ' '} {k:16} {kind(v)}")
PY
```

Swap the argument for `CreatePodRequest`, `UpdatePodRequest`, `CreateTemplateRequest`,
`CreateNetworkVolumeRequest`, … **Which schemas mention a field** — useful when a `422`
names something you cannot place:

```bash
python3 -c 'import json,sys; S=json.load(open("/tmp/rp-v2.json"))["components"]["schemas"]; [print(" ",n) for n,s in S.items() if sys.argv[1] in json.dumps(s)]' flashboot
```

### Precedence when sources disagree

**observed live behavior > the spec > these tables.** The spec is not always right, and
the reference docs say so where it is known to be wrong — `timeout` is documented to
default to `300000` ms but comes back `0`. If you hit a case where the running API
contradicts the spec, trust the API, and **say so in your summary** so the user knows a
documented default cannot be relied on.

If you find a mapping in `reference/` that no longer matches the spec, fix the call and
flag the drift — the tables carry a verification date precisely so staleness is
detectable rather than silent.

For GraphQL there is no machine-readable schema (introspection is disabled), so that
side cannot be checked this way — see the caveat in
[reference/graphql-to-v2.md](reference/graphql-to-v2.md).

## Tooling notes

The inventory scanner is deliberately a **grep-class script, not a code-graph index**:
API generation is a property of URL strings and field names, it must work on any
language in an arbitrary customer repo, and it has to give the same answer for every
user with zero setup. A code-intelligence index (LSP, or an MCP graph server if one is
already running) earns its keep at a different step — step 1's *blast radius* question,
"who calls this wrapper whose response field just got renamed" — not at detection.
Use one there if it is already available; do not stand one up just for this.
