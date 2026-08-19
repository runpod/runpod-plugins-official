# Golden paths

End-to-end tasks an agent should be able to complete **start to finish** using
the Runpod skills — the yardstick for "can it actually do everything agentically",
and a worked reference to copy from.

These are agent-facing scenarios, not marketing demos. An agent — not a human
clicking the Console — must be able to complete them. **Paths 01–19 were run live on
a real account** (each caught real skill gaps we then folded back), commands and
outputs are the real ones, and every test resource was torn down after. 04's training
phase was verified as the train phase of golden path 08; 01–10 were run 2026-07-07→10,
and 11–19 on 2026-07-13. Path 20 was live-verified 2026-07-15 (diagnosed via the Runpod MCP
worker logs — a `COMPLETED` job off a `--model-reference` cache hit). Path 21 documents
**provisioning (launch) only** — verified against the CLI/REST specs + MCP source (2026-07-16),
not a full live run. Paths 22, 23, and 25 (minimal-image + storage-model paths) were added
2026-07-16 and **run live** (built, pushed, deployed, invoked/SSH'd, torn down). The
load-balanced image contract is covered by the already-live-verified [path 14](14-load-balancing-endpoint.md).

## Before you run any path (shared prerequisites)

Every path assumes this baseline — set it up once, then follow the path:

- **Auth + SSH keys** — resolve `RUNPOD_API_KEY` (or `runpodctl doctor` / MCP OAuth) and,
  for any pod path, **register an SSH key before creating the pod**. Full setup:
  [`../../runpod-usage/reference/getting-started.md`](../../runpod-usage/reference/getting-started.md).
- **Companion CLIs** — image paths need `docker` running **and `docker login`** to a
  registry you can push to; some paths need `hf` (HF token) or `aws` (Runpod S3 keys,
  which are **Console-only** — an agent can't self-provision them). See
  [`../../companion-clis/SKILL.md`](../../companion-clis/SKILL.md).
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

Each doc follows the same template: **Goal · Status · Lane(s) → When to use →
Prerequisites → Walkthrough (real commands) → Verify it works (the actual test +
observed output) → Gotchas we hit → Cost & cleanup → Skill gaps folded back.**

## Table of contents

| # | Golden path | Kind | Approach(es) | Status |
| --- | --- | --- | --- | --- |
| 01 | [Ollama server on a pod + URL](01-ollama-pod.md) | pod / server | runpodctl pod + SSH | ✅ live-verified |
| 02 | [ComfyUI server on a pod + URL](02-comfyui-pod/README.md) | pod / server | — | ✅ live-verified |
| | ↳ [Variant A — from scratch](02-comfyui-pod/variant-a-from-scratch.md) | | PyTorch template + install | ✅ |
| | ↳ [Variant B — prebuilt official image](02-comfyui-pod/variant-b-prebuilt.md) | | official template (auto-starts) | ✅ (faster) |
| 03 | [Whisper endpoint (audio → text)](03-whisper-endpoint/README.md) | serverless | — | ✅ live-verified |
| | ↳ [Variant A — Runpod Hub worker](03-whisper-endpoint/variant-a-hub.md) | | runpodctl + Hub (recommended) | ✅ |
| | ↳ [Variant B — from scratch with flash](03-whisper-endpoint/variant-b-flash.md) | | flash code-first handler | ✅ |
| 04 | [LoRA fine-tune (training run) on a pod](04-finetune-pod.md) | pod / batch job | runpodctl pod + volume | ✅ live-verified (training phase, via 08) |
| 05 | [Custom model → serverless endpoint](05-model-to-endpoint-pipeline.md) | cross-lane pipeline | hf → docker → runpodctl | ✅ live-verified |
| 06 | [Interactive dev pod (SSH / VS Code)](06-dev-pod.md) | pod / interactive | runpodctl pod + volume | ✅ live-verified |
| 07 | [Network-volume handoff (pod → volume → serverless)](07-network-volume-handoff.md) | pod + serverless | runpodctl + flash | ✅ live-verified |
| 08 | [Fine-tune → serve (LoRA on a pod → serverless)](08-finetune-to-serverless.md) | train → serve loop | runpodctl + peft/axolotl + flash | ✅ live-verified |
| 09 | [Custom serverless dev loop (iterate in a pod → dual-mode image → serverless)](09-custom-serverless-dev-loop/README.md) | custom image / escape hatch | runpodctl + docker (dual-mode `MODE_TO_RUN`) | ✅ live-verified |
| 10 | [Multi-region HA serverless (multi-volume + data sync)](10-multi-region-ha-serverless.md) | serverless / availability | runpodctl ≥v2.4.0 (`--network-volume-ids`) + S3 API (aws) | ✅ live-verified |
| 11 | [Public Endpoints (call a ready hosted model)](11-public-endpoints.md) | serverless / hosted | Runpod Public Endpoint API (native + OpenAI-compatible) | ✅ live-verified |
| 12 | [Serverless streaming (`/stream`)](12-serverless-streaming.md) | serverless | generator handler + `/stream` | ✅ live-verified |
| 13 | [Autoscaling tuning](13-autoscaling-tuning.md) | serverless / scaling | runpodctl + scaler config (queue-delay / request-count) | ✅ live-verified |
| 14 | [Load-balancing endpoint (non-flash)](14-load-balancing-endpoint.md) | serverless / LB | GraphQL `saveEndpoint type:"LB"` + HTTP-server worker | ✅ live-verified |
| 15 | [Monitor & debug / observability](15-monitor-and-debug.md) | serverless / ops | `runpodctl serverless health`/`status`/`logs` (or `/health` + `/status` + v2 REST / MCP worker logs) + config-change events | ✅ live-verified |
| 16 | [Serverless webhooks](16-serverless-webhooks.md) | serverless | `webhook` field on `/run` (push vs poll) | ✅ live-verified |
| 17 | [Serverless WebSocket worker](17-serverless-websocket.md) | serverless / LB | `worker-lb-websocket` + `wss://<ep>.api.runpod.ai/ws` | ✅ live-verified |
| 18 | [Concurrent handler (per-worker concurrency)](18-concurrent-handler.md) | serverless / throughput | async `concurrency_modifier` | ✅ live-verified |
| 19 | [3-region same-file endpoint](19-three-region-same-file.md) | serverless / availability | 3 volumes + S3 sync + GraphQL multi-volume attach | ✅ live-verified |
| 20 | [Host-cached HF model endpoint (`--model-reference`)](20-model-caching-endpoint.md) | serverless / model delivery | runpodctl ≥v2.4.0 (`--model-reference`) + vLLM worker | ✅ live-verified |
| 21 | [Network volume storage tiers (standard vs high-performance)](21-storage-tiers.md) | storage / provisioning | runpodctl (standard) + REST v2 / console (high-perf) | 📘 documented (launch only) |
| 22 | [Minimal pod image (+ don't kill SSH)](22-minimal-pod-image/README.md) | image contract / pod | docker buildx + runpodctl pod (CPU) + SSH | ✅ live-verified |
| 23 | [Minimal serverless queue image](23-minimal-queue-image/README.md) | image contract / serverless | docker buildx + runpodctl serverless (CPU) + `/runsync` | ✅ live-verified |
| 25 | [Bake into image vs mount a network volume](25-bake-vs-mount/README.md) | storage model / image | docker buildx + runpodctl nv + CPU pod (`df -T`: overlay vs MooseFS) | ✅ live-verified |

> **When a path has two variants, prefer the prebuilt/Hub one** (Variant B for
> ComfyUI, Variant A for Whisper) unless you need custom code — that's the
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
3. **Check the Status before you trust it.** ✅ live-verified paths were run end to
   end — commands and outputs are real. ⚠️ spec paths are reasoned from the docs,
   **not proven**; treat their exact flags/paths as unconfirmed (each file lists
   what a real run should verify).
4. **Follow the Walkthrough, then actually run Verify** — "Running" ≠ "ready".
   Don't report success until the service answers a real request.
5. **If the skills fall short, fold the fix back** into the relevant `SKILL.md` /
   `reference/*.md` — that's how a live run improves the skills (see each path's
   "skill gaps folded back" section for examples).

## Status legend

- **stub** — goal captured, not yet specified.
- **drafted — gaps identified** — flow + acceptance criteria written; skill gaps listed.
- **spec (not yet live-verified)** — full flow, acceptance criteria, and gotchas
  written and grounded in the skills + docs, but **not yet run** end to end;
  exact flags/paths still need confirming on a real account.
- **covered** — the skills contain everything an agent needs; verified by a run.
- **✅ live-verified** (used in the table above) — run end to end on a real account; the
  commands and the "observed output" blocks are from that run.
- **📘 documented (launch only)** (used in the table above) — the provisioning/launch steps
  are written and grounded in the CLI/REST specs, but a full end-to-end run wasn't performed.

## Cross-cutting requirements (every path)

1. **Auth** — resolve `RUNPOD_API_KEY` (or `runpodctl doctor` / MCP OAuth) before acting.
2. **Agentic execution** — an agent has no Console/web terminal; it must drive
   everything through the CLI/API/MCP and SSH-exec, non-interactively.
3. **Readiness, not fire-and-forget** — poll until the service actually answers;
   don't report success on "pod Running" alone.
4. **Escalate on manual steps** — if something needs a human (OAuth, a quota
   increase, a license click, a missing credential), stop and tell the user.
5. **Clean up** — set `--stop-after` / `--terminate-after` on test resources.
