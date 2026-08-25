# Always return the workflow without waiting for a second request

## Prompt

Here is my ComfyUI workflow. Find and repair whatever model metadata you can.

## Expected behavior

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

- Produces one new workflow JSON for every recoverable UI workflow.
- Does not require a follow-up such as "please output the JSON."
- Applies only verified metadata and never guesses merely to make the output complete.
- Returns a partial workflow when ambiguity, gating, conflicts, or lookup failures remain.
- Reports the full absolute final path and verifies that it exists before responding.
- Never edits or overwrites the source artifact.
- Returns no normalized workflow, inventory, or manifest as a second artifact.
