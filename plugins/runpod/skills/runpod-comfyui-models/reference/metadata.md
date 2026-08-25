# Apply ComfyUI model metadata

Use this reference after identity resolution. A request to repair authorizes `verified`
records to be applied to a new copy; a separate confirmation is needed only for a
material choice such as a `high`-confidence candidate or conflict replacement. Never
edit or overwrite the source. Preserve graph behavior and make the repaired workflow
independently useful. A pending confirmation does not delay the mandatory file handoff:
omit that record, publish the partial workflow, and ask after its path in the same response.
Use the current Comfy
[workflow-template specification](https://github.com/Comfy-Org/workflow_templates/blob/main/docs/SPEC.md#model-metadata-format)
and [embedding guide](https://github.com/Comfy-Org/workflow_templates#9--embed-models)
as the authoritative metadata convention.

## UI workflow versus API prompt

Portable model metadata belongs to UI-format workflow JSON. API-format prompt JSON is
useful for inventory because its named inputs make model references easy to locate, but
it has no equivalent portable model-metadata contract. For API-only input, keep any
reviewed resolution plan as temporary working state and ask for the original UI workflow
if annotation is required. Do not hand off the manifest as a substitute, and do not add
`properties.models` to API nodes and claim the prompt was repaired.

## Canonical node record

Attach model metadata to the consuming loader node's `properties.models` array:

```json
{
  "name": "flux1-dev.safetensors",
  "url": "https://huggingface.co/owner/repo/resolve/<commit>/diffusion_models/flux1-dev.safetensors",
  "hash": "<64 lowercase hexadecimal SHA-256 characters>",
  "hash_type": "SHA256",
  "directory": "diffusion_models"
}
```

The portable ComfyUI workflow-template convention is node-level
`properties.models`. RunpodDirect can also read a root `workflow.models` collection, but
do not use that extension as a reason to omit a known node association. A root record is
reasonable only as an additional compatibility/fallback record when the node association
cannot be represented reliably; deduplicate by exact name and URL.

Use the runtime directory **key**, not an absolute path. In particular, current
RunpodDirect requests use keys such as `checkpoints`, `diffusion_models`, `vae`, or
`text_encoders`, while some documentation displays them as `models/checkpoints` paths.
Confirm all accepted keys with one `GET /server_download/folder_paths` call when a live
instance is available.

## Resolution manifest consumed by the script

Start with `workflow_sha256` and `requirement_id` values from
`inventory_workflow_models.py`; do not recalculate or invent identifiers:

```json
{
  "schema_version": 1,
  "workflow_sha256": "<value from inventory>",
  "models": [
    {
      "requirement_id": "<value from inventory>",
      "filename": "flux1-dev.safetensors",
      "directory": "diffusion_models",
      "url": "https://huggingface.co/owner/repo/resolve/<40-character-commit>/diffusion_models/flux1-dev.safetensors",
      "sha256": "<optional 64-character digest>",
      "expected_size": 2389012345,
      "source": {"provider": "huggingface", "repository": "owner/repo", "revision": "<commit>"},
      "license": "<SPDX id, provider value, or unknown>",
      "access": "public",
      "reviewed": true,
      "verified": true,
      "ambiguous": false,
      "replace_existing": false
    }
  ]
}
```

`workflow_sha256` is a canonical semantic fingerprint of the parsed JSON, not the
bytewise SHA-256 of the source file. Whitespace and object-key order therefore do not
invalidate a reviewed manifest, while any data change does.

`reviewed` records that the proposed identity/action was assessed against the evidence
and the user's existing request scope; it does not require a separate conversational
round trip for a verified new-copy repair. `verified` means the record now identifies one
exact artifact through trusted evidence or an explicit user selection among exact
candidates; it does **not** mean the bytes were hash-verified.
Only `sha256` carries that integrity claim. Never set these booleans merely to satisfy the
script. Leave ambiguous/unresolved requirements out and report them. For the mandatory
workflow handoff, use the apply script's explicit `--allow-unresolved` mode so it preserves
those loader selections and reports a `partial` result instead of inventing metadata.

The apply helper validates fields that affect workflow metadata and leaves provenance,
size, license, and access fields in the separate review manifest as audit evidence.
Set `replace_existing` to `true` only after reviewing the reported field-level conflict
for that requirement. Omit it, or leave it `false`, when adding metadata or preserving an
identical existing record.

## Patch rules

1. Always write a new output file. Never edit, replace, or overwrite the supplied JSON or
   PNG. Prefer `<workflow-stem>.repaired.json`; if it already exists, choose a
   collision-safe numbered filename rather than overwriting it.
2. Preserve node IDs, links, widget values, layout, subgraphs, unknown fields, JSON types,
   and existing object-key order. The helper reserializes the workflow with indentation,
   so whitespace and inline-array formatting can change; review semantic changes rather
   than expecting a byte-minimal diff.
3. Attach each record to its identified consuming loader, including loaders in nested
   subgraphs. Requirement identifiers are occurrence-specific: do not attach by filename
   alone when different nodes select same-name but different artifacts.
4. Require `name`, direct `url`, and `directory`. Add `hash` and `hash_type` when a
   trustworthy SHA-256 is available; do not invent a digest or hash algorithm.
5. Keep `name` identical to the selected widget/input filename. A URL whose response is
   renamed by `Content-Disposition` does not justify changing the workflow silently.
   If the selected value contains a subfolder, do not flatten it to a basename; the MVP
   reports that requirement for manual placement instead of generating misleading metadata.
6. Reject URL fragments, credentials in URLs, local paths, path-traversal filenames, and
   metadata whose directory is not accepted by the live instance.
7. If an existing record conflicts with the approved record, surface the diff. The helper
   refuses the replacement until that manifest item explicitly sets
   `"replace_existing": true`; do not set the flag merely because the newly found source
   is more popular. When confirmation is still needed, omit the replacement, publish the
   partial workflow first, and ask in the same handoff. In `--allow-unresolved` mode,
   remove known invalid/unsafe metadata that has no approved replacement while preserving
   the loader selection itself.
8. Re-inventory the candidate before publishing the final path. The apply helper performs
   this check in memory and always refuses invalid or API-only output. In its explicit
   `--allow-unresolved` handoff mode, it publishes a valid UI workflow with unresolved
   selections preserved and labels it `partial`; otherwise unresolved output is refused.
   `complete` means the approved metadata is structurally present and correctly
   associated. Runtime and artifact verification are separate steps.

An inventory summary of `complete_metadata` means structurally complete metadata, not
that the live folder exists, the bytes match, access is granted, or the workflow executed.

## What to deliver

Report:

- exactly one new persistent output named `<workflow-stem>.repaired.json` (or a
  collision-safe numbered variant) for every recoverable UI workflow, whether records
  were added, the workflow was already complete, or some requirements remain unresolved;
- one final file reference in the form `Fixed workflow: <full-absolute-path>`; make that
  same path clickable when supported and show no other artifact path;
- a plain `Status: Ready to import` or
  `Status: Workflow file created — <count> model(s) still need attention` line;
- `Next: Drag this JSON into ComfyUI.`;
- when the workflow already had complete metadata, that the final copy is unchanged and
  no records were added;
- a direct instruction to drag and drop the actionable workflow JSON into ComfyUI;
- exactly one plain-language automatic-download status: `Ready`,
  `Not checked on your ComfyUI`, or
  `Not available — RunpodDirect was not detected`;
- only when RunpodDirect was confirmed active, that its Missing Models window should
  appear and that refreshing ComfyUI/re-importing is a reasonable first retry;
- when RunpodDirect was not checked or not detected, that automatic direct-to-Pod
  downloading requires the
  [ComfyUI-RunpodDirect custom node](https://github.com/MadiatorLabs/ComfyUI-RunpodDirect)
  to be installed, enabled, and loaded; never promise the Missing Models window;
- after a repair, the count of records added and, when reasonably short, their model
  filenames; show the technical `Model | Directory | Source URL | SHA-256` table only
  when the user requests technical details, provenance, or an audit;
- what was fixed and what still needs attention, in plain language;
- model filenames still needing attention and the decision or missing information needed;
- `Status: Ready to import` or the plain-language `needs attention` status; never imply everything
  is fixed when some model information remains missing;
- whether the file was prepared for automatic downloads, models were actually downloaded,
  and/or the workflow was successfully tested, using ordinary language.

Assume a non-technical audience by default. Translate internal states instead of exposing
terms such as manifest, requirement ID, immutable revision, directory key, artifact tuple,
UI-format detection, or re-inventory. Do not include helper commands, API routes, shell
transcripts, long URLs, or hashes unless the user requests technical evidence or must make
a decision that depends on it. Keep safety checks rigorous internally.

Preserve the original artifact without editing or overwriting it. Put
extracted/normalized JSON, inventories, and the
review manifest only in a uniquely named task directory under the system temporary
directory. After the repaired JSON passes re-inventory, remove that exact agent-created
directory; never remove the source or final file, and never recursively delete an
unverified or broad path. Do not mention, attach, link, or enumerate temporary artifact
paths in the final response. The full absolute path to the final repaired JSON is the one
path that must be shown. Use finally-style cleanup on every terminal path, including
ambiguity, gating, invalid/API-only input, cancellation, tool errors, and failed
validation. Do not generate a second persistent audit artifact; summarize requested audit
evidence in chat. A lookup failure, ambiguity, gate, conflict, or rejected metadata record
still requires a partial/unchanged final workflow JSON. Leave no final output only when no
UI workflow can be recovered or every writable collision-safe destination fails.

Metadata compatibility is not extension availability: without an active RunpodDirect
installation, the enriched workflow remains portable but does not create the extension's
Missing Models UI or perform direct-to-Pod downloads. Offer setup help when appropriate,
but do not imply that workflow repair authorized custom-node installation or a restart.

Do not say "the workflow works" after a JSON patch alone. Use "metadata repaired" until
the artifacts have been verified and an actual workflow execution succeeds.
