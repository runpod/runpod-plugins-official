# Always return the workflow without waiting for a second request

## Prompt

Here is my ComfyUI workflow. Find and repair whatever model metadata you can.

## Expected behavior

The agent preserves the original artifact and does all non-deliverable work (extracted
or normalized JSON, inventory, resolution manifest) inside one task-specific temporary
directory it created and verified. The repaired JSON is published outside that
directory, and afterwards only that exact agent-created directory is removed — on
success and on any terminal path alike.

Once the agent confirms that the artifact contains a UI workflow, creating a new workflow
JSON becomes mandatory. It resolves and applies every verified record, preserves any
unresolved, ambiguous, gated, or rejected model selection unchanged, and calls the apply
helper with `--allow-unresolved`. It does not stop after presenting findings, a manifest,
or a model table and wait for the user to ask for the actual JSON.

The final response contains exactly one artifact reference in the form
`Fixed workflow: <full-absolute-path>`. It says `Status: Ready to import` or that specific model
files still need attention, and preserves the original input. Internal `complete` or
`partial` labels do not need to be shown to the user.
Only an artifact with no recoverable UI workflow, or failure of every safe writable
destination, may end without a workflow file.

## Assertions

- Produces one new workflow JSON — the single new persistent file — for every
  recoverable UI workflow.
- Does not require a follow-up such as "please output the JSON."
- Applies only verified metadata and never guesses merely to make the output complete;
  if a metadata candidate fails validation, omits it and still publishes the workflow
  with that selection unresolved.
- Returns a partial workflow when ambiguity, gating, conflicts, or lookup failures
  remain.
- Has exactly one file path/link in the final response: the repaired JSON's full
  absolute path, verified to exist before responding.
- Never edits or overwrites the source artifact.
- Keeps every non-deliverable file inside one verified task-specific temporary
  directory and cleans only that exact agent-created directory — after successful
  validation, and also on ambiguity, gating, invalid/API-only input, cancellation, tool
  failure, or validation failure.
- Returns no normalized workflow, inventory, or manifest as a second artifact or
  deliverable; summarizes requested audit evidence in chat instead of generating another
  persistent artifact.
