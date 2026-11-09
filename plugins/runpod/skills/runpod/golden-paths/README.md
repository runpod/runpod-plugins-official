# Golden paths

End-to-end tasks an agent should be able to complete **start to finish** using
the Runpod skills — the yardstick for "can it actually do everything agentically",
and a worked reference to copy from.

These are agent-facing scenarios, not marketing demos. An agent — not a human
clicking the Console — must be able to complete them. Most paths were run live on a real
account (each caught real skill gaps we then folded back); the commands and outputs in
their run records are the real ones, and every test resource was torn down after. Each
path's status and date are in the [table](#table-of-contents) and in the header of the path
itself ([legend](#status-legend)): 04's training phase was verified as the train phase of
golden path 08, and 21 documents **provisioning (launch) only** (spec-checked 2026-07-29). The
load-balanced image contract is covered by [path 14](14-load-balancing-endpoint.md).

## Before you run any path (shared prerequisites)

Every path assumes this baseline — set it up once, then follow the path:

- **Auth + SSH keys** — resolve `RUNPOD_API_KEY` (or `runpodctl doctor` / MCP OAuth) and,
  for any pod path, **register an SSH key before creating the pod**. Full setup:
  [`../../runpod-usage/reference/getting-started.md`](../../runpod-usage/reference/getting-started.md).
  GP26 file authoring needs no cloud credentials.
- **Verify the key** before the first call: `curl -s -o /dev/null -w '%{http_code}'
  https://api.runpod.io/v2/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`. The
  same key authorizes the REST v2 API at `api.runpod.io/v2`, endpoint calls at
  `api.runpod.ai/v2`, and Public Endpoints. A path that uses `runpodctl` or `flash` assumes it
  is installed and authenticated.
- **Companion CLIs** — image paths need `docker` running **and `docker login`** to a
  registry you can push to; some paths need `hf` (HF token) or `aws` (Runpod S3 keys,
  which are **Console-only** — an agent can't self-provision them). See
  [`../../runpod-companion-clis/SKILL.md`](../../runpod-companion-clis/SKILL.md).
- **Placeholders are yours to fill** — commands use `<template-id>`, `<endpoint-id>`,
  `<vol-…>`, etc.; capture the real id a command returns and reuse it in the next step.
  **Docker images shown as `<your-registry>/gpNN-…` are the original live-run images —
  you cannot push to that namespace; `docker login` and substitute your own.** Real ids
  shown inside "observed output" blocks are evidence from the original run, not values to
  paste.
- **runpodctl version** — a few paths need **≥ v2.4.0** (multi-volume attach); the
  Homebrew tap can lag, so install from
  [GitHub releases](https://github.com/runpod/runpodctl/releases) if `runpodctl version`
  is behind.

## Layout

- A path with **one approach** is a single file: `NN-name.md`.
- A path with **multiple approaches** is a folder: `NN-name/` with a `README.md`
  (goal, "which variant?", shared schema/gotchas/cost) plus one file per variant.

Each doc starts with frontmatter that says which tools it drives, whether an agent with only
the Runpod MCP tools can finish it, and which concepts (`../../runpod-usage/concepts/`) it
works with:

```yaml
---
lanes: [runpodctl, ssh]
mcp: partial        # full | partial | none
concepts: [pod, network-volume, pod-ssh-access]
---
```

A folder path can also carry a `skill.json`, which the Runpod backend syncs into the Hub. It
follows [`skill.schema.json`](skill.schema.json); `hooks/check_skill_json.py` checks it in CI,
including that `id` is the folder name and every URL points at a file in this repo.

Each doc follows the same template: **Goal · Status · Lane(s) → When to use →
Prerequisites → Walkthrough (real commands) → Verify it works (the actual test +
observed output) → Gotchas we hit → Cost & cleanup → Skill gaps folded back.**

## Table of contents

| # | Golden path | Kind | Approach(es) | Status |
| --- | --- | --- | --- | --- |
| 01 | [Ollama server on a pod + URL](01-ollama-pod/README.md) | pod / server | runpodctl pod + SSH | live-verified 2026-07-07 |
| 02 | [ComfyUI server on a pod + URL](02-comfyui-pod/README.md) | pod / server | — | live-verified 2026-07-07 |
| | ↳ [Variant A — from scratch](02-comfyui-pod/variant-a-from-scratch.md) | | PyTorch template + install | live-verified 2026-07-07 |
| | ↳ [Variant B — prebuilt official image](02-comfyui-pod/variant-b-prebuilt.md) | | official template (auto-starts) | live-verified 2026-07-07 (faster) |
| 03 | [Whisper endpoint (audio → text)](03-whisper-endpoint/README.md) | serverless | — | live-verified 2026-07-07 |
| | ↳ [Variant A — Runpod Hub worker](03-whisper-endpoint/variant-a-hub.md) | | runpodctl + Hub (recommended) | live-verified 2026-07-07 |
| | ↳ [Variant B — from scratch with the Runpod SDK](03-whisper-endpoint/variant-b-flash.md) | | Runpod SDK `@app.queue` (`rp flash`) | live-verified 2026-10-16 |
| 04 | [LoRA fine-tune (training run) on a pod](04-finetune-pod.md) | pod / batch job | runpodctl pod + volume | live-verified 2026-07-10 (training phase, via 08) |
| 05 | [Custom model → serverless endpoint](05-model-to-endpoint-pipeline.md) | cross-lane pipeline | hf → docker → runpodctl | live-verified 2026-07-10 |
| 06 | [Interactive dev pod (SSH / VS Code)](06-dev-pod.md) | pod / interactive | runpodctl pod + volume | live-verified 2026-07-10 |
| 07 | [Network-volume handoff (pod → volume → serverless)](07-network-volume-handoff.md) | pod + serverless | runpodctl + Runpod SDK (`rp flash`) | live-verified 2026-10-16 (SDK read step; pod step 2026-07-10; volume write + read-back in `rp flash dev --once` on `runpod` 2.1.0, 2026-11-04) |
| 08 | [Fine-tune → serve (LoRA on a pod → serverless)](08-finetune-to-serverless.md) | train → serve loop | runpodctl + peft/axolotl + Runpod SDK (`rp flash`) | live-verified 2026-10-17 (SDK serve step; pod training 2026-07-10) |
| 09 | [Custom serverless dev loop (iterate in a pod → dual-mode image → serverless)](09-custom-serverless-dev-loop/README.md) | custom image / escape hatch | runpodctl + docker (dual-mode `MODE_TO_RUN`) | live-verified 2026-07-10 |
| 10 | [Multi-region HA serverless (multi-volume + data sync)](10-multi-region-ha-serverless.md) | serverless / availability | runpodctl ≥v2.4.0 (`--network-volume-ids`) + S3 API (aws) | live-verified 2026-07-10 |
| 11 | [Public Endpoints (call a ready hosted model)](11-public-endpoints.md) | serverless / hosted | Runpod Public Endpoint API (native + OpenAI-compatible) | live-verified 2026-07-13 |
| 12 | [Serverless streaming (`/stream`)](12-serverless-streaming.md) | serverless | generator handler + `/stream` | live-verified 2026-07-13 |
| 13 | [Autoscaling tuning](13-autoscaling-tuning.md) | serverless / scaling | runpodctl + scaler config (queue-delay / request-count) | live-verified 2026-07-13 |
| 14 | [Load-balancing endpoint (non-flash)](14-load-balancing-endpoint.md) | serverless / LB | v2 `"type":"LOAD_BALANCER"` (or GraphQL `saveEndpoint type:"LB"`) + HTTP-server worker | live-verified 2026-10-29 (v2 route; GraphQL run 2026-07-13) |
| 15 | [Monitor & debug / observability](15-monitor-and-debug.md) | serverless / ops | `runpodctl serverless health`/`status`/`logs` (or `/health` + `/status` + v2 REST / MCP worker logs) + config-change events | live-verified 2026-07-13 |
| 16 | [Serverless webhooks](16-serverless-webhooks.md) | serverless | `webhook` field on `/run` (push vs poll) | live-verified 2026-07-13 |
| 17 | [Serverless WebSocket worker](17-serverless-websocket.md) | serverless / LB | `worker-lb-websocket` + `wss://<ep>.api.runpod.ai/ws` | legacy (last live run 2026-07-13) |
| 18 | [Concurrent handler (per-worker concurrency)](18-concurrent-handler.md) | serverless / throughput | async `concurrency_modifier` | live-verified 2026-07-13 |
| 19 | [3-region same-file endpoint](19-three-region-same-file.md) | serverless / availability | 3 volumes + S3 sync + GraphQL multi-volume attach | legacy (last live run 2026-07-13) |
| 20 | [Host-cached HF model endpoint (`--model-reference`)](20-model-caching-endpoint.md) | serverless / model delivery | runpodctl ≥v2.4.0 (`--model-reference`) + vLLM worker | live-verified 2026-07-15 |
| 21 | [Network volume storage tiers (standard vs high-performance)](21-storage-tiers.md) | storage / provisioning | runpodctl (standard) + REST v2 / console (high-perf) | spec-checked 2026-07-29 (launch only) |
| 22 | [Minimal pod image (+ don't kill SSH)](22-minimal-pod-image/README.md) | image contract / pod | docker buildx + runpodctl pod (CPU) + SSH | live-verified 2026-07-16 |
| 23 | [Minimal serverless queue image](23-minimal-queue-image/README.md) | image contract / serverless | docker buildx + runpodctl serverless (CPU) + `/runsync` | live-verified 2026-07-16 |
| 25 | [Bake into image vs mount a network volume](25-bake-vs-mount/README.md) | storage model / image | docker buildx + runpodctl nv + CPU pod (`df -T`: overlay vs MooseFS) | live-verified 2026-07-16 |
| 26 | [Author a complete template project](26-template-project/README.md) | project authoring / Pod / queue / LB | app files + documented build/deployment handoff | spec-checked 2026-10-06 (local/container checks recorded in path, no live Runpod verification) |
| | ↳ [Variant — application Pod](26-template-project/variant-pod.md) | | Pod image, app port | spec-checked 2026-10-06 (local checks only) |
| | ↳ [Variant — queue worker](26-template-project/variant-queue.md) | | queue handler image | spec-checked 2026-10-06 (local checks only) |
| | ↳ [Variant — load-balanced HTTP worker](26-template-project/variant-load-balanced.md) | | load-balanced image | spec-checked 2026-10-06 (local checks only) |
| | ↳ [Variant — heavy layers and retained editable Pod state](26-template-project/variant-pytorch.md) | | PyTorch base + code layer | spec-checked 2026-10-06 (local checks only) |
| 27 | [vLLM model: Pod first, then a load-balancing endpoint](27-vllm-pod-to-endpoint.md) | pod + serverless / LB | runpod-mcp (`create-pod` with `args`, `create-endpoint` `LOAD_BALANCER`) + `test_endpoint.py` | live-verified 2026-11-06 |

> **When a path has two variants, prefer the prebuilt/Hub one** (Variant B for
> ComfyUI, Variant A for Whisper) unless you need custom code or explicitly requested template/Dockerfile authoring — that's the
> development loop's "prefer prebuilt over from-scratch" rule in action.

> **Complementary pairs:** 13 (autoscaling) + 18 (concurrency) — concurrency raises
> per-worker throughput, autoscaling adds/removes workers. 14 (load-balancing) + 17
> (WebSocket) share the `type:"LB"` substrate. 10 + 19 are the 2-region and 3-region
> multi-volume HA cases. **22 (pod) + 23 (queue) are the minimal-image-per-contract pair**
> ([14](14-load-balancing-endpoint.md) is the load-balanced counterpart) — same "build a tiny
> image" task, one per contract — and double as evals for
> [building-images.md](../../runpod-usage/reference/building-images.md).

## How to use these

1. **Match your task to a row** in the table (or read
   [`../../runpod-usage/reference/development-loop.md`](../../runpod-usage/reference/development-loop.md)
   first if you're unsure whether it's a pod or a serverless job).
2. **For a multi-variant path, open the folder `README.md` first** — it tells you
   which variant to pick and holds the shared schema/gotchas/cost. Then open the
   variant file for the step-by-step.
3. **Check the Status before you trust it** ([legend](#status-legend)). Live-verified
   paths were run end to end, so commands and outputs are real. Spec-checked paths are
   reasoned from the docs, **not proven**; treat their exact flags/paths as unconfirmed
   (each file lists what a real run should verify). Legacy paths name the route to use
   instead.
4. **Follow the Walkthrough, then actually run Verify** — "Running" ≠ "ready".
   Don't report success until the service answers a real request.
5. **If the skills fall short, fold the fix back** into the relevant `SKILL.md` /
   `reference/*.md` — that's how a live run improves the skills (see each path's
   "skill gaps folded back" section for examples).

## Status legend

Every path states one status in its frontmatter (`status`, `verified`, `evals`) and in the
`> **Status:**` line under its title; the table above repeats it, and
`hooks/check_golden_paths.py` fails CI when the three disagree.

- **live-verified YYYY-MM-DD** — the documented route was run end to end on a real account
  on that date; commands and "observed output" blocks are from a run.
- **spec-checked YYYY-MM-DD** — checked against CLI `--help`, the OpenAPI specs or the MCP
  source (and any local checks the path lists) on that date, but not run end to end on
  Runpod; treat exact flags and paths as unconfirmed.
- **legacy (last live run YYYY-MM-DD)** — it was run end to end, but on a route the skills
  now steer away from (GraphQL, REST v1, or a removed CLI flag), and the preferred route it
  names has not been run end to end. Its ordering and gotchas still hold; use the preferred
  route.

`evals` names the scenarios that cover the path: `<skill>/evals/<name>` files (hand-check
specifications; nothing executes them) and `live:<check>` ids, which the weekly
`live-evals` workflow runs for free against the REST v2 API. Older run records inside the
paths say COVERED or ✅ for live-verified and DOCUMENTED or 📘 for spec-checked.

## Cross-cutting requirements (every path)

1. **Auth** — the [shared prerequisites](#before-you-run-any-path-shared-prerequisites) before live infrastructure actions.
2. **Agentic execution** — an agent has no Console/web terminal; it must drive
   everything through the CLI/API/MCP and SSH-exec, non-interactively.
3. **Readiness, not fire-and-forget** — poll until the service actually answers;
   don't report success on "pod Running" alone.
4. **Escalate on manual steps** — if something needs a human (OAuth, a quota
   increase, a license click, a missing credential), stop and tell the user.
5. **Clean up** — remove test resources when done (`runpodctl pod remove`).
