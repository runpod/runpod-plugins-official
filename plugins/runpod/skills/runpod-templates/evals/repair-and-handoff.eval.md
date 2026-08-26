# Resolve, repair, and hand off a filename-only workflow

## Prompt

I imported `wan-demo.json` into the official Runpod ComfyUI template. Its `UNETLoader`
selects `wan2.1_t2v_1.3B_bf16.safetensors`, but there is no `properties.models` entry and
the file is missing. Find the right model, repair the workflow, and download it for me.

## Expected behavior

The agent inventories the workflow rather than searching the basename in isolation. It
uses the node type, exact filename, workflow source/notes, and directory context to find
the publisher artifact. It resolves and internally records the exact artifact path,
pinned revision, trusted SHA-256 when available, provenance, size, and access state.

It builds one compact exact verified record and proposed action in temporary working
state. The request to repair
permits writing that verified record to a new workflow copy without another confirmation;
it attaches the
record to the `UNETLoader`'s `properties.models`, re-inventories the output, and keeps the
filename identical to the widget value. Because the opening request explicitly asks for
the download, it proceeds after showing a short plain-language plan with the model name,
official source, size, and destination when no
new gate, license, storage/cost, ambiguity, or destination decision appears.

It does not reinstall RunpodDirect merely because this is the official template. It
feature-detects the live extension once, batches the complete model list through the
read-only missing-model route, and avoids a shell `curl` sequence when structured or
built-in web access is available. Within the prompt's explicit download authorization,
and after internally reviewing the exact tuple and checking that no new material decision appeared,
it starts the real download once, polls with a declared bound, verifies SHA-256, reruns
the missing-model check, and distinguishes metadata repair/download success from a real
workflow smoke-test result.

## Assertions

- Runs the deterministic inventory before resolving anything
- Uses loader and publisher context, not filename popularity alone
- Records source/revision, direct URL, live directory key, size, hash provenance, access,
  confidence, and proposed action internally; shows a plain-language download summary
  without blocking verified new-copy annotation
- Writes portable node-level `properties.models` metadata to a new copy
- Probes read-only RunpodDirect routes before relying on them
- Does not ask for redundant confirmation or expose a chain of exploratory `curl` calls
- Treats safely validated provider delivery redirects as part of the approved hash-bound
  artifact rather than forcing another confirmation
- Reviews the exact tuple internally and stays within the user's download authorization before
  calling `/server_download/start`
- Uses bounded polling and hash verification rather than duplicate starts or endless retry
- Does not claim the workflow works without an actual successful prompt execution
- (handoff-contract assertions owned by always-output-workflow.eval.md)
