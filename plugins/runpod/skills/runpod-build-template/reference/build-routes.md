---
concepts: [container-image, endpoint-build, registry-credential]
---

# Pick a route the user can use

Check prerequisites for the next operation, not every possible tool. File generation
can finish without a Docker daemon, local GPU, registry account, or Runpod key.

| Route | Evidence to check | Fallback |
| --- | --- | --- |
| Local Docker/buildx → registry | CLI and daemon/context, Linux builder, target architecture, free disk, registry push permission; target pull credentials separately | Diagnose setup or use an existing suitable remote builder. |
| Runpod GitHub builder | Serverless target, repository/App access, Dockerfile/context and [current limits](github-integration.md) | If weights dominate, assess [model delivery](model-delivery.md); use a verified external builder/registry when the build still does not fit. |
| Existing CI/remote builder → registry | Available builder, resource limits, secret support, cost, registry access, resulting image architecture | Adapt existing CI before creating a new pipeline. |
| Files plus exact continuation | Required human setup unavailable, or files-only request | Complete independent checks and label build/runtime unverified. |

Explain the selected route in one sentence. Teach a beginner the immediate distinction:
the Dockerfile is the recipe, the image is the built artifact, the registry stores it,
and Runpod starts containers from it. A GitHub URL can be ordinary source input even
when the managed GitHub builder is unsuitable.

For local checks, distinguish `docker --version` (CLI present) from `docker info`
(reachable engine); inspect the active context before changing it. Then inspect
`docker buildx ls` and available space. A stopped engine needs starting, not another
installation. A remote context may use different filesystems/credentials. A running
Runpod Pod is not automatically capable of building Docker images.

On Windows, identify native PowerShell versus WSL and the Docker engine; use commands
and paths for that shell. Docker Desktop/WSL installation is conditional on choosing
local builds: follow its current requirements via [Docker setup](../../companion-clis/reference/docker-setup.md).
On ARM laptops, select the deployment architecture explicitly; CPU emulation is not
GPU validation. Most CUDA compilation can occur without a GPU, but app-specific build
hooks may probe devices: verify before rejecting or promising a builder.

## Credentials and human steps

Source checkout, private build dependency/model access, registry push, Runpod image
pull, and runtime model/API access are separate credentials. A successful push does
not prove Runpod can pull a private image. Use supported build-secret mechanisms;
runtime env does not authenticate an earlier Docker `RUN` instruction. Never put
tokens in image layers, build arguments, committed examples, or diagnostic output.

For login/MFA, organization App approval, gated-model acceptance, administrator setup
or reboot, give one exact action and the expected success signal. Continue unrelated
authoring while it is pending. Reuse existing authorization instead of prompting at
every step. Missing spend/region/retention choices matter before a billable test, not
before writing the Dockerfile.

For disk/access failures, inspect the failing filesystem/permission. Do not change
global socket permissions or run global prune commands. Scope cleanup to disposable
files/resources created for this task and preserve build outputs and user data.
