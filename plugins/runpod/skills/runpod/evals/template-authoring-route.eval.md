# Route explicit template authoring before general deployment

## Prompt

“Create a complete documented template project from this GitHub application. It may
already have a Runpod template, but I need my own Dockerfile and supporting files.”
Then independently: “Run this application using an existing official template.”

## Expected behavior

The first request matches golden path 26 and runpod-build-template, preserving its
source deliverable. The second keeps normal prebuilt discovery/deployment routing.
The same behavior must hold when starting directly in runpod-templates, companion-clis,
runpod-usage or flash rather than first reading the router.

## Assertions

- Explicit authoring is not replaced with prebuilt/Flash or an unrelated dual-mode image.
- File authoring does not require cloud auth, SSH or local Docker.
- A single existing-image build/push operation still routes to companion-clis.
- Only relevant references are loaded; manual eval documentation is not called CI coverage.
