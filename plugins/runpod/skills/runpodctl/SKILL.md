---
name: runpodctl
description: >-
  Runpod CLI for managing GPU/CPU workloads from the terminal — pods, serverless
  endpoints, templates, network volumes, Hub deploys, models, SSH, and file
  transfer (send/receive). Use for terminal/CI/scripting, SSH setup, `doctor`,
  or when the Runpod MCP tools are not connected; prefer runpod-mcp for structured
  tool calls in an MCP-enabled session.
allowed-tools: Bash(runpodctl:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.9.0" # x-release-please-version
  concepts: [runpodctl, pod, cpu-pod, serverless-endpoint, template, network-volume, hub-repo, ssh-key, file-transfer, model-store, volume-cache]
license: Apache-2.0
---

# Runpodctl

Manage GPU pods, serverless endpoints, templates, volumes, and models. For serverless development workflows, use the [Runpod SDK](https://github.com/runpod/runpod-python) regardless of CLI version.

## Install

`curl -fsSL https://cli.runpod.net | sudo bash` (Linux/macOS, and Windows via WSL) or `brew install runpod/runpodctl/runpodctl`. Manual binaries and the Windows and conda steps: the [runpodctl README](https://github.com/runpod/runpodctl#install), beside the `install.sh` they describe. API key: https://console.runpod.io/user/settings

> Old builds silently lack newer flags/behaviors (e.g. `--model-reference` doesn't exist before
> v2.4.0) and produce confusing downstream errors, and the Homebrew tap can lag well behind.
> Before any work: **update to the latest build** (`runpodctl version`, then `runpodctl update`,
> or reinstall from the [latest release](https://github.com/runpod/runpodctl/releases)); **pin one
> recent version for the whole task**; **never switch between an old and a new binary mid-task**
> (a known failure); **verify once** with `runpodctl version` before you continue.

## Quick start

```bash
runpodctl update && runpodctl version   # FIRST: latest build, confirmed, before any work
export RUNPOD_API_KEY=your_key      # agents: non-interactive auth, read by runpodctl
runpodctl doctor                    # humans: interactive first-time setup (prompts for API key + SSH keys); not for scripted use
runpodctl pod create --help         # inspect exact current flags before creating
runpodctl gpu list                  # GPU types
runpodctl datacenter list           # GPU availability per data center (co-locate GPU + volume)
runpodctl hub search vllm           # find a hub repo
runpodctl serverless create --hub-id <id> --name "my-vllm"  # deploy from hub
runpodctl template search pytorch   # find a template
runpodctl pod create --template-id runpod-torch-v280 --gpu-id "NVIDIA GeForce RTX 4090" --min-cuda-version 12.8  # create from template
runpodctl pod list                  # your pods
```

## Live Help Is Authoritative

Live `runpodctl --help`, `runpodctl <resource> --help` and `runpodctl <resource> <action> --help` are authoritative for exact flags, aliases, and syntax (the generated pages under [`runpodctl/docs/`](https://github.com/runpod/runpodctl/tree/main/docs) mirror them). Inspect live help before unfamiliar commands; this skill covers workflows, decision rules, safety notes, and common examples, and is not an exhaustive flag reference.

Live help does **not** cover output shapes, error codes, or exit-code behavior: use [reference/output-and-errors.md](reference/output-and-errors.md), and when in doubt **probe the binary** (run it wrong on purpose, e.g. `runpodctl serverless get nope`, and read the JSON). Every doc is a snapshot, this skill included; the binary in front of you wins.

## Output & errors

Data is **JSON on stdout** (`--output=yaml` is the only alternative; there is no table format; v2.10.0+ rejects any other value with `usage_error`, v2.9.0 and earlier silently return JSON). A failure is one flat JSON object on **stderr** plus a **non-zero exit**:

```jsonc
{"error":"failed to get endpoint: endpoint not found","code":"not_found","status":404}
```

- **Branch on `code`, never on `status` or the message** (GraphQL reports a missing resource as HTTP 200 + null data, so `status` is often absent).
- **Retry with backoff only on `network_error`, `rate_limited`, `server_error`;** runpodctl never retries internally. `no_credentials` = no key set; `unauthorized`/`forbidden` = a key is set but wrong or lacks access (don't re-prompt). `usage_error`, `cli_error`, `bad_request`, `not_found`, `conflict`: fix the input. Any other code is fatal: surface `error` verbatim.
- **Gate on the exit code, then parse stderr:** deprecation `warning:`/`note:` lines go to stderr on success too.
- **Coded errors, the serverless `urls` object and GPU pricing need runpodctl ≥ v2.8.0.** Older binaries emit `{"error":"…"}` with no `code`, so gate on `code` being present, not on `runpodctl version`.
- **`project` behaves differently per build** (exit 0 with errors on stdout through v3.0.1; exit 1 with a Runpod SDK notice in builds with [runpod/runpodctl#382](https://github.com/runpod/runpodctl/pull/382)). Treat that notice as fatal.

Full code table, `cli_error` vs `usage_error`, plain-text exceptions, the exact SDK notice, and the env-var table (incl. `RUNPOD_INVOKE_URL`): **[reference/output-and-errors.md](reference/output-and-errors.md)**.

## Decision Rules

- **Hub** for a known deployable app or worker (vLLM, ComfyUI, Whisper, a Runpod-maintained repo). **Picking a worker:** prefer a **first-party or well-adopted, recently-released** worker on a **broad, high-availability GPU pool**; signals in `runpodctl hub list`: `--owner runpod-workers` (first-party), `--order-by releasedAt`/`updatedAt` (recency), `--order-by deploys`/`stars` (adoption). Don't pin a scarce large-GPU tier a small model doesn't need.
- **Templates** when the user already has a template ID, wants reusable image/config defaults, or needs lower-level control than Hub. **`pod create --image`** for a specific Docker image with no saved template.
- **Serverless** for request/response inference APIs and scalable workers; **pods** for interactive work, notebooks, training, debugging, or long-lived sessions. **CPU pods** for preprocessing, file movement, lightweight scripts, and non-CUDA work; **GPU pods** when CUDA, model inference, training, or GPU memory is required.
- **"Active worker" = minimum workers, not maximum:** `--workers-min 1` (one worker always warm → no cold start; ideal for development/iteration), **not** `--workers-max 1` (that only caps the ceiling).
- ⚠️ **A min-1 worker bills continuously, even while idle** (it defeats scale-to-zero). After dev you **must** set `--workers-min 0` (or delete the endpoint), or it quietly runs up cost.
  - **Needs runpodctl ≥ v2.10.0.** Earlier binaries **silently dropped** `--workers-min 0` and `--idle-timeout 0` from the update request (`omitempty` ate the zero): the reset looked applied and the endpoint kept billing. Check `runpodctl version`; on an older binary confirm with `serverless get <id>` and fall back to `PATCH https://api.runpod.io/v2/serverless/<id>` with an explicit `{"workers":{"min":0}}`.
- **Set the execution timeout on every endpoint create.** A v2 create without `timeout` comes back `"timeout": 0` (live-verified 2026-10-29; the spec claims 300000 ms), which the server treats as no per-request limit. runpodctl ≥ 2.14.0 has `serverless create --execution-timeout <seconds>` (as of 2.14.0 `serverless update` does not; check `--help`); read the timeout back with `serverless get`, and fix a 0 with `PATCH https://api.runpod.io/v2/serverless/<id>` `{"timeout":<ms>}`.
- `serverless update` has **no `--gpu-id` flag**. To change an endpoint's GPU pools, `PATCH https://api.runpod.io/v2/serverless/<id>` with `{"gpu":{"pools":["ADA_24"]}}` (pool ids, from the `pool` field of `GET /v2/catalog/gpus`). Sending `pools` without `excludedTypes` clears any exclusions.
- **CPU serverless endpoints:** `runpodctl serverless create --compute-type CPU`, or REST v2 `POST https://api.runpod.io/v2/serverless` with a `cpu` block in place of `gpu`. **Never** send `"computeType":"CPU"` to REST v1 `POST https://rest.runpod.io/v1/endpoints`: it silently provisions a **GPU** endpoint ([evidence](reference/command-reference.md#cpu-endpoints-and-rest-v1)).
- **Leave `--cloud-type` at its `SECURE` default.** Community Cloud hosts are approved vendors; Secure Cloud hosts are data-center-grade providers and tend toward more stable behavior. Pass `--cloud-type COMMUNITY` only when the user explicitly asks (a public port 22 there needs a machine with a public IP, which the CLI cannot request).
- A CPU pod gets 2 vCPUs on whichever CPU flavor has the most stock; `--name` defaults to the image name without its tag. CPU pods take a network volume (`--network-volume-id`) but not a pod volume (`--volume-in-gb` is rejected). Do not pass GPU flags.
- **Set a CUDA floor on every GPU create: `--min-cuda-version 12.8`** (`pod create` and `serverless create`; not `template create`). Without it a modern image can land on a host too old to run it, and the create will not reject it: the container dies at startup or silently runs on CPU. `13.0` only for a CUDA-13 image; omit for CPU. Rule, exceptions and capacity check: [`runpod-usage` gpu-selection "pin the CUDA floor"](../runpod-usage/reference/gpu-selection.md#step-3-pin-the-cuda-floor).
- **Waiting for a resource to be usable: use `--wait`, don't hand-roll a poll loop** (v2.9.0+). `create` returns once the resource is *scheduled*, which is why a "RUNNING" pod often refuses ssh and a fresh endpoint 404s. `pod create --wait` returns when port 22 answers with an ssh banner. `pod create --wait-for running` (v2.15.0+) returns when the container is up, no ssh needed: use it when container-up is all the task needs, or for an image that does not start sshd (most cpu images, since cpu pods get no Runpod-managed ssh), where plain `--wait` would bill through the whole timeout and then fail; a cpu image that starts its own sshd still satisfies plain `--wait`, so keep that when the user needs ssh. `serverless create --wait` returns when `/health` reports a ready or running worker. On timeout or ctrl-c the resource is **kept** and its id is in the error object's `id` field: read it and clean up, don't assume nothing was created (a pod bills by the second; an endpoint with no running worker doesn't, but starts one on the first request).
- **A service on a pod** (Ollama, ComfyUI, a dev server): declare its `--ports` and `--env` at creation when possible (`runpodctl pod update` can change them on an existing pod), then follow the pod development loop in `runpod-usage` (`reference/pod-workflows.md`): SSH-exec the install, bind to `0.0.0.0`, poll the proxy URL until it answers.
- **SSH:** connection details from `runpodctl pod get <pod-id>` or `runpodctl ssh info <pod-id>`. runpodctl has **no interactive-shell command**: `ssh info` returns the connection command + key but does not connect, so run `ssh user@host "command"` yourself.
- Network volumes are location-sensitive: check datacenter availability before attaching, and migrate with `send` / `receive` or S3-compatible storage.
- Clean up paid resources after tests: serverless endpoints, pods, and temporary volumes created for validation.
  - **Cost guard:** remove the pod when the work is done (`runpodctl pod remove <pod-id>`). For an unattended deadline, schedule a stop from inside the pod: Runpod pods ship `runpodctl` and a pod-scoped API key ([Manage Pods](https://docs.runpod.io/pods/manage-pods)). A stopped pod still bills for disk and any volume.
  - **`--stop-after` / `--terminate-after` never worked.** Before v2.12.0 `pod create` accepts both, but the backend never enforced them, so the pod keeps running and billing past the deadline; v2.12.0 removed them. If `runpodctl pod create --help` still lists them, run `runpodctl update`. Never offer them as a cost guard.
  - **Attached volume:** to delete a network volume, remove the pod using it first.

### Serverless facts (context, not rules)

- **Scale-to-zero billing:** endpoints scale to zero with `--workers-min 0` (the default): no GPU billing while idle, only per request-second; the right cost posture for a request/response API.
- **Broken-image tell:** deployed workers go `ready` but jobs sit `IN_QUEUE` with `inProgress: 0` → the image is broken/mis-dispatching; switch to a different worker rather than wait it out.
- **Diagnosing it:** worker/job counts with `runpodctl serverless health <endpoint-id>` (v2.9.0+), then what the workers printed with `runpodctl serverless logs <endpoint-id>` (v2.10.0+); no hand-built curl needed. Repeated `system` "start container" lines with no `container` output = the container exits before the handler runs.

## Commands

Essentials only; flags come from `--help`. [reference/command-reference.md](reference/command-reference.md) holds what `--help` cannot answer: what a flag *means* when it succeeds, which field to trust, and what a failure looks like.

### Pods

```bash
runpodctl pod list                                   # running pods (+ --all / --status / --since / --created-after)
runpodctl pod get <pod-id>                           # details incl. SSH info + runtimeStatus
runpodctl pod create --template-id <id> --gpu-id "NVIDIA GeForce RTX 4090" --min-cuda-version 12.8   # from template (or --image <img>)
runpodctl pod create --compute-type cpu --image ubuntu:22.04                 # CPU pod (2 vCPUs; name defaults to the image)
runpodctl pod create --image <img> --gpu-id <id> --wait                      # block until ssh answers, then print the pod (v2.9.0+)
runpodctl pod create --compute-type cpu --image ubuntu:22.04 --wait-for running  # block until the container is up; no sshd needed (v2.15.0+)
runpodctl pod {start|stop|restart|update|delete} <pod-id>                    # lifecycle (delete aliases: rm/remove)
runpodctl pod logs <pod-id> [--follow] [--since 30m --source system]          # recent container+system logs, json lines (v2.10.0+); --follow keeps streaming and reconnects on its own; --source system = platform view: image pull / create / start
```

runpodctl v3.0.0 removed `pod reset`; use `pod restart` only when a restart is intended.

**A stalled deploy shows up in `--source system`** (v2.10.0+): repeated pull progress, or a `create container` that never reaches `start`. `--source container` is your workload's own output. Each line is one `{source,line,ts}` object; pipe it to `jq`.

**Read `runtimeStatus`, not `desiredStatus`, to decide whether a pod is usable** (v2.9.0+): `desiredStatus: RUNNING` says that while the image is still pulling. Field meanings, reason tokens, and two edges (`--status` filters `desiredStatus` only; `unknown` = lookup failed, not pod down) → [reference/command-reference.md](reference/command-reference.md#pod-status-fields).

### Hub

Browse/search existing Runpod Hub listings; pick the execution lane with the [router capability matrix](../runpod/SKILL.md#runpod-mcp-vs-runpodctl-the-overlap). Authoring a project's Hub listing files: [runpod-build-template](../runpod-build-template/SKILL.md).

```bash
runpodctl hub search vllm                            # find a repo (+ hub list [--type/--category/--order-by/--owner])
runpodctl hub get <listing-id|owner/name>            # repo details
```

### Serverless (alias: sls)

```bash
runpodctl serverless list | get <endpoint-id> | delete <endpoint-id>
runpodctl serverless create --name "x" --template-id <id> --min-cuda-version 12.8   # from template
runpodctl serverless create --name "x" --hub-id <listing-id>    # from hub (+ --env KEY=VAL to override defaults)
runpodctl serverless create --hub-id <id> --gpu-id "NVIDIA GeForce RTX 4090" \
  --model-reference https://huggingface.co/<org>/<model>:main   # attach & host-cache a HF model (GPU only)
runpodctl serverless update <endpoint-id> --workers-max 5
runpodctl serverless create --template-id <id> --workers-min 1 --wait          # block until a worker is ready (v2.9.0+)
```

**Invoke URLs come back with the endpoint:** `create`/`get`/`list`/`update` include a `urls` object (`run`, `runsync`, `health`), so read them instead of assembling the URL. They're built from `RUNPOD_INVOKE_URL` (default `https://api.runpod.ai/v2`), which `RUNPOD_API_URL`/`RUNPOD_GRAPHQL_URL` do **not** move: [reference/output-and-errors.md](reference/output-and-errors.md#serverless-invoke-urls).

**Reading worker logs** (v2.10.0+), first-class, so worker output needs neither the MCP lane nor a hand-built SSE read:

```bash
runpodctl serverless logs <endpoint-id>                       # every worker's recent logs, json lines, each tagged with its workerId
runpodctl serverless logs <endpoint-id> --worker <worker-id>  # just one worker
runpodctl serverless logs <endpoint-id> --follow              # picks up workers that scale up mid-follow
runpodctl serverless logs <endpoint-id> --since 1h --source system   # why a worker will not start
```

The crash-loop tell is under [Serverless facts](#serverless-facts-context-not-rules).

**Invoking an endpoint** (v2.9.0+), first-class, so an agent does not hand-build a curl request or manage a bearer token:

```bash
runpodctl serverless run <endpoint-id> --input '{"prompt":"hello"}'   # submit and wait for the result
runpodctl serverless run <endpoint-id> --input-file payload.json      # same, payload from a file ("-" = stdin)
runpodctl serverless run <endpoint-id> --input '{}' --wait 15m        # longer budget (default 5m)
runpodctl serverless run <endpoint-id> --input '{}' --no-wait         # submit, print the queued job, exit 0
runpodctl serverless status <endpoint-id> <job-id>                    # check a job submitted earlier
runpodctl serverless health <endpoint-id>                             # worker + job counts
```

- **Pass only the handler payload:** the cli wraps it as `{"input": <your json>}` itself, so pasting a whole curl envelope double-wraps it.
- **`timeout` means the cli stopped waiting, not that the endpoint broke.** When the message names a `serverless status` command the job is still running server-side: poll it, do **not** re-invoke (that buys a second job).

Payload rules, the stdout/stderr split, exit codes and why `/runsync` is never used → [reference/command-reference.md](reference/command-reference.md#invoking-an-endpoint-serverless-run-v290).

**Create from hub:** `--hub-id` resolves the hub listing, extracts the build image and config (GPU IDs, container disk, env vars), creates an inline template, and deploys. Accepts both SERVERLESS and POD listing types. The hub config's GPU IDs and env defaults are included automatically; override with `--gpu-id` and `--env`.

**CPU serverless endpoints** (rule in Decision Rules): `runpodctl serverless create --compute-type CPU` (optionally `--instance-id`, e.g. `cpu3g-4-16`). The 2026-07-14 evidence against REST v1, and why the invoke API is unaffected: [reference/command-reference.md](reference/command-reference.md#cpu-endpoints-and-rest-v1).

**Model cache (`--model-reference`, GPU only, runpodctl v2.4.0+):** attach a Hugging Face model by full URL with a ref (`…:main`); Runpod caches it host-side in the standard HF cache dir (`/runpod-volume/huggingface-cache/hub/`), so the worker loads it directly: no bake, no volume. Works with `--template-id` and `--hub-id`. Example, the one-cached-model limit, and how it compares to baking / network volume / the Model Repository: **[reference/model-caching.md](reference/model-caching.md)**. Worked end-to-end: golden path [20 — model-caching endpoint](../runpod/golden-paths/20-model-caching-endpoint.md).

**Multi-region / HA:** `--network-volume-ids <v1>,<v2> --data-center-ids <dc1>,<dc2>` (one volume per DC; **runpodctl ≥ v2.4.0**, and the Homebrew tap can lag). Data does **not** sync between volumes: golden path [10](../runpod/golden-paths/10-multi-region-ha-serverless.md). Model-reference output on `update` and the `--clear-models` shape: [reference/command-reference.md](reference/command-reference.md#endpoint-update-and-zero-values).

### Templates (alias: tpl)

```bash
runpodctl template search <q>                        # find (+ template list [--type official/community/user, --all, --limit])
runpodctl template get <template-id>                 # details (README, env, ports)
runpodctl template create --name "x" --image "img" [--serverless]
runpodctl template delete <template-id>
```

### Network Volumes (alias: nv)

```bash
runpodctl network-volume list | get <volume-id> | delete <volume-id>
runpodctl network-volume create --name "x" --size 100 --data-center-id "US-GA-1"
runpodctl network-volume update <volume-id> --name "new"
```

Exact flags: `runpodctl network-volume <action> --help`.

> **No storage-tier flag.** `create` provisions the data center's **default** tier; there's no `--type`. For a **High-Performance** volume use the console (a ⚡ data center's toggle), a raw **v2 REST** call (`POST https://v2-rest.runpod.io/v2/network-volumes` with `"type":"HIGH_PERFORMANCE"`), or the MCP `create-network-volume` tool's `volumeType` (`STANDARD` | `HIGH_PERFORMANCE`). Tier is immutable after creation. Launch details: golden path [21](../runpod/golden-paths/21-storage-tiers.md).

### Models (Model Repository)

`runpodctl model` manages the **Runpod Model Repository**: managed, versioned storage for your **own** model artifacts (upload once, distributed to workers; not pinned to a data center like a network volume). What it is, why/how, migrating off a baked-in model, and Model-Repo-vs-volume: **[reference/model-caching.md](reference/model-caching.md)**.

```bash
runpodctl model list [--all] [--name "llama"] [--provider "meta"]   # yours by default; --all = not just yours
runpodctl model add --name "my-model" --model-path ./model   # upload a local model dir (multipart)
runpodctl model remove --name "my-model" --owner <owner>
```

`model add` also supports upload sessions, versioning, metadata, and private-source credentials: see live `runpodctl model add --help`.

### Info & SSH

```bash
runpodctl user                                       # account info + balance (alias: me)
runpodctl gpu list                                   # available GPUs + $/hr + per-DC stock (+ --include-unavailable)
runpodctl datacenter list                            # datacenters (alias: dc)
runpodctl ssh info <pod-id>                          # SSH connection details (command + key; NOT an interactive session)
```

**`gpu list` carries pod on-demand pricing and a `dataCenterAvailability[]` breakdown.** When a create must land in a specific DC, read the breakdown (top-level `stockStatus` is only the best across DCs) and pass `--include-unavailable` (the default listing hides no-stock GPUs and can omit one that has stock only in your DC). Shape, stock vocabulary, `null` prices and the `"none"` vs omitted-key sentinel: [reference/output-and-errors.md](reference/output-and-errors.md#gpu-pricing-and-per-data-center-availability).

Registry auth, `billing` and SSH key management: [reference/command-reference.md](reference/command-reference.md). Host key pinning (which versions pin, and why **`ssh forget` needs the operator's go-ahead**): [Pod host key trust](reference/command-reference.md#pod-host-key-trust-v2150).

### File Transfer

```bash
runpodctl send <path>                                # prints a one-time code, then blocks until the receiver connects
runpodctl receive <code>                             # positional code (no --code flag)
```

Encrypted/incremental/compressed: don't pre-tar. **Key gotchas:** capture the **first line of `send` stdout** (the code) as it streams (background + tee); each `send` mints a **fresh** code; both sides must exit `0`. Full agent flow (pod push via `ssh` + `receive`): [reference/command-reference.md](reference/command-reference.md#file-transfer).

### Utilities

`runpodctl doctor` (diagnose and fix CLI issues), `update`, `version`, `completion` (auto-detects the shell and installs completion).

## URLs

- **Pod:** `https://<pod-id>-<port>.proxy.runpod.net` for an exposed port (e.g. `https://abc123xyz-8888.proxy.runpod.net`).
- **Serverless:** prefer `runpodctl serverless run|status|health` (same api, with auth, validation and bounded polling handled) and the `urls` object the endpoint commands return. Use raw urls only for what the commands don't cover: streaming, the OpenAI-compatible route, or a copy-paste `curl` for a user. Only `status/<job-id>` has to be built by hand.

```
https://api.runpod.ai/v2/<endpoint-id>/run        # Async request
https://api.runpod.ai/v2/<endpoint-id>/runsync    # Sync request
https://api.runpod.ai/v2/<endpoint-id>/health     # Health check
https://api.runpod.ai/v2/<endpoint-id>/status/<job-id>  # Job status
```

## Source & docs

- CLI source: https://github.com/runpod/runpodctl
- Releases (binaries): https://github.com/runpod/runpodctl/releases
- Docs: https://docs.runpod.io/runpodctl/overview
