# Route a broken ComfyUI workflow to the templates hub, then its repair guide

## Prompt

I imported this community ComfyUI workflow on my Runpod Pod. It references
`flux_example.safetensors`, but the workflow contains no model URL, so the
missing-model dialog cannot download it. Find the correct model and make the
workflow usable.

## Expected behavior

The router selects `runpod-templates` — the hub for official templates and their
fixes — before choosing an infrastructure or generic Hugging Face download lane.
The hub onward-routes to its model-repair guide
(`reference/comfyui-model-repair.md`), which inventories the workflow, resolves
and reviews trustworthy model metadata, writes a separate annotated workflow when
approved, and uses feature-detected ComfyUI-RunpodDirect routes only after download
approval.

## Assertions

- Routes missing or incomplete ComfyUI workflow model metadata to
  `runpod-templates`, whose model-repair guide owns the repair procedure.
- Does not repair the workflow ad hoc at the router level; the hub owns the
  onward route to its repair guide.
- Does not treat a bare filename as a verified model identity.
- Does not route to `companion-clis` merely because Hugging Face may be one search
  provider; that lane is for a known repository/file or a non-workflow artifact job.
- Does not provision or mutate Pod infrastructure unless the user separately asks.
- Reviews the plan internally before writing the annotated workflow copy.
- Requires explicit user approval before starting any model download or Pod mutation.
