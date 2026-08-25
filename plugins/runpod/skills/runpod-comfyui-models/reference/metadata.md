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

Use the runtime directory **key**, not an absolute path, and never invent a key or
convert one such as `diffusion_models` into an arbitrary filesystem path. As of
2026-08, RunpodDirect requests use keys such as `checkpoints`, `diffusion_models`,
`vae`, or `text_encoders`, while some documentation displays them as
`models/checkpoints` paths. Confirm all accepted keys with one
`GET /server_download/folder_paths` call when a live instance is available.

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

The helper scripts are stdlib-only and need python3 >= 3.9.

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
   If the selected value contains a subfolder, do not flatten it to a basename: as of
   2026-08 RunpodDirect's download contract accepts a simple filename (upstream
   RunpodDirect ships no version tags to pin against), so report that requirement for
   manual placement instead of generating misleading metadata.
6. Reject URL fragments, credentials in URLs, local paths, path-traversal filenames, and
   metadata whose directory is not accepted by the live instance. For metadata added
   during a repair, validate the exact pinned trusted-host URL and hash without chasing
   delivery-CDN redirects; outbound redirect validation happens at the download boundary
   (see [runpoddirect.md](runpoddirect.md)).
7. If an existing record conflicts with the approved record, surface the diff. The helper
   refuses the replacement until that manifest item explicitly sets
   `"replace_existing": true`; do not set the flag merely because the newly found source
   is more popular. When confirmation is still needed, omit the replacement, publish the
   partial workflow first, and ask in the same handoff.
8. An existing record that already matches the resolved canonical fields is kept in
   place verbatim — unknown fields such as `note` or `size` are preserved — and is not
   rewritten merely to pin a revision or add a hash. Harden existing complete metadata
   only when the user asks for verification/hardening or a live failure exposes a
   problem.
9. The apply helper never silently preserves an unsafe pre-existing entry: without
   `--allow-unresolved` it refuses to publish (exit 2); with `--allow-unresolved` it
   removes the unsafe entry from the published workflow, reports it in the unresolved
   output, and preserves the loader selection itself. It likewise removes known invalid
   metadata that has no approved replacement while preserving the selection.
10. Re-inventory the candidate before publishing the final path. The apply helper
    performs this check in memory and refuses invalid or API-only output. In its
    explicit `--allow-unresolved` handoff mode, it publishes a valid UI workflow with
    unresolved selections preserved and labels it `partial`; otherwise unresolved output
    is refused. `complete` means the approved metadata is structurally present and
    correctly associated; it does not certify that the workflow runs. Runtime and
    artifact verification are separate steps.
11. For metadata added during a repair, prefer a pinned repository revision plus
    SHA-256. `main`, a search-result URL, a model card, or an HTML page is not an
    immutable artifact identity.
12. Treat `.safetensors`, `.sft`, `.ckpt`, `.pth`, and `.pt` as the supported model
    formats: as of 2026-08 that is the RunpodDirect scanner contract (upstream
    RunpodDirect ships no version tags to pin against). Report other model formats for
    a separately verified placement path.

Inventory issue codes: `unsafe_url` marks a pre-existing metadata entry whose URL is
unsafe — a non-https scheme, a host that is not exactly `huggingface.co` or
`civitai.com` after normalization, an IP-literal host, userinfo or a fragment, or
credential-shaped query keys. An entry flagged `unsafe_url` makes `metadata_status`
`partial`, never `complete`.

An inventory summary of `complete_metadata` means structurally complete metadata, not
that the live folder exists, the bytes match, access is granted, or the workflow executed.

## What to deliver

The workflow file is a mandatory deliverable: the task is not complete until exactly one
new persistent `<workflow-stem>.repaired.json` (or a collision-safe numbered variant)
exists — whether records were added, the workflow was already complete, or some
requirements remain unresolved.

For a recoverable UI workflow, use this order and keep it brief:

1. `Fixed workflow: <full-absolute-path>` as the only file reference; make that same
   path clickable when supported and show no other artifact path.
2. `Status: Ready to import` when all supported model references are covered, or
   `Status: Workflow file created — <count> model(s) still need attention` when partial.
   Never imply everything is fixed when some model information remains missing.
3. `Next: Drag this JSON into ComfyUI.`
4. Exactly one automatic-download status, followed by one plain sentence explaining what
   it means: `Automatic downloads: Ready`, `Automatic downloads: Not checked on your
   ComfyUI`, or `Automatic downloads: Not available — RunpodDirect was not detected`.
5. State plainly whether model files were downloaded and whether the workflow was run.

The three automatic-download states:

- **Confirmed active** → `Automatic downloads: Ready`. Tell the user to drag the
  actionable JSON into ComfyUI; the RunpodDirect Missing Models window should appear. If
  it does not, refresh ComfyUI and import the JSON again.
- **Not checked** → `Automatic downloads: Not checked on your ComfyUI`. Say that
  automatic direct-to-Pod downloading requires
  [ComfyUI-RunpodDirect](https://github.com/MadiatorLabs/ComfyUI-RunpodDirect) and that
  its installation/load status was not verified. Do not promise that the Missing Models
  window will appear.
- **Unavailable or not detected** → `Automatic downloads: Not available — RunpodDirect
  was not detected`. Say the workflow file is ready, but automatic downloading requires
  RunpodDirect to be installed, enabled, and loaded. Offer setup help; do not install,
  update, or restart ComfyUI without authorization.

Metadata compatibility is not extension availability: without an active RunpodDirect
installation, the enriched workflow remains portable but does not create the extension's
Missing Models UI or perform direct-to-Pod downloads.

After a repair, summarize how many models received download information and, when the
list is short, name them. When the workflow already had complete metadata, say the final
copy is unchanged and no records were added. If attention is needed, list the affected
model filenames and the human decision in plain language after the file path. Show the
technical `Model | Directory | Source URL | SHA-256` table only when the user asks for
technical details, provenance, or an audit. A lookup failure, ambiguity, gate, conflict,
or rejected metadata record still requires a partial/unchanged final workflow JSON;
leave no final output only when no UI workflow can be recovered or every writable
collision-safe destination fails. Do not say "the workflow works" after a JSON patch
alone: use "metadata repaired" until the artifacts have been verified and an actual
workflow execution succeeds.

Assume a non-technical audience by default. Translate internal states instead of exposing
terms such as manifest, requirement ID, immutable revision, directory key, artifact
tuple, UI-format detection, `verified`, `high`, `ambiguous`, `unresolved`, or
re-inventory — unless a decision depends on them, and then with a short translation. Do
not include helper commands, API routes, shell transcripts, long URLs, or hashes unless
the user requests technical evidence. Do not ask the user to run extraction, `curl`, API,
or metadata-editing commands. Keep safety checks rigorous internally; offer deeper
technical evidence only when requested.

Preserve the original artifact without editing or overwriting it. Put extracted or
normalized JSON, inventories, and the review manifest only in one uniquely named task
directory under the system temporary directory — never beside the source or final file.
After the repaired JSON passes re-inventory, remove that exact agent-created directory;
never remove the source or final file, and never recursively delete an unverified or
broad path. Use finally-style cleanup on every terminal path, including ambiguity,
gating, invalid/API-only input, cancellation, tool errors, and failed validation. Do not
mention, attach, link, or enumerate temporary artifact paths in the final response; the
final repaired JSON's full absolute path is the one path that must be shown. Do not
generate a second persistent audit artifact; summarize requested audit evidence in chat.

For a task that also creates or starts a Pod, first consult the
[worked examples](../../runpod/golden-paths/README.md), then route that infrastructure
work through `runpod-mcp` or `runpodctl`. Return here once ComfyUI is reachable.
