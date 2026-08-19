---
name: runpodctl
description: >-
  Runpod CLI for managing GPU/CPU workloads from the terminal — pods, serverless
  endpoints, templates, network volumes, Hub deploys, models, SSH, and file
  transfer (send/receive). Use for terminal/CI/scripting, Hub browse/deploy, SSH
  setup, `doctor`, or when the Runpod MCP tools are not connected. For structured
  tool calls in an MCP-enabled session, prefer runpod-mcp.
allowed-tools: Bash(runpodctl:*)
compatibility: Linux, macOS
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Runpodctl

Manage GPU pods, serverless endpoints, templates, volumes, and models.

## Install

`curl -sSL https://cli.runpod.net | bash` (any platform) or `brew install runpod/runpodctl/runpodctl`. Manual binaries, Windows/Linux steps, and the version caveat (`--model-reference` + multi-volume need **v2.4.0+**): **[reference/install.md](reference/install.md)**.

> Old runpodctl builds silently lack newer flags/behaviors (e.g. `--model-reference` doesn't
> exist before v2.4.0) and produce confusing downstream errors — and the Homebrew tap can lag
> well behind. So, before any work:
>
> - **Update to the latest build** — check `runpodctl version`, then run `runpodctl update`
>   (or reinstall from the [latest release](https://github.com/runpod/runpodctl/releases)).
> - **Pin to one recent version for the whole task.**
> - **Never switch between an old and a new binary mid-task** (that flip-flop is a known failure).
> - **Verify once** — `runpodctl version` shows the current build before you continue.

## Quick start

```bash
runpodctl update                    # FIRST: get on the latest build — old versions cause confusing errors
runpodctl version                   # confirm the current version before doing any work
export RUNPOD_API_KEY=your_key      # Non-interactive auth (agents) — runpodctl reads this
runpodctl doctor                    # Interactive first-time setup (API key + SSH) — for humans
runpodctl --help                    # See current top-level commands
runpodctl pod create --help         # Inspect exact current flags before creating
runpodctl gpu list                  # See available GPU types
runpodctl datacenter list           # GPU availability per data center (use to co-locate GPU + volume)
runpodctl hub search vllm           # Find a hub repo
runpodctl serverless create --hub-id <id> --name "my-vllm"  # Deploy from hub
runpodctl template search pytorch   # Find a template
runpodctl pod create --template-id runpod-torch-v21 --gpu-id "NVIDIA GeForce RTX 4090"  # Create from template
runpodctl pod list                  # List your pods
```

> Auth: an agent should `export RUNPOD_API_KEY=...` (non-interactive). `runpodctl
> doctor` is interactive (prompts) and also sets up SSH keys — good for a human's
> first run, not for scripted use.

API key: https://console.runpod.io/user/settings

## Live Help Is Authoritative

Live `runpodctl --help` output is authoritative for exact flags, aliases, and command syntax. Use this skill for workflows, decision rules, safety notes, and common examples.

```bash
runpodctl --help
runpodctl <resource> --help
runpodctl <resource> <action> --help
```

Before using unfamiliar commands, inspect live help first. Do not rely on this skill as an exhaustive flag reference.

**What live help does *not* cover:** output shapes, error codes, and exit-code behavior. `--help` lists flags; it never shows you what a failure looks like. For those, use [reference/output-and-errors.md](reference/output-and-errors.md) — and when in doubt, **probe the binary**: run the command wrong on purpose (`runpodctl serverless get nope`) and read the JSON it emits. Every doc is a snapshot, this skill included; the binary in front of you wins.

## Output & errors

Data is **JSON on stdout** (`--output=yaml` is the only alternative — there is no table
format; anything else silently returns JSON). A failure from the resource commands is a
single flat JSON object on **stderr** plus a **non-zero exit**:

```jsonc
{"error":"failed to get endpoint: endpoint not found","code":"not_found","status":404}
```

**Branch on `code`, never on `status` or the message.** `status` is there only when the
failure arrived on a non-2xx response — GraphQL reports a missing resource as HTTP 200 +
null data, so `if status == 404` misses every GraphQL not-found.

| `code` | what to do |
| --- | --- |
| `network_error` | **retry with backoff** — the only code meaning "couldn't reach the API" |
| `rate_limited` `server_error` | **retry with backoff** — 429/5xx from the API |
| `usage_error` `cli_error` `bad_request` `not_found` `conflict` | don't retry, fix the input |
| `no_credentials` | no key set: `export RUNPOD_API_KEY=…` or `runpodctl doctor` |
| `unauthorized` `forbidden` | a key **is** set but is wrong/expired or lacks access — don't retry, don't re-prompt for a missing key |
| anything else | treat as fatal, surface `error` verbatim — the API can pass through its own code |

**runpodctl never retries internally**; nothing backs off for you.

- **`not_found` always means the API lacks the resource**, never a mistyped local path
  (that's `cli_error`).
- **`cli_error` is a mixed bucket:** local environment problems *and* invocation mistakes
  the command validates itself (e.g. `ssh remove-key` with neither `--name` nor
  `--fingerprint`). Only cobra-enforced required flags are `usage_error`.
- **`usage_error`** = unknown command/flag, bad args, missing cobra-required flag; usage
  text follows the JSON. Runtime errors no longer print usage.
- **Non-empty stderr does not mean failure** — deprecation `warning:` and `note:` lines go
  to stderr on success too. Gate on the exit code, then parse stderr.

Coded errors, the serverless `urls` object and GPU pricing all need **runpodctl ≥ v2.8.0**.
Older binaries emit `{"error":"…"}` with **no `code` and no `status`** — still JSON-shaped,
so a `switch (err.code)` silently gets `undefined` rather than failing loudly. **Gate on
`code` being present**, not on JSON-vs-plaintext; `runpodctl version` is unreliable for
this (plaintext, and a source build reports a placeholder version).

Full code table, the surfaces that still print plaintext (`exec`, legacy `pod`
commands, `project`), and the env-var table (incl. `RUNPOD_INVOKE_URL`):
**[reference/output-and-errors.md](reference/output-and-errors.md)**.

## Decision Rules

- Use Hub when the user wants a known deployable app or worker such as vLLM, ComfyUI, Whisper, or a Runpod-maintained repo.
  - **Picking a worker:** prefer a **first-party or well-adopted, recently-released** worker on a **broad, high-availability GPU pool**. Observable signals via `runpodctl hub list`: `--owner runpod-workers` (first-party), `--order-by releasedAt`/`updatedAt` (recency), `--order-by deploys`/`stars` (adoption). Don't pin a scarce large-GPU tier a small model doesn't need.
- **"Active worker" = minimum workers, not maximum.** If a user asks for an "active worker," they mean `--workers-min 1` (keep one worker always warm → no cold start), **not** `--workers-max 1` (that only caps the ceiling). A warm min-1 worker is ideal for development/iteration.
- ⚠️ **A min-1 worker bills continuously, even while idle** (it defeats scale-to-zero). When you set `--workers-min 1` for dev, you **must** set it back to `--workers-min 0` (or delete the endpoint) when done — otherwise it quietly runs up cost.
  - **Needs runpodctl ≥ v2.10.0.** On earlier binaries `--workers-min 0` and `--idle-timeout 0` were **silently dropped** from the update request (`omitempty` ate the zero), so the reset looked like it applied and the endpoint kept billing. Check `runpodctl version`; on an older binary confirm with `serverless get <id>` and fall back to `PATCH https://rest.runpod.io/v1/endpoints/<id>` with an explicit `{"workersMin":0}`.
- `serverless update` has **no `--gpu-id` flag**. To change an existing endpoint's GPU pool, call `PATCH https://rest.runpod.io/v1/endpoints/<id>` with `{"gpuTypeIds":[...]}` directly.
- **CPU serverless endpoints:** always create them with `runpodctl serverless create --compute-type CPU` — **not** the MCP server, whose v2 `create-endpoint` requires `gpuPoolIds` and has no CPU concept. **Never** use the public control REST `POST https://rest.runpod.io/v1/endpoints` with `"computeType":"CPU"` — it silently provisions a **GPU** endpoint instead (verified evidence in the Serverless command section below).
- Use templates when the user already has a template ID, wants reusable image/config defaults, or needs lower-level control than Hub.
- Use direct pod creation with `--image` when the user has a specific Docker image and does not need a saved template.
- Use serverless for request/response inference APIs and scalable workers; use pods for interactive work, notebooks, training, debugging, or long-lived sessions.
- Use CPU pods for preprocessing, file movement, lightweight scripts, and non-CUDA work. Use GPU pods when CUDA, model inference, training, or GPU memory is required.
- Do not pass GPU flags when creating CPU pods. Check `runpodctl pod create --help` for the current valid flag set.
- **Waiting for a resource to be usable: use `--wait`, don't hand-roll a poll loop** (v2.9.0+). `create` returns as soon as the resource is *scheduled*, which is why a "RUNNING" pod often refuses ssh and a fresh endpoint 404s. `pod create --wait` returns when port 22 answers with an ssh banner; `serverless create --wait` when `/health` reports a ready or running worker. On timeout or ctrl-c the resource is **kept**, and its id is in the error object's `id` field — read that and clean up, don't assume nothing was created (a pod bills by the second; an endpoint with no running worker doesn't, but will start one on the first request).
- Standing up a **service on a pod** (Ollama, ComfyUI, a dev server)? Declare its `--ports` and `--env` **at creation** (they can't be added to a running pod without a reset), then follow the pod development loop in the `runpod-usage` skill (`reference/pod-workflows.md`) — SSH-exec the install, bind to `0.0.0.0`, and poll the proxy URL until it answers.
- For SSH, use `runpodctl pod get <pod-id>` or `runpodctl ssh info <pod-id>` to retrieve connection details. runpodctl has **no interactive-shell command** — `ssh info` returns the connection command + key but does not connect. Run commands over SSH yourself with `ssh user@host "command"`.
- Network volumes are location-sensitive. Check datacenter availability before attaching volumes, and use `send` / `receive` or S3-compatible storage for migrations.
- Clean up paid resources after tests: delete serverless endpoints, pods, and temporary volumes created for validation.
  - **Cost guard on creation:** use `--terminate-after` (deletes the pod); `--stop-after` only *stops* it, so disk/volume keep billing.
  - **Attached volume:** to delete a network volume, remove the pod using it first.

### Serverless facts (context, not rules)

- **Scale-to-zero billing:** serverless endpoints scale to zero with `--workers-min 0` (the default) — no GPU billing while idle, only per request-second; this is the right cost posture for a request/response API.
- **Broken-image tell:** if deployed workers go `ready` but jobs sit `IN_QUEUE` with `inProgress: 0`, the image is broken/mis-dispatching — the fix is to switch to a different worker rather than wait it out.
- **Diagnosing it:** read the worker/job counts with `runpodctl serverless health <endpoint-id>` (v2.9.0+), then read what the workers actually printed with `runpodctl serverless logs <endpoint-id>` (v2.10.0+) — no hand-built curl needed. Repeated `system` "start container" lines with no `container` output means the container exits before the handler runs.

## Commands

Essentials below. **For flags, ask the binary** — `runpodctl <resource> <action> --help`, which is current by construction. [reference/command-reference.md](reference/command-reference.md) holds the part `--help` cannot answer: what a flag *means* when it succeeds, which field to trust, and what a failure looks like.

### Pods

```bash
runpodctl pod list                                   # running pods (+ --all / --status / --since / --created-after)
runpodctl pod get <pod-id>                           # details incl. SSH info + runtimeStatus
runpodctl pod create --template-id <id> --gpu-id "NVIDIA GeForce RTX 4090"   # from template
runpodctl pod create --image <img> --gpu-id "NVIDIA GeForce RTX 4090"        # from image
runpodctl pod create --compute-type cpu --image ubuntu:22.04                 # CPU pod (lowercase `cpu`; serverless uses `CPU`)
runpodctl pod create --image <img> --gpu-id <id> --wait                      # block until ssh answers, then print the pod (v2.9.0+)
runpodctl pod {start|stop|restart|reset|update|delete} <pod-id>              # lifecycle (delete aliases: rm/remove)
runpodctl pod logs <pod-id>                          # recent container+system logs, json lines (v2.10.0+)
runpodctl pod logs <pod-id> --follow                 # keep streaming, reconnects on its own
runpodctl pod logs <pod-id> --since 30m --source system   # platform view: image pull / create / start
```

**A stalled deploy shows up in `--source system`** (v2.10.0+): repeated pull progress, or a
`create container` that never reaches `start`. Use `--source container` for your workload's own
output. Each line is one `{source,line,ts}` object, so pipe it straight to `jq`.

**Read `runtimeStatus`, not `desiredStatus`, to decide whether a pod is usable** (v2.9.0+):
`desiredStatus: RUNNING` says that while the image is still pulling. Field meanings, reason
tokens, and two edges (`--status` filters `desiredStatus` only; `unknown` = lookup failed, not
pod down) → [reference/command-reference.md](reference/command-reference.md#pod-status-fields).

### Hub

Browse/search the Runpod Hub (curated deployable repos).

```bash
runpodctl hub search vllm                            # find a repo (+ hub list [--type/--category/--order-by/--owner])
runpodctl hub get <listing-id|owner/name>            # repo details
```

### Serverless (alias: sls)

```bash
runpodctl serverless list | get <endpoint-id> | delete <endpoint-id>
runpodctl serverless create --name "x" --template-id <id>       # from template
runpodctl serverless create --name "x" --hub-id <listing-id>    # from hub (+ --env KEY=VAL to override defaults)
runpodctl serverless create --hub-id <id> --gpu-id "NVIDIA GeForce RTX 4090" \
  --model-reference https://huggingface.co/<org>/<model>:main   # attach & host-cache a HF model (GPU only)
runpodctl serverless update <endpoint-id> --workers-max 5
runpodctl serverless create --template-id <id> --workers-min 1 --wait          # block until a worker is ready (v2.9.0+)
```

**Invoke URLs come back with the endpoint.** `create`/`get`/`list`/`update` include a
`urls` object (`run`, `runsync`, `health`), so a freshly created endpoint is callable
without a second lookup — read them instead of assembling the URL yourself. They're
built from `RUNPOD_INVOKE_URL` (default `https://api.runpod.ai/v2`), which
`RUNPOD_API_URL`/`RUNPOD_GRAPHQL_URL` do **not** move: [reference/output-and-errors.md](reference/output-and-errors.md#serverless-invoke-urls).

**Reading worker logs** (v2.10.0+) — also first-class, so worker output no longer requires the
MCP lane or a hand-built SSE read:

```bash
runpodctl serverless logs <endpoint-id>                       # every worker's recent logs, json lines
runpodctl serverless logs <endpoint-id> --worker <worker-id>  # just one worker
runpodctl serverless logs <endpoint-id> --follow              # picks up workers that scale up mid-follow
runpodctl serverless logs <endpoint-id> --since 1h --source system   # why a worker will not start
```

Logs belong to a **worker**, not the endpoint, so without `--worker` this reads them all at once and
tags each line with its `workerId`. **The crash-loop tell:** repeated `system` "start container" lines
with no `container` output means the container exits before the handler runs — jobs then sit in the
queue with nothing wrong with capacity.

**Invoking an endpoint** (v2.9.0+) — first-class commands, so an agent does not hand-build a
curl request or manage a bearer token:

```bash
runpodctl serverless run <endpoint-id> --input '{"prompt":"hello"}'   # submit and wait for the result
runpodctl serverless run <endpoint-id> --input-file payload.json      # same, payload from a file ("-" = stdin)
runpodctl serverless run <endpoint-id> --input '{}' --wait 15m        # longer budget (default 5m)
runpodctl serverless run <endpoint-id> --input '{}' --no-wait         # submit, print the queued job, exit 0
runpodctl serverless status <endpoint-id> <job-id>                    # check a job submitted earlier
runpodctl serverless health <endpoint-id>                             # worker + job counts
```

- **Pass only the handler payload** — the cli wraps it as `{"input": <your json>}` itself, so
  pasting a whole curl envelope double-wraps it.
- **`timeout` means the cli stopped waiting, not that the endpoint broke.** When the message
  names a `serverless status` command the job is still running server-side — poll it, do
  **not** re-invoke (that buys a second job).

Payload rules, the stdout/stderr split, exit codes and why `/runsync` is never used →
[reference/command-reference.md](reference/command-reference.md#invoking-an-endpoint-serverless-run-v290).

**Create from hub:** `--hub-id` resolves the hub listing, extracts the build image and config (GPU IDs, container disk, env vars), creates an inline template, and deploys. Accepts both SERVERLESS and POD listing types. GPU IDs and env var defaults from the hub config are included automatically; override with `--gpu-id` and `--env`.

**CPU serverless endpoints** (the always/never rule is in Decision Rules above): create with `runpodctl serverless create --compute-type CPU` (optionally `--instance-id`, e.g. `cpu3g-4-16`). Verified evidence for why the public REST must not be used: 2026-07-14, `POST https://rest.runpod.io/v1/endpoints` with `"computeType":"CPU"` silently returned a GPU endpoint (`gpuCount:1`, `cpuFlavorIds:null`), while `runpodctl --compute-type CPU` correctly returned `computeType:"CPU"` with `instanceIds:["cpu3g-4-16"]`. The MCP server is **not** an alternative here: its v2 `create-endpoint` requires `gpuPoolIds` and the v2 spec has no `computeType`/`cpuFlavor` field at all (verified 2026-07-29). The public control REST is v1-only (`rest.runpod.io/v2` just redirects to docs). The separate **runtime/invoke** API `https://api.runpod.ai/v2/<endpoint-id>/…` (health/run/runsync/openai) is a different v2 and works fine — the v1-vs-v2 caveat here is only about the **control/management** REST.

**Model cache (`--model-reference`):** Attach a Hugging Face model to the endpoint by full URL with a ref, e.g. `https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct:main`. Runpod caches it host-side in the standard HF cache dir (`/runpod-volume/huggingface-cache/hub/`), so the worker loads it directly — no bake, no volume. Repeatable; works with `--template-id`/`--hub-id`, GPU only, **runpodctl v2.4.0+**. Full mechanics + how it compares to baking / network volume / the Model Repository: **[reference/model-caching.md](reference/model-caching.md)**. Worked end-to-end: golden path [20 — model-caching endpoint](../runpod/golden-paths/20-model-caching-endpoint.md).

**Multi-region / high-availability (`--network-volume-ids`):** attach **multiple** network
volumes (one per data center) so workers spread across DCs instead of being pinned to one —
`runpodctl serverless create --template-id <t> --network-volume-ids <v1>,<v2> --data-center-ids <dc1>,<dc2> …`.
**Requires runpodctl ≥ v2.4.0** (older versions don't support multi-volume attach). Check
`runpodctl version`; the Homebrew tap can lag, so prefer the
[GitHub releases](https://github.com/runpod/runpodctl/releases) binary. Data does **not**
sync between volumes automatically — see golden path
[10 — multi-region HA serverless](../runpod/golden-paths/10-multi-region-ha-serverless.md).

For exact serverless flags, run `runpodctl serverless <action> --help`.

### Templates (alias: tpl)

```bash
runpodctl template search <q>                        # find (+ template list [--type official/community/user, --all, --limit])
runpodctl template get <template-id>                 # details (README, env, ports)
runpodctl template create --name "x" --image "img" [--serverless]
runpodctl template delete <template-id>
```

### Network Volumes (alias: nv)

```bash
runpodctl network-volume list                         # List all volumes
runpodctl network-volume get <volume-id>              # Get volume details
runpodctl network-volume create --name "x" --size 100 --data-center-id "US-GA-1"  # Create volume
runpodctl network-volume update <volume-id> --name "new"  # Update volume
runpodctl network-volume delete <volume-id>           # Delete volume
```

For exact network volume flags, run `runpodctl network-volume <action> --help`.

> **No storage-tier flag.** `create` provisions the data center's **default** tier — there's
> no `--type`. To get a **High-Performance** volume, use the console (a ⚡ data center's toggle)
> or a raw **v2 REST** call (`POST https://v2-rest.runpod.io/v2/network-volumes` with
> `"type":"HIGH_PERFORMANCE"`) — or the MCP `create-network-volume` tool, which takes
> `volumeType` (`STANDARD` | `HIGH_PERFORMANCE`). Tier is immutable after creation. Launch details: golden path [21](../runpod/golden-paths/21-storage-tiers.md).

### Models (Model Repository)

`runpodctl model` manages the **Runpod Model Repository** — managed, versioned storage
for your **own** model artifacts (upload once, distributed to workers; not pinned to a
data center like a network volume). What it is, why/how, migrating off a baked-in model,
and Model-Repo-vs-volume: **[reference/model-caching.md](reference/model-caching.md)**.

```bash
runpodctl model list                                  # List your models
runpodctl model list --all                            # List all models (not just yours)
runpodctl model list --name "llama"                   # Filter by name
runpodctl model list --provider "meta"                # Filter by provider
runpodctl model add --name "my-model" --model-path ./model   # Upload a local model dir (multipart)
runpodctl model remove --name "my-model" --owner <owner>     # Remove a model
```

`model add` supports upload sessions, versioning, metadata, and private-source credentials — see live `runpodctl model add --help`.

### Info & SSH

```bash
runpodctl user                                       # account info + balance (alias: me)
runpodctl gpu list                                   # available GPUs + $/hr + per-DC stock (+ --include-unavailable)
runpodctl datacenter list                            # datacenters (alias: dc)
runpodctl ssh info <pod-id>                          # SSH connection details (command + key; NOT an interactive session)
```

**`gpu list` carries pricing and placement data** — `securePricePerHr` /
`communityPricePerHr` (explicitly `null` when that cloud doesn't offer the GPU) and a
`dataCenterAvailability[]` breakdown. Read the breakdown, not just top-level
`stockStatus` (which is only the *best* status across DCs), when a create has to
schedule in a specific DC — and pass `--include-unavailable`, since the default listing
hides no-stock GPUs and can omit one that has stock only in the DC you want. The prices
are **pod on-demand** rates. Shape, stock-value vocabulary and the `"none"` vs
omitted-key sentinel:
[reference/output-and-errors.md](reference/output-and-errors.md#gpu-pricing-and-per-data-center-availability).

`ssh info` gives connection details, not a session — if interactive SSH isn't available, run `ssh user@host "command"`. **Registry auth, `billing` history, and SSH key management** (`ssh add-key`/`remove-key`) are in [reference/command-reference.md](reference/command-reference.md).

### File Transfer

```bash
runpodctl send <path>                                # prints a one-time code, then blocks until the receiver connects
runpodctl receive <code>                             # positional code (no --code flag)
```

Encrypted/incremental/compressed — don't pre-tar. **Key gotchas:** capture the **first line of `send` stdout** (the code) as it streams (background + tee), each `send` mints a **fresh** code, both sides must exit `0`. Full agent flow (pod push via `ssh` + `receive`): [reference/command-reference.md](reference/command-reference.md#file-transfer).

### Utilities

```bash
runpodctl doctor                                      # Diagnose and fix CLI issues
runpodctl update                                      # Update CLI
runpodctl version                                     # Show version
runpodctl completion                                  # Auto-detect shell and install completion
```

## URLs

### Pod URLs

Access exposed ports on your pod:

```
https://<pod-id>-<port>.proxy.runpod.net
```

Example: `https://abc123xyz-8888.proxy.runpod.net`

### Serverless URLs

Prefer `runpodctl serverless run|status|health` (above) — same api, with auth, validation and
bounded polling handled. Use the raw urls for what the commands don't cover: streaming, the
OpenAI-compatible route, or a copy-paste `curl` for a user.

```
https://api.runpod.ai/v2/<endpoint-id>/run        # Async request
https://api.runpod.ai/v2/<endpoint-id>/runsync    # Sync request
https://api.runpod.ai/v2/<endpoint-id>/health     # Health check
https://api.runpod.ai/v2/<endpoint-id>/status/<job-id>  # Job status
```

`serverless create`/`get`/`list`/`update` already return `run`/`runsync`/`health` in a
`urls` object — prefer those over hand-assembling, since a non-default
`RUNPOD_INVOKE_URL` changes the base. Only `status/<job-id>` has to be built by hand.

## Source & docs

- CLI source: https://github.com/runpod/runpodctl
- Releases (binaries): https://github.com/runpod/runpodctl/releases
- Docs: https://docs.runpod.io/runpodctl/overview
