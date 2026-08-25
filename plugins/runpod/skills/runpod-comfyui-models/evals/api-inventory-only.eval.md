# Inventory API prompt JSON without inventing UI metadata

## Prompt

This is the API-format prompt I send to `/prompt`. Its `UNETLoader` input references
`missing.safetensors`. Add the normal ComfyUI model metadata so RunpodDirect can use it.

## Expected behavior

The agent inventories the named API input and can resolve an exact artifact into an
internal temporary review plan or approved download plan. It explains that portable
`properties.models` metadata belongs to UI-format workflow JSON and asks for the
original UI workflow before annotation. It does not insert frontend-only fields into
the API prompt and claim that RunpodDirect will consume them.

## Assertions

- Inventories the API-format loader and preserves its input unchanged.
- May resolve and report the artifact independently of annotation.
- Does not run the metadata-application script on API-only JSON.
- Requests UI workflow JSON when portable workflow repair is required.
- Does not claim metadata repair or end-to-end success from a nonstandard API edit.
- Does not present the temporary review plan as a repaired-file deliverable.
- Leaves no final repaired JSON for API-only input.
- (handoff-contract assertions owned by always-output-workflow.eval.md)
