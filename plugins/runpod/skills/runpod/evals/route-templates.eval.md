# Route "run X on a pod" to the templates lane when an official template covers it

## Prompt

I want ComfyUI running on a Runpod pod with a web UI I can open in my browser.
Set it up for me.

## Expected behavior

The router recognizes "run a common workload on a pod" as a `runpod-templates`
shape: an official prebuilt template already covers ComfyUI, so the agent deploys
the template — via the matching golden path — instead of building a custom image.
Fixing an already-running template pod also lands in `runpod-templates` first,
which routes onward.

## Assertions

- Routes "run ComfyUI on a pod" to `runpod-templates` and its ComfyUI reference /
  golden path 02 variant B, not to building a custom image via docker/companion-clis.
- Distinguishes pod templates from Hub serverless repos: does not answer the task
  with the `worker-comfyui` Hub listing when the user asked for a pod.
- A "my pod is Running but the URL 502s" task on an official template also routes
  to `runpod-templates` first (the reference's Readiness section), onward to
  runpod-usage gotchas when the cause is template-independent.
- An imported ComfyUI workflow with missing model metadata is handed to the
  templates skill's model-repair guide, not repaired ad hoc.
