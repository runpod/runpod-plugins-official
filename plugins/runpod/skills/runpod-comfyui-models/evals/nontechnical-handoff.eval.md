# Hand a repaired workflow to a non-technical ComfyUI user

## Prompt

I do not really understand models or metadata. This old ComfyUI workflow says things are
missing. Please fix it and tell me what to do.

## Expected behavior

The agent performs the technical work without asking the user to identify models, extract
PNG metadata, run commands, understand hashes, or edit JSON. For a recoverable workflow,
it creates exactly one repaired JSON and leads with its full absolute path.

The handoff says whether the workflow is ready or how many models still need attention,
tells the user to drag the JSON into ComfyUI, and explains automatic-download availability
in one plain sentence. It may name affected model files, but it does not show manifests,
requirement IDs, directory keys, revision hashes, API routes, command logs, or long source
URLs unless the user asks for technical details.

## Assertions

- Uses `Ready to import` or `needs attention` rather than unexplained internal confidence
  labels, and does not imply the workflow has already run.
- Gives one direct next action: drag the JSON into ComfyUI.
- Explains RunpodDirect in plain language and does not imply metadata alone downloads files.
- Does not ask the user to run shell/API commands or edit metadata manually.
- Keeps the default handoff short, with technical details only on request.
- (handoff-contract assertions owned by always-output-workflow.eval.md)
