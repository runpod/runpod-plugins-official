# Ask for the artifact once, then return a RunpodDirect-ready workflow

## Prompt A — no artifact yet

My imported ComfyUI workflow is broken and it says models are missing. Can you fix it?

## Expected behavior A

The agent asks the user to attach either the workflow JSON or the original ComfyUI output
PNG. It does not begin by requesting model names, node screenshots, Pod credentials,
browser access, or hand-written metadata. It explains briefly, only if needed, that an
original PNG can contain the workflow while a screenshot or re-encoded image may not.

## Prompt B — artifact attached

Here is the workflow JSON/output PNG.

## Expected behavior B

The agent asks no further intake question. It preserves the source, extracts embedded UI
workflow JSON when needed, inventories model references, resolves exact verified records,
and returns a new metadata-enriched workflow JSON that ComfyUI-RunpodDirect can consume.
Live Pod checking and downloading occur only when available and within the request; they
are not prerequisites for delivering the portable repaired file.

## Assertions

- With no artifact, asks exactly one concise question offering JSON or original PNG.
- Does not ask the user to identify models or reconstruct metadata manually.
- With an artifact, asks zero routine intake questions and performs the repair flow.
- Requests another artifact only when the supplied image lacks a repairable embedded UI
  workflow, and states that concrete blocker.
- (handoff-contract assertions owned by always-output-workflow.eval.md)
