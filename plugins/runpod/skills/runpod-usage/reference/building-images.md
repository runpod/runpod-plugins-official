# Building container images for Runpod

Shared design principles for image authoring. For a complete project use
[runpod-build-template](../../runpod-build-template/SKILL.md); for CLI login/build/push
use [companion-clis Docker](../../companion-clis/reference/docker.md). Choose the
application contract before selecting its base, storage and startup.

## Choose a compatible base

Prefer an official Runpod image when it supplies the required framework/CUDA stack.
Otherwise prefer pinned Ubuntu with an explicit, compatible runtime/dependency plan.
Preserve a suitable existing base when changing it would add risk without benefit;
small CPU examples may use a language runtime base. Do not install CUDA or PyTorch
for an app that does not need them.

Inspect the selected base's Python, framework, CUDA runtime/toolkit and startup hooks.
Check application/native-extension requirements and target GPU/driver compatibility;
an official image does not guarantee every combination works. The CUDA version shown
by `nvidia-smi` alone does not identify the application's installed toolkit/framework.
Run a representative GPU operation before claiming compatibility.

Record an exact published tag and resolved digest, source revision, dependency locks
or constraints and model revision. Tags can move; a pinned base alone does not pin
later downloads. Build for the target platform (Runpod's x86 Linux examples use
`--platform=linux/amd64`); an ARM laptop's default image can be wrong for the target.

## Layer for reuse

Order stable base/system/framework dependencies before application dependencies and
changing source. Copy dependency manifests before application code. Extending the
same published dependency image preserves its layers; independently installing the
same PyTorch version does not guarantee identical layers.

Declare frequently changing build arguments near their first use. In-scope `ARG`
values affect later `RUN` cache keys even when the command does not reference them;
declaring an app version before an unrelated apt/CUDA install can force that install
to rerun. Verify cache behavior separately from final layer identity and pull time.

Host-cached layers can avoid transfer, but residency on every machine is not promised.
BuildKit's build cache and the deployment host's image cache are different. A small
code-only change should preserve heavy layer identities: compare the resulting images.
Separate transfer size, unpacked disk and startup work when measuring an improvement.

- Exclude secrets, local environments, datasets and caches with `.dockerignore`, while
  preserving required source/build inputs.
- Use `apt-get update` and installation in one layer, `--no-install-recommends` where
  appropriate, and clean package lists in that same layer.
- Use either deliberate BuildKit package caches or avoid retaining installer caches;
  deleting large files in a later layer does not remove their earlier layer bytes.
- Use multi-stage builds when build tools can be removed without losing runtime libraries.
- Use supported build secrets for private dependencies, runtime secrets for execution;
  neither secrets in `ARG` nor credentials copied then deleted are safe image storage.
- Inspect dependency resolution so app extensions do not silently replace the base's
  framework with an incompatible or duplicate stack.

[Docker build guidance](https://docs.docker.com/build/building/best-practices/) and
[layer sharing](https://docs.docker.com/engine/storage/drivers/) explain these mechanics.

## Match startup to the target

| Target | Contract |
| --- | --- |
| Pod | Promised app, development environment or batch command; SSH/Jupyter only when required. |
| Queue Serverless | SDK worker running the real job handler. |
| Load-balanced Serverless | HTTP application with the currently required health/readiness contract. |

For a Pod that promises SSH/Jupyter, preserve the selected base's supported startup
hooks. Some Runpod bases provide `/start.sh` and pre/post hooks; inspect that exact
version rather than assuming every base does. Overriding its entrypoint can disable
those services. Application-only Pods may intentionally use their own command.

For one foreground app, prefer an exec-form `CMD` or a startup script ending in
`exec`. If several services are required, use deliberate supervision and observable
readiness/failure propagation. Do not background `/start.sh`, wait a fixed number of
seconds and infer that initialization succeeded. Hook ordering, whether a hook blocks,
and signal handling must be verified on the chosen base.

From Ubuntu, install/configure SSH only if the requested interface needs it; validate
key handling and access, rather than copying an unrelated template's services. The
historically tested [Pod example](../../runpod/golden-paths/22-minimal-pod-image/README.md)
shows one SSH-enabled contract, not a mandatory Pod layout.

## Image versus persistent storage

Keep stable runtimes and many small immutable files in image layers outside mount
points, using the base's environment or an intentional path such as `/opt/venv`.
Mounts can hide baked files. Inspect actual mounted storage: `/workspace` on a Pod or
`/runpod-volume` on Serverless is a path, not proof of a storage tier or lifecycle.
The [bake/mount experiment](../../runpod/golden-paths/25-bake-vs-mount/README.md) records
one specific deployment's filesystem observations.

Persist user outputs, configuration, models, datasets and editable source as needed.
Avoid copying a whole PyTorch/Python environment to a volume on each startup. An
editable Pod may reuse image packages with a compatible small persistent environment;
`--system-site-packages` is optional and requires ABI/version/shadowing checks.
Immutable apps need no persistent environment or migration framework.

Choose model placement explicitly: image, supported provider cache, persistent volume,
or controlled download. Consider revision, authorization, redistribution permission,
capacity, cold startup and reuse. For downloads handle incomplete files and integrity;
coordinate concurrent writers on shared storage. Namespace incompatible mutable
versions, stage atomic replacement on the same filesystem, and preserve versions in
use. Do not delete user workspace data to repair a mismatch.

## Verify the workload

Check source/configuration first, build and run the actual entrypoint where possible,
then validate through the intended Runpod interface when authorized. A successful build
or healthy process does not establish useful output. Record unavailable GPU, cache,
cloud and timing evidence as unverified.

Use the [authoring variants](../../runpod/golden-paths/26-template-project/README.md)
and [verification protocol](../../runpod-build-template/reference/verification.md) for
fresh/reused storage, restart, repeated requests, likely failures and comparable
measurements. Existing minimal contracts: [Pod](../../runpod/golden-paths/22-minimal-pod-image/README.md),
[queue](../../runpod/golden-paths/23-minimal-queue-image/README.md),
[load balancing](../../runpod/golden-paths/14-load-balancing-endpoint.md).
