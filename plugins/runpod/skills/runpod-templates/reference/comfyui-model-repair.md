# Repair a ComfyUI workflow for RunpodDirect

This is a **usage guide** in the `runpod-templates` skill — a repair procedure, not a
9-question template reference. The helper scripts it drives live in
[`../scripts/`](../scripts/) (`inventory_workflow_models.py`, `apply_model_metadata.py`,
`extract_png_workflow.py`).

Return a new UI workflow JSON containing trustworthy `properties.models` records that
ComfyUI-RunpodDirect can consume — never substitute a plausible model merely to make the
graph queue. Never edit, replace, or overwrite the supplied JSON or PNG. For every
recoverable UI workflow, hand off exactly one new `<workflow-stem>.repaired.json` — even
when resolution is incomplete, ambiguous, gated, or interrupted.

## Terms — workflow vs prompt vs metadata record

| Term | What it is | Role here |
| --- | --- | --- |
| **UI workflow JSON** | The graph the ComfyUI frontend exports/imports: nodes, links, widget values, `properties` | the only JSON this guide annotates |
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
| [comfyui-repair/resolution.md](comfyui-repair/resolution.md) | Which exact artifact is this model? Evidence, source order, confidence policy. |
| [comfyui-repair/metadata.md](comfyui-repair/metadata.md) | How is approved metadata written into the workflow? Patch rules, unsafe-URL handling, the exact handoff lines. |
| [comfyui-repair/runpoddirect.md](comfyui-repair/runpoddirect.md) | Is the live extension there, and how is it driven safely? Feature detection, download authorization, URL/redirect/secret safety. |

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

Shell commands do not resolve like the links in this guide: links resolve relative to
this file, but a `python3 ../scripts/...` invocation resolves against the agent's
working directory, which is usually somewhere else. Resolve the skill's `scripts/`
directory once, from the location of this guide, and use it for every invocation:

```bash
SKILL_SCRIPTS="$(cd "$(dirname <path-to-this-guide>)/../scripts" && pwd)"
```

(`<path-to-this-guide>` is the absolute path this reference was loaded from. Verify with
`ls "$SKILL_SCRIPTS"` — it must list the three scripts below — before running anything.)

1. **Extract** (PNG input only): `python3 -B "$SKILL_SCRIPTS/extract_png_workflow.py"` pulls
   the embedded UI `workflow` from a ComfyUI output PNG into the task's temporary
   directory.
2. **Inventory**: `python3 -B "$SKILL_SCRIPTS/inventory_workflow_models.py"` lists every
   loader selection, subgraphs included — evidence, never an identity decision.
3. **Resolve** each identity per [comfyui-repair/resolution.md](comfyui-repair/resolution.md),
   stopping at the first `verified` publisher artifact; keep the review manifest
   temporary.
4. **Apply**: `python3 -B "$SKILL_SCRIPTS/apply_model_metadata.py" --allow-unresolved` writes
   the new workflow every time, even when nothing could be resolved; patch rules,
   unsafe-URL handling, and the publish contract live in
   [comfyui-repair/metadata.md](comfyui-repair/metadata.md).
5. **Live checks** (only within the request's scope): one batched read-only probe of the
   pod's RunpodDirect routes — `curl` is fine, batched rather than a visible sequence —
   then downloads only as authorized, per
   [comfyui-repair/runpoddirect.md](comfyui-repair/runpoddirect.md).

Consult `--help` only after a usage error. Working state (extracted JSON, inventory,
manifest) lives in one task-specific temporary directory, deleted after the repaired
JSON validates; the repaired JSON is the only persistent artifact. Hand off in plain
language — the exact lines are in [comfyui-repair/metadata.md](comfyui-repair/metadata.md).

## Routing onward

| The task is actually… | Send it to |
| --- | --- |
| Provision a pod for the workflow | [golden path 02](../../runpod/golden-paths/02-comfyui-pod/README.md) (index: [golden paths](../../runpod/golden-paths/README.md)), then runpod-mcp or runpodctl |
| Model repo and file already known exactly | `companion-clis` |
| Another template problem (a pod that won't boot, models missing on first boot) | the other reference files in this skill — [comfyui.md](comfyui.md) / [pytorch.md](pytorch.md) |
| Install or understand RunpodDirect itself | [comfyui-repair/runpoddirect.md](comfyui-repair/runpoddirect.md) |
