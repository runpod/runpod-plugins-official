---
lanes: [docker]
mcp: none
concepts: [container-image, pod, pod-volume-disk]
---

# Variant — heavy layers and retained editable Pod state

## Goal · Status · Lane(s)

Demonstrate that a code change can reuse a compatible PyTorch image without copying
its runtime into `/workspace`, while retaining the base's long-lived Pod startup.
**GPU, image-layer and Runpod checks unverified until executed.** Lane:
runpod-build-template → selected builder → infra lane if requested.

## When to use

An application has a compatible heavy base but startup needlessly reinstalls or copies
it. This is a diagnostic fixture, not a complete ML application or a universal editable
environment design. Validate the user's representative workload separately.

## Prerequisites

Choose a currently available official Runpod PyTorch tag/digest compatible with the
target app/GPU. Inspect its actual Python, entrypoint and `/start.sh`: this example
requires a base whose `/start.sh` initializes its services and remains running. The
[fixture Dockerfile](template/pytorch/Dockerfile) deliberately requires `BASE_IMAGE`;
it must not silently choose an arbitrary CUDA line. Build context is `template/pytorch`.
The official [base Dockerfile](https://github.com/runpod/containers/blob/main/official-templates/base/Dockerfile)
and [startup script](https://github.com/runpod/containers/blob/main/container-template/start.sh)
show this pattern; match the source revision to the selected image before relying on it.

## Walkthrough

1. Build a baseline with the chosen immutable base identity:
   `docker build --platform linux/amd64 --build-arg BASE_IMAGE=<verified-image> -t template-probe:v1 .`
2. Create a task-owned temporary workspace containing a sentinel user file. Start the
   image with `/workspace` mounted and its **default command**. For a local NVIDIA
   container runtime, for example:
   `docker run -d --name template-probe --gpus all --mount type=bind,source=<absolute-test-workspace>,target=/workspace template-probe:v1`.
   Confirm the container stays running and the base services you configured are usable.
   Then execute the finite check separately:
   `docker exec template-probe python /opt/template-probe/verify.py --output-dir /workspace/probes`.
   CUDA is the default; an explicit `--device cpu` test establishes only CPU behavior.
   Do not treat a missing GPU as a pass. On Runpod, leave the startup command at the
   image default and run the same Python command from SSH or the terminal.
3. For the editable-source case, seed **only** `verify.py` into `/workspace/project`
   when it is absent. Run that editable source using the image's interpreter. Change
   a harmless print/comment in the persisted copy, restart the same container, and
   confirm it remains. Re-run the probe after restart; each invocation creates a new
   report under `/workspace/probes` without replacing previous results.
   Keep all PyTorch packages in the image; there is no environment synchronization.
4. Make a code-only change to the image fixture and build `v2` with the same base.
   Compare `docker image inspect` `RootFS.Layers` for v1/v2: the base/framework layers
   should remain identical. Record evidence rather than promising a cached host pull.
5. Run the new image with the same retained workspace and re-run the check explicitly.
   Verify the sentinel and editable source are unchanged and `torch_path` is outside
   `/workspace`. For a chosen exact filename use `--output`; it refuses to overwrite
   an existing result. Keep startup at `/start.sh` throughout both versions.

The probe's matrix multiplication checks real torch execution and emits its version,
package path, selected device and result. It does not measure a user's inference/training
quality or performance. Test native extensions and the real model separately.

## Verify

Check matrix result, device, runtime path, retained file contents and layer identities.
Try an unavailable GPU and a pre-existing output: both should fail clearly without
rewriting user files. Record fresh/reused storage, image identity and relevant timings;
the first run alone does not prove cold-cache behavior.

From `template/pytorch`, local regression checks are:

```text
python -B -m unittest -v test_verify
python -B check_lifecycle.py
```

The first uses a torch double to check repeated reports, no-clobbering and failure
handling. The second builds the actual Dockerfile on a small mock base, tests its
foreground HTTP service before/after restarting the same container with the same
volume, checks retained files, and removes its own containers, volumes and image tags.
It does not pull a CUDA image or verify torch, SSH, Jupyter, GPU or Runpod behavior.
Real GPU acceptance still requires the explicit probe and service checks above.

## Gotchas

The image is a long-lived development Pod; no probe or inference runs automatically
at startup. A finite probe used as the default command can cause repeated Pod restarts
while billing continues. Keep the base command and invoke the probe separately;
its exit status signals success/failure without shutting down the Pod. The base owns
SSH/Jupyter startup, so verify its access settings rather than assuming they are enabled.
An interrupted report write is not a completed result: accept it only after successful
probe exit, and preserve it for diagnosis. Persistent source is
optional, and a compatible persistent venv is not required merely to edit Python code.
For concurrent shared state use workload-appropriate locking/versioning; never update
a runtime used by other workers in place.

## Cost & cleanup

Local GPU/Runpod tests require a chosen budget. This Pod remains running after a
probe succeeds or fails, and keeps billing until stopped/terminated. Preserve results,
then stop/remove the local test container or terminate the authorized disposable Runpod
Pod and verify cleanup. Remove only this test's image tags and temporary workspace;
do not prune the shared base.

## Skill gaps

Actual compatible base selection, GPU run, layer comparison, shared-filesystem behavior
and live platform acceptance must be recorded by the executor; no measured result is
claimed here.
