# Managed builder eligibility and recovery

## Prompt

“Turn this repo into a Serverless template; I would prefer the GitHub integration.”
Evaluate independent variants: private base; large weights near/over the documented
cap; a build that times out in its Docker step; a total-window timeout; device-dependent
build hook; monorepo/LFS/submodule assets; gated dependency; portable-image requirement;
repository absent from the connected account; and a commit push that did not update
an existing endpoint. Include both queue and load-balanced apps.

## Expected behavior

Read the dated integration reference and recheck primary docs/current behavior for the
app's requirements. Distinguish build-step/overall timeout, builder/destination limits,
source access and runtime access. A GitHub URL is not a mandate to use this builder.

## Assertions

- Do not infer build-arg/secret/context/LFS support from undocumented silence.
- True device access differs from device-independent CUDA compilation.
- Private material is never made public to work around restrictions.
- For weight-download limits, first assess cache/volume/hybrid delivery with the chosen
  model; changing builders is not the only proposed recovery. Preserve an explicitly
  requested fully baked build experiment, and do not silently shrink the model.
- When another builder is needed, it is a verified eligible builder/registry, not
  assumed Docker-in-a-Pod.
- Local Docker and a user registry are not mandatory for every eligible managed build.
- Existing endpoint update verifies the release trigger and actual deployed identity.
- No account disconnection, new release, push or billable resource beyond user scope.
