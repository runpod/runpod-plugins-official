# Explicit authoring versus deployment

## Prompt

Evaluate separately: (a) “Turn this ComfyUI repository into my own documented Pod
template project.” (b) “Run official ComfyUI on a Pod.” (c) “My existing template takes
minutes copying its venv into /workspace; optimize these source files.” (d) “Build and
push this existing Dockerfile.” (e) “Use Flash to deploy my decorated Python function.”

## Expected behavior

Authoring/improvement uses runpod-build-template and golden path 26. Ordinary official
template discovery uses runpod-templates; single build/push mechanics use companion-clis;
explicit Flash stays there. Existing examples inform the requested deliverable without
replacing it. Improve mode preserves a baseline and names an optimization objective.

## Assertions

- (a)/(c) deliver app-specific source projects, not just a prebuilt deployment or advice.
- (a) does not default to a dual-mode image or a queue handler.
- (b)/(d)/(e) do not unnecessarily enter a full template-authoring process.
- Files-only requests do not demand Runpod auth or publish/provision resources.
