---
name: runpod-templates
description: >-
  Runpod's official prebuilt pod
  templates (ComfyUI, PyTorch, and others): what each image ships, which ports and
  paths it uses, how to pick one, how to pin a version, and what is missing on first
  boot. Use when a task says "run <X> on a pod" and an official template already
  covers it, instead of building an image — and when a user needs help with or wants
  to fix something about a Runpod template they are already running (won't boot, can't
  reach the UI, missing models, wrong CUDA line, broken ComfyUI workflow metadata on
  imported workflows): start here and route onward. Deploy
  with runpodctl or runpod-mcp; end-to-end walkthroughs live in the runpod router's
  golden paths.
allowed-tools: Bash(python3:*), Bash(curl:*)
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Official Runpod templates

**Prefer an official template over building an image.** Runpod maintains prebuilt
images for common workloads; deploying one is a create + poll, with no SSH install
step. This skill is the reference for *what those images actually are*. It does not
manage infrastructure — deploy with **runpod-mcp** (if connected) or **runpodctl**.

## Terms — "template" vs the Hub

Two different products share the word "Hub", and conflating them derails discovery:

| Term | What it is | Runs as | Discover with |
| --- | --- | --- | --- |
| **Pod template** (this skill) | A saved pod config — image + ports + disk + env. The official ones appear on Console **Hub template pages** (`console.runpod.io/hub/template/<id>`) | a **pod** | `runpodctl template list --type official` / `template search` · REST `GET /v2/catalog/templates` |
| **Hub repo / listing** | A packaged **serverless worker** (e.g. `runpod-workers/worker-comfyui`) with a handler, deployed as an endpoint | **serverless** | `runpodctl hub list` / `hub search` · MCP `list-hub-repos` / `deploy-hub-repo` |

Same word, disjoint catalogs: `hub search comfyui` returns only the serverless worker
and none of the official ComfyUI **pod** templates, and `template search` returns no
Hub repos. In the REST v2 catalog, pod vs serverless templates are told apart by each
entry's `serverless` flag.

## What "official" means, and how to find them

A template is Runpod-maintained when it reports `isRunpod: true`. Anything else in search
results is community-published: usable, but not covered by this skill and not
version-guaranteed.

```bash
runpodctl template list --type official   # the whole official set (14 as of 2026-08-25)
runpodctl template search <name>          # by name; check isRunpod: true
runpodctl template get <template-id>      # image, ports, portsConfig, disk + full readme
```

`template get` returns the template's **readme** — the description maintained alongside
the image, and the authoritative answer when it disagrees with this skill. Take image
tags, ports, and env from these commands, not from these files: the templates ship on
their own release train and move faster than this repo. The reference files record the
**shape and the gotchas**, which is the expensive part to rediscover.

⚠️ **`runpodctl hub ...` is not how you find pod templates** — see [Terms](#terms--template-vs-the-hub).

To hand a user a Console link, use `https://console.runpod.io/hub/template/<template-id>`.

### REST v2 has no template search — only slices you filter yourself

REST v2 has no query/search parameter for templates, so every "search" is a client-side
filter over a fetched slice:

| Endpoint | Params | Returns |
| --- | --- | --- |
| `GET /v2/catalog/templates` | `source=official\|verified\|community` (default `official`) | the public catalog slice |
| `GET /v2/templates` | none | only templates **you own** |
| `GET /v2/templates/{id}` | — | one template, owned or catalog |

**`official` (14) and `verified` (3) are fully enumerable; `community` is capped at 100
with pagination explicitly unsupported.** A community template past that cap never
enters a slice the API can return, and `runpodctl template search` reads those same
server-side slices — so it has no view past the cap either. If a user names one you
cannot find, ask them for the template id rather than concluding it does not exist.

`isRunpod` is a GraphQL/v1 field with **no v2 equivalent** — in v2, "official" is the
`source` slice you requested, not a flag on the record.

Catalog entries carry **`allowedCudaVersions`**, which is the reliable way to pick between
CUDA-line variants of the same template — pair it with `runpodctl pod create
--min-cuda-version` instead of inferring from the GPU name.

## The templates

| Workload | Reference | Deploy walkthrough |
| --- | --- | --- |
| **ComfyUI** — image generation UI at a URL | [`reference/comfyui.md`](reference/comfyui.md) | [golden path 02, variant B](../runpod/golden-paths/02-comfyui-pod/variant-b-prebuilt.md) |
| **PyTorch** — general GPU base / dev box (2.1 → 2.9, incl. cluster + ROCm builds) | [`reference/pytorch.md`](reference/pytorch.md) | [golden path 06](../runpod/golden-paths/06-dev-pod.md) |
| **Ubuntu** — bare 20.04 / 22.04 / 24.04 (**CPU** category) | TODO | — |
| **Network storage file browser** (GPU + CPU) | TODO | [golden path 07](../runpod/golden-paths/07-network-volume-handoff.md) |

Add a template by adding one file here and one row above. Do not create a new skill
per template — the task shape is identical and every registered skill costs context in
every session.

## How to use a template reference

Each file under `reference/` answers the same questions in the same order, so an agent
can skim to the one it needs:

1. **Identity** — template name, id, image, upstream source repo.
2. **Variants** — CUDA/arch/GPU-generation splits and which to pick.
3. **Ports and credentials** — what is exposed and any default login.
4. **Autostart** — what is already running on boot, with the exact command.
5. **Paths** — where the app, its config, and its data live (and what a network
   volume mount changes).
6. **Readiness** — how long first boot takes and the exact signal for "actually
   serving". `Running` is never the signal.
7. **What does not ship** — the gap between "booted" and "usable", and how to close
   it programmatically rather than by clicking.
8. **Sizing** — container disk and minimum VRAM.
9. **Version pinning** — how to hold a known-good version.

One file is the exception: [`reference/comfyui-model-repair.md`](reference/comfyui-model-repair.md)
is a **usage guide** — a ComfyUI workflow repair procedure that drives the scripts in
[`scripts/`](scripts/) — not a 9-question template reference.

## Routing onward — this skill is the hub, not the destination

A user asking about a template rarely wants the reference file itself; they want a
template deployed, fixed, or replaced. Land here, identify which, and hand off:

| The user wants to… | Send them to |
| --- | --- |
| **Deploy** a template end to end | the matching golden path in the table above ([index](../runpod/golden-paths/README.md)) — live-verified runs with real commands |
| **Fix a pod that won't serve** ("Running" but URL dead, 404/502) | the template's reference file, §Readiness — then [`runpod-usage/reference/gotchas.md`](../runpod-usage/reference/gotchas.md) |
| **Fix a ComfyUI workflow whose models won't download** (missing/broken model metadata, imported workflow or PNG) | [the repair guide](reference/comfyui-model-repair.md) — it drives the repair scripts in [`scripts/`](scripts/). The official ComfyUI templates ship ComfyUI-RunpodDirect, so its automatic-download path applies |
| **Add models / files** to a running template pod | the template's reference file (§What does not ship), or `companion-clis` for generic Hugging Face transfers |
| **Customize beyond what the template ships** (pinned versions, extra nodes, lighter image) | [`runpod-usage/reference/building-images.md`](../runpod-usage/reference/building-images.md) — build `FROM` the official base |
| **A serverless worker**, not a pod | not a pod template — Hub workers via `runpodctl` / `runpod-mcp` |

Reference files here answer *what is in the image*; they never duplicate a walkthrough or
a repair procedure — they point at the owner.
