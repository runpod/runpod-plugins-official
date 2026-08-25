---
name: runpod-comfyui-models
description: >-
  Repair imported ComfyUI workflows with missing or broken model metadata for
  ComfyUI-RunpodDirect. Accept a workflow JSON or original ComfyUI output PNG,
  extract and inventory it, and resolve exact model artifacts. Use when a user
  reports a broken workflow, missing models, or failed model discovery; use
  companion-clis for generic Hugging Face transfers and runpod-mcp or runpodctl
  for Pod lifecycle.
user-invocable: true
allowed-tools: Bash(python3:*), Bash(curl:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Repair a ComfyUI workflow for RunpodDirect

Return a new UI workflow JSON containing trustworthy `properties.models` records that
ComfyUI-RunpodDirect can consume — never substitute a plausible model merely to make the
graph queue. Never edit, replace, or overwrite the supplied JSON or PNG. For every
recoverable UI workflow, hand off exactly one new `<workflow-stem>.repaired.json` — even
when resolution is incomplete, ambiguous, gated, or interrupted.

## Terms — workflow vs prompt vs metadata record

| Term | What it is | Role here |
| --- | --- | --- |
| **UI workflow JSON** | The graph the ComfyUI frontend exports/imports: nodes, links, widget values, `properties` | the only JSON this skill annotates |
| **API `prompt` JSON** | The execution format POSTed to `/prompt`, keyed by node id | inventory evidence only — never annotate it |
| **`properties.models` record** | A loader node's model metadata entry (`name`, `url`, `directory`, optional `hash`) | what a repair adds or fixes |

Annotation targets the UI format only; the API prompt has no portable model-metadata
contract.

## Intake

- No artifact yet → ask exactly once: **“Please attach the workflow JSON or the original
  ComfyUI output PNG.”** (Screenshots and re-encoded images usually lose the workflow.)
- Artifact present → no further intake questions: extract when needed, inventory,
  resolve, write the repaired copy, return it.
- No recoverable UI workflow (API-only JSON, stripped PNG) → that is the single blocker;
  request the original UI workflow or PNG.

## Decide the path

| Observed state | Action |
| --- | --- |
| Every model requirement has complete metadata with no reported issues | Preserve its content unchanged, write the one new final JSON, and report that no records were added. Verify or harden only when explicitly requested or when a live failure provides evidence of a problem. |
| Exact filename but no trustworthy URL | Inventory node context, then resolve candidates from original template sources, ComfyUI-Manager, Hugging Face, or Civitai. |
| Generic filename or several credible matches | Do not apply ambiguous metadata or download. Publish the partial workflow, report its path, then show the candidates and ask the user to choose. |
| Gated or license-restricted artifact | Publish the partial workflow first, then stop before authentication/download until access and license acceptance are confirmed. |
| RunpodDirect routes unavailable | Produce the repaired workflow; keep its working manifest temporary and recommend or diagnose RunpodDirect only when the environment warrants it. |

## The references

| Reference | The one question it answers |
| --- | --- |
| [reference/resolution.md](reference/resolution.md) | Which exact artifact is this model? Evidence, source order, confidence policy. |
| [reference/metadata.md](reference/metadata.md) | How is approved metadata written into the workflow? Patch rules, unsafe-URL handling, the exact handoff lines. |
| [reference/runpoddirect.md](reference/runpoddirect.md) | Is the live extension there, and how is it driven safely? Feature detection, download authorization, URL/redirect/secret safety. |

## Low-friction contract

- **inspect / check** → read-only work.
- **find / repair / fix** → also write the new repaired copy.
- **download / make it work on this Pod** → also download verified public unchanged tuples.
- **run / test end to end** → plus one controlled smoke test.

Never reconfirm a step the opening intent already covered. Ask once, and only for a
material decision: ambiguity, gated access or a license, an install or restart, a
cost/storage choice, or an action beyond the opening request. If no decision remains,
finish the authorized work and report once — an optional next step is not a question.

## Workflow

1. **Extract** (PNG input only): `python3 -B extract_png_workflow.py` pulls the embedded
   UI `workflow` from a ComfyUI output PNG into the task's temporary directory.
2. **Inventory**: `python3 -B inventory_workflow_models.py` lists every loader
   selection, subgraphs included — evidence, never an identity decision.
3. **Resolve** each identity per [reference/resolution.md](reference/resolution.md),
   stopping at the first `verified` publisher artifact; keep the review manifest
   temporary.
4. **Apply**: `python3 -B apply_model_metadata.py --allow-unresolved` writes the new
   workflow every time, even when nothing could be resolved; patch rules, unsafe-URL
   handling, and the publish contract live in
   [reference/metadata.md](reference/metadata.md).
5. **Live checks** (only within the request's scope): one batched read-only probe of the
   pod's RunpodDirect routes — `curl` is fine, batched rather than a visible sequence —
   then downloads only as authorized, per
   [reference/runpoddirect.md](reference/runpoddirect.md).

Consult `--help` only after a usage error. Working state (extracted JSON, inventory,
manifest) lives in one task-specific temporary directory, deleted after the repaired
JSON validates; the repaired JSON is the only persistent artifact. Hand off in plain
language — the exact lines are in [reference/metadata.md](reference/metadata.md).

## Routing onward

| The task is actually… | Send it to |
| --- | --- |
| Provision a pod for the workflow | [golden path 02](../runpod/golden-paths/02-comfyui-pod/README.md) (index: [golden paths](../runpod/golden-paths/README.md)), then runpod-mcp or runpodctl |
| Model repo and file already known exactly | `companion-clis` |
| A template pod won't boot, or models are missing on a template pod | `runpod-templates` |
| Install or understand RunpodDirect itself | [reference/runpoddirect.md](reference/runpoddirect.md) |
