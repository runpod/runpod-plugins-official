# Return one repaired workflow, not a bundle of working files

## Prompt

Repair the missing model metadata in this original ComfyUI output PNG and give me the
result I should import.

## Expected behavior

The agent preserves the PNG and creates a unique task-specific temporary directory for
the extracted workflow, inventory data, and resolution manifest. After applying verified
metadata, it validates the candidate before atomically publishing
`<workflow-stem>.repaired.json` outside that directory, then deletes only the exact
temporary directory it created.

The final response contains exactly one full absolute file path/link: the repaired JSON.
It may include a short plain-language model summary and automatic-download status in chat,
but it does not list,
attach, or link the extracted/normalized workflow, inventory, manifest, or temporary
directory. If no metadata change was needed, it still produces the one final UI workflow
JSON, states that no records were added, and leaves the source untouched. If repair cannot produce a valid UI workflow, it reports the blocker
without presenting an intermediate artifact as a result.

## Assertions

- Leaves one new persistent file after a successful repair.
- Preserves the supplied source and never edits or overwrites it.
- Keeps all non-deliverable files inside one verified task-specific temporary directory.
- Cleans only that exact agent-created temporary directory after successful validation.
- Cleans that directory on ambiguity, gating, invalid/API-only input, cancellation, tool
  failure, or validation failure too.
- Has exactly one file path/link in the final response.
- Shows the final JSON's full absolute path.
- Does not expose `.normalized.json`, inventory, or manifest files as deliverables.
- If a metadata candidate fails validation, omits it and publishes a partial/unchanged
  workflow; leaves no final JSON only when no UI workflow is recoverable.
- Summarizes requested audit evidence in chat instead of generating another persistent
  artifact.
