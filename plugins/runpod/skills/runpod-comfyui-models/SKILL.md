---
name: runpod-comfyui-models
description: >-
  Repair imported ComfyUI workflows with missing or broken model metadata for
  ComfyUI-RunpodDirect. Accept a workflow JSON or original ComfyUI output PNG, extract
  and inventory it, resolve exact model artifacts, and always return a new workflow JSON
  when a UI workflow is recoverable. Use when a user reports a broken workflow, missing models, or failed
  model discovery; use companion-clis for generic Hugging Face transfers and runpod-mcp
  or runpodctl for Pod lifecycle.
user-invocable: true
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Repair a ComfyUI workflow for RunpodDirect

When model metadata is missing or broken, return a new UI workflow JSON containing
trustworthy `properties.models` records that ComfyUI-RunpodDirect can consume. If every
model requirement already has structurally complete `name`, `url`, and `directory`
metadata with no reported issues, preserve the supplied workflow unchanged. Do not
rewrite complete metadata merely to pin a revision or add a hash unless the user asks for
verification/hardening or a live check exposes a problem. Checking a live Pod or
downloading models is optional and depends on the request. Do not substitute a plausible
model merely to make the graph queue.

For every recoverable UI workflow, create and hand off exactly one new persistent file:
`<workflow-stem>.repaired.json` (or a collision-safe numbered variant), even when model
resolution is incomplete, ambiguous, gated, or interrupted by a provider/tool failure.
The workflow file is a mandatory deliverable and the task is not complete until it exists.
Never edit, replace, or overwrite the supplied JSON or PNG. Resolve the final file's full
absolute path and include one final file reference in the form
`Fixed workflow: <full-absolute-path>`; make that same path clickable when supported and
show no other artifact path.
Extracted or normalized workflow JSON, inventory output, and the resolution
manifest are disposable working state: create them only inside one task-specific
temporary directory, never beside the source or final file, and remove that exact
agent-created directory after the repaired JSON passes re-inventory. Do not list its
paths in the final response. If no metadata change is needed, still write the unchanged UI
workflow to the one final JSON and state that no records were added. Never create a second
persistent audit file; summarize audit evidence in chat when requested.

When some requirements remain unresolved, apply only verified records, preserve all
unresolved loader selections unchanged, remove known invalid or unsafe metadata rather
than carrying it into the new copy, publish the JSON with `partial` status, and list the
remaining requirements in chat. Never omit the workflow merely because it is partial,
and never claim that a partial workflow is fully repaired. The only normal no-output case
is that the supplied artifact contains no recoverable UI workflow (for example API-only
JSON or a PNG with stripped workflow metadata). A filesystem failure is a blocker only
after trying a collision-safe name in a writable task output directory.

Assume the user is non-technical unless they clearly ask for implementation or audit
details. Keep manifests, hashes, revision IDs, directory keys, API routes, helper names,
and extraction/inventory mechanics out of the default handoff. After a repair, summarize
how many models received download information and name them when the list is short. Show
the technical `Model | Directory | Source URL | SHA-256` table only when the user asks for
technical details, provenance, or an audit. If no records were added, say that plainly.

## Plain-language handoff

For a recoverable UI workflow, use this order and keep it brief:

1. `Fixed workflow: <full-absolute-path>` as the only file reference.
2. `Status: Ready to import` when all supported model references are covered, or
   `Status: Workflow file created — <count> model(s) still need attention` when partial.
3. `Next: Drag this JSON into ComfyUI.`
4. `Automatic downloads: Ready`, `Automatic downloads: Not checked on your ComfyUI`, or
   `Automatic downloads: Not available — RunpodDirect was not detected`, followed by one
   plain sentence explaining what that means.
5. State plainly whether model files were downloaded and whether the workflow was run.

If attention is needed, list the affected model filenames and the human decision in plain
language after the file path. Do not use internal labels such as `verified`, `high`,
`ambiguous`, `unresolved`, `artifact tuple`, `UI format`, or `re-inventory` without a
short translation. Do not expose command transcripts or ask the user to run extraction,
`curl`, API, or metadata-editing commands. A concise explanation is enough; offer deeper
technical evidence only when requested.

Always state the RunpodDirect status explicitly in user-friendly language:

- **Confirmed active** → **Automatic downloads: Ready.** Tell the user to drag the
  actionable JSON into ComfyUI; the
  RunpodDirect Missing Models window should appear. If it does not, refresh ComfyUI and
  import the JSON again.
- **Not checked** → **Automatic downloads: Not checked on your ComfyUI.** Say that
  automatic direct-to-Pod downloading requires
  [ComfyUI-RunpodDirect](https://github.com/MadiatorLabs/ComfyUI-RunpodDirect), and that
  its installation/load status was not verified. Do not promise that the Missing Models
  window will appear.
- **Unavailable or not detected** → **Automatic downloads: Not available — RunpodDirect
  was not detected.** Say that the workflow file is ready, but automatic downloading requires
  RunpodDirect to be installed, enabled, and loaded. Offer setup help; do not install,
  update, or restart ComfyUI without authorization.

The metadata-enriched JSON remains the portable deliverable when RunpodDirect is absent,
but metadata alone does not create the Missing Models UI or download files to the Pod.

For a task that also creates or starts a Pod, first consult the
[worked examples](../runpod/golden-paths/README.md), then route that infrastructure work
through `runpod-mcp` or `runpodctl`. Return here once ComfyUI is reachable.

## Intake

- If the user reports an imported workflow problem but has not supplied the artifact,
  ask exactly once: **“Please attach the workflow JSON or the original ComfyUI output
  PNG.”** Explain only when useful that screenshots, JPEGs, and re-encoded PNGs usually do
  not retain the embedded workflow.
- Do not first ask for model names, node screenshots, browser access, Pod credentials, or
  manual metadata. Inspect the supplied artifact to discover what is actually missing.
- Once the JSON or PNG is present, continue without another intake question: extract when
  needed, inventory, resolve, write a repaired JSON copy, re-inventory it, and return the
  file without waiting for the user to ask for it. The user should not need to extract the
  embedded workflow or separately request the output.
- If an image contains only an API `prompt`, has stripped metadata, or lacks a repairable
  UI workflow, make that the single blocker and request the original UI workflow JSON or
  original ComfyUI PNG.

## Decide the path

| Observed state | Action |
| --- | --- |
| Every model requirement has complete metadata with no reported issues | Preserve its content unchanged, write the one new final JSON, and report that no records were added. Verify or harden only when explicitly requested or when a live failure provides evidence of a problem. |
| Exact filename but no trustworthy URL | Inventory node context, then resolve candidates from original template sources, ComfyUI-Manager, Hugging Face, or Civitai. |
| Generic filename or several credible matches | Do not apply ambiguous metadata or download. Publish the partial workflow, report its path, then show the candidates and ask the user to choose. |
| Gated or license-restricted artifact | Publish the partial workflow first, then stop before authentication/download until access and license acceptance are confirmed. |
| RunpodDirect routes unavailable | Produce the repaired workflow; keep its working manifest temporary and recommend or diagnose RunpodDirect only when the environment warrants it. |

Read [reference/resolution.md](reference/resolution.md) when any model needs discovery.
Read [reference/metadata.md](reference/metadata.md) before editing a workflow. Read
[reference/runpoddirect.md](reference/runpoddirect.md) only when checking or using the
live extension.

## Low-friction contract

- Interpret intent once: **inspect/check** permits read-only work; **find/repair/fix** also
  permits writing a new repaired copy; **download/make it work on this Pod** also permits
  downloading verified public unchanged tuples; **run/test end to end** additionally
  permits one controlled smoke test. Do not reconfirm an action already covered by that
  opening intent.
- Treat a supplied workflow/PNG plus a request to find or repair models as authorization
  for extraction, inventory, read-only source lookup, read-only live checks, and writing
  a repaired **new copy**. Do not ask for confirmation between those steps.
- Batch independent provider lookups and send the whole reviewed model list through one
  missing-model check. Prefer connected provider APIs, MCP, or built-in web access over
  a sequence of shell `curl` commands. If a tool-level network permission is unavoidable,
  group the minimum read-only work into one narrowly scoped request.
- Stop discovery at the first `verified` publisher/official artifact with an exact path,
  immutable revision, compatible loader/directory, and trusted hash. Do not inventory
  mirrors after identity is already settled.
- Ask one consolidated question only when a material decision remains: credible
  ambiguity, a merely `high`-confidence match, gated access/license acceptance,
  custom-node install/update/restart, an uncovered destination or storage/cost
  choice, or a download/queue action outside the opening request. When a UI workflow is
  available, ask that question only after publishing and reporting the mandatory partial
  workflow in the same handoff.
- If no decision remains, finish the authorized work and report the result once. Do not
  turn optional next steps into another required question.
- Once a UI workflow is recovered, no ambiguity, access gate, lookup failure, or partial
  result may bypass final JSON creation. A response containing only findings, a model
  table, or instructions is incomplete.

## Workflow

1. Preserve the original artifact. Create one uniquely named task directory under the
   system temporary directory for all non-deliverable files. Resolve and record its exact
   absolute path; cleanup may target only this directory and only after confirming it was
   created for the current task. Use a `finally`-style cleanup on every terminal path,
   including success, ambiguity, gating, invalid or API-only input, cancellation, tool
   error, and failed validation. Never retain that directory as an audit deliverable. For
   a ComfyUI-generated output PNG, invoke
   `extract_png_workflow.py` directly with Python's `-B` flag to extract the embedded
   `workflow` record to a JSON file inside that temporary directory; its result also
   reports the recognized records.
   Consult `--help` only after a usage error or when a non-default option is needed. Prefer
   that UI record over the embedded API `prompt`. If only `prompt` remains, extract it
   explicitly for inventory only and request the original UI workflow before annotation;
   report absent or invalid fields as possible re-encoding damage. For JSON input, use it
   directly. Then run `inventory_workflow_models.py` with `-B`. Include nodes inside
   subgraphs. Treat the result as evidence, not a model-identity decision.
   If every requirement reports complete metadata with no issues, stop without provider
   discovery or metadata editing. Use an empty reviewed manifest with the inventory's
   semantic workflow hash so the apply helper validates the unchanged UI workflow before
   atomically publishing the new final JSON. Then clean the task directory and hand back
   only the final file's full absolute path.
2. Resolve missing records together with the confidence policy in
   [reference/resolution.md](reference/resolution.md). Keep unresolved and ambiguous
   records visible rather than dropping them, and stop looking once each identity is
   verified. When a live ComfyUI instance is available, call `folder_paths` once alongside
   provider lookup to confirm all runtime directory keys.
3. Build one compact review manifest inside the task-specific temporary directory:
   consuming node, exact filename, runtime directory key,
   immutable or otherwise exact URL, source/revision, SHA-256, size when known,
   license/gating, confidence, and proposed action. A request to repair authorizes
   verified records to be written to a new copy without a second confirmation. Before an
   authorized download, summarize the verified tuple in chat without attaching or linking
   the manifest. Record any decision needed for a `high`-confidence candidate or metadata
   conflict, but do not pause for the answer yet. The source is never an output target.
   The manifest must never assert that an unresolved guess was verified. Omit unresolved,
   ambiguous, gated, or rejected records; proceed through step 5 so the finalizer preserves
   those loader selections and publishes the partial workflow. Ask the consolidated choice
   only in the same handoff, after the `Fixed workflow` path.
4. When a live instance is available, send the complete reviewed model array through one
   RunpodDirect missing-model check. That real batch also feature-detects the route; do not
   make an empty probe or repeat it per model. An exact filename found on disk proves
   presence, not identity; verify SHA-256 when the expected hash is known.
5. If inventory reports UI format, always run `apply_model_metadata.py` directly with
   Python's `-B` flag and `--allow-unresolved` to create the new workflow from the verified
   records, including when the manifest is empty. The helper re-inventories the in-memory
   candidate, refuses invalid UI output, preserves unresolved selections, and atomically
   publishes the sole final JSON. Its structured result reports the full absolute output
   path, `complete` or `partial` status, and unresolved count. Consult
   `--help` only after a usage error or when a non-default option is needed.
   When replacing conflicting metadata, review the reported field-level change and set
   `replace_existing: true` only on that manifest item; the helper refuses an implicit
   replacement.
   If a proposed metadata record fails validation, omit that record and finalize the
   workflow with that requirement unresolved; do not omit the final workflow. Only after
   the helper reports successful validation and publication, remove the exact
   task-specific temporary directory and make the repaired JSON the sole new persistent
   artifact and only full absolute file path/link in the final response. Report models
   needing attention in plain language, summarize records added without technical details
   by default, and state the RunpodDirect status using the user-friendly three-state rule
   above. Never finish with only a report: verify the final path exists
   immediately before responding. For API-only prompt JSON, keep the reviewed manifest internal,
   request the original UI workflow; the finally-style cleanup still removes the task
   directory. Do not invent UI
   metadata fields in an execution prompt or hand off a manifest as a substitute.
6. Reuse the live result from step 4. Only if that check was skipped or unavailable and a
   later authorized download needs it, feature-detect RunpodDirect once with the complete
   reviewed list. If the opening request explicitly includes downloading, show a short
   plain-language plan with model name, official source, size when known, and destination;
   keep raw URLs and hashes internal unless requested or a decision depends on them. Then
   proceed without asking again unless a new ambiguity, gate, license, cost/storage, or
   destination choice appears. If downloading was not
   requested, stop after the read-only result and let the UI consume the repaired metadata;
   do not call `POST /server_download/start`. Poll authorized downloads for a bounded period, surface
   failure, and verify integrity afterward; never retry indefinitely.
7. Re-run the live missing-model check only after a download or another Pod/environment
   change; metadata annotation alone cannot change installed files. A successful download
   is not proof that the workflow runs: only when the user asked to run/test end to end,
   queue one controlled smoke test and report missing nodes, runtime errors, or remaining
   dependencies.

## Invariants

- Match the metadata `name` byte-for-byte with the filename selected by the loader.
- Do not flatten a selection such as `subfolder/model.safetensors` to its basename;
  report it as requiring a placement decision because RunpodDirect's current download
  contract accepts a simple filename.
- Treat `.safetensors`, `.sft`, `.ckpt`, `.pth`, and `.pt` as the current RunpodDirect
  scanner contract. Report other model formats for a separately verified placement path.
- Use a directory key returned by the live ComfyUI/RunpodDirect instance; do not invent
  paths or convert a key such as `diffusion_models` into an arbitrary filesystem path.
- For metadata added during a repair, prefer a pinned repository revision plus SHA-256.
  `main`, a search-result URL, a model card, or an HTML page is not an immutable artifact
  identity. Do not use this preference as a reason to rewrite otherwise complete existing
  metadata unless verification/hardening was requested or a live failure exposed a problem.
- Never auto-apply a fuzzy match. Filename similarity, popularity, or model family alone
  cannot distinguish quantizations, encodings, finetunes, or renamed uploads.
- Do not put access tokens in workflow JSON, manifests, command arguments, logs, or chat.
- For metadata repair, validate the exact pinned trusted-host URL and hash without chasing
  delivery-CDN redirects. At the download boundary, validate every outbound redirect as
  described in [reference/runpoddirect.md](reference/runpoddirect.md); the local route
  accepting a URL does not make it trustworthy. Expected provider delivery hops do not
  require another question when they remain content-bound to the approved SHA-256 and no
  credential crosses hosts.
- Installing a custom node, restarting ComfyUI, accepting a license, and queueing a
  prompt are separate mutations. This skill never edits the original workflow. A
  download is covered only when the user's request includes it and the reviewed plan
  introduces no new material decision; otherwise obtain the authorization that action
  needs.
