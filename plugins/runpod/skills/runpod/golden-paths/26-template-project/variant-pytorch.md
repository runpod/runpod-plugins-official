---
lanes: [docker]
mcp: none
concepts: [container-image, pod, pod-volume-disk]
---

# Variant — heavy layers and retained editable Pod state

## Goal · Status · Lane(s)

Demonstrate that a code change can reuse a compatible PyTorch image without copying
its runtime into `/workspace`. **GPU, image-layer and Runpod checks unverified until
executed.** Lane: runpod-build-template → selected builder → infra lane if requested.

## When to use

An application has a compatible heavy base but startup needlessly reinstalls or copies
it. This is a diagnostic fixture, not a complete ML application or a universal editable
environment design. Validate the user's representative workload separately.

## Prerequisites

Choose a currently available official Runpod PyTorch tag/digest compatible with the
target app/GPU. Inspect its actual Python and startup behavior. The
[fixture Dockerfile](template/pytorch/Dockerfile) deliberately requires `BASE_IMAGE`;
it must not silently choose an arbitrary CUDA line. Build context is `template/pytorch`.

## Walkthrough

1. Build a baseline with the chosen immutable base identity:
   `docker build --platform linux/amd64 --build-arg BASE_IMAGE=<verified-image> -t template-probe:v1 .`
2. Create a task-owned temporary workspace containing a sentinel user file. Run
   `verify.py` with a mount at `/workspace` and a new output path. CUDA is the default;
   an explicit CPU test establishes only CPU behavior. Do not treat a missing GPU as a pass.
3. For the editable-source case, seed **only** `verify.py` into `/workspace/project`
   when it is absent. Run that editable source using the image's interpreter. Change
   a harmless print/comment in the persisted copy, restart, and confirm it remains.
   Keep all PyTorch packages in the image; there is no environment synchronization.
4. Make a code-only change to the image fixture and build `v2` with the same base.
   Compare `docker image inspect` `RootFS.Layers` for v1/v2: the base/framework layers
   should remain identical. Record evidence rather than promising a cached host pull.
5. Run the new image with the same retained workspace and a distinct result filename.
   Verify the sentinel and editable source are unchanged and `torch_path` is outside
   `/workspace`. The fixture refuses to overwrite an existing result.

The probe's matrix multiplication checks real torch execution and emits its version,
package path, selected device and result. It does not measure a user's inference/training
quality or performance. Test native extensions and the real model separately.

## Verify

Check matrix result, device, runtime path, retained file contents and layer identities.
Try an unavailable GPU and a pre-existing output: both should fail clearly without
rewriting user files. Record fresh/reused storage, image identity and relevant timings;
the first run alone does not prove cold-cache behavior.

## Gotchas

The probe is a batch Pod contract and exits after success; it does not promise SSH or
Jupyter. Its default result path can be used once; restart with a **new** `--output`
path. An interrupted write is not a completed result: accept it only after successful
process exit, and preserve it for diagnosis. This is a probe, not restart-safe app
initialization. Preserve base services only for an app that needs them. Persistent source is
optional, and a compatible persistent venv is not required merely to edit Python code.
For concurrent shared state use workload-appropriate locking/versioning; never update
a runtime used by other workers in place.

## Cost & cleanup

Local GPU/Runpod tests require a chosen budget. Preserve results; remove only this
test's containers, image tags and temporary workspace. Do not prune the shared base.

## Skill gaps

Actual compatible base selection, GPU run, layer comparison, shared-filesystem behavior
and live platform acceptance must be recorded by the executor; no measured result is
claimed here.
