---
concepts: [endpoint-build, endpoint-release, container-image, model-store]
---

# Managed GitHub builds for Serverless

Checked against [Runpod's GitHub integration guide](https://docs.runpod.io/serverless/workers/github-integration)
on **2026-10-10**. Recheck the live guide/UI before relying on a limit or deployment
trigger. These are constraints of this managed route, not universal Docker limits.

| Documented behavior | Decision |
| --- | --- |
| Queue and Load Balancer types are selectable | Eligible for either Serverless contract; this is not a general Pod builder. |
| Connected GitHub account/App controls repository access; branch and Dockerfile path are selectable | Verify repo/org access. Merely having an upstream URL does not make it importable. Record the revision being built. |
| Docker build step: 30 minutes; total clone/build/upload/test: 160 minutes | Diagnose the actual phase; assess model delivery for large weight downloads, and another builder for work that still cannot fit. |
| Image limit: 80 GB | Check large dependencies/weights early. The guide does not define the measurement precisely; verify near-boundary images. |
| Private base images unsupported | Use a suitable authorized public base or external builder/registry. Never publish private material as a workaround. |
| Builds requiring GPU access unsupported | Use compatible prebuilt artifacts or device-independent compilation if valid; otherwise verify an external GPU builder. CUDA compilation does not inherently require a GPU. |
| Built images cannot be pulled/executed on other platforms | Use an external registry route if the user needs a portable image or local testing of that exact artifact. Source remains portable. |
| Existing integration updates require a new GitHub release, not only a commit push | Verify the deployed release/image after an update. Do not tell the user that pushing a commit completed deployment. |
| One GitHub connection per Runpod account; connections are described as non-shared | Check team/organization ownership without disconnecting an existing account. |

Check Dockerfile path **and build context** independently. Do not infer support for
build args, BuildKit secrets, private package credentials, LFS, submodules, or unusual
monorepos from silence. Verify the specific requirement before choosing this route;
use a verified alternative when unresolved. Do not copy illustrative CI YAML without
checking its current actions, permissions, credentials, and tests.

For model-heavy builds, assess [model delivery](model-delivery.md) before the first
build and again after a download-driven timeout. Moving eligible weights to Model Store
or a populated volume can preserve the chosen model and GitHub route; implement the
loader and endpoint/storage settings together. This does not solve an unrelated compile
timeout. Do not recommend a smaller model merely to fit the builder without the user's
agreement. If the user explicitly wants to test a fully baked image against the limit,
preserve that experiment and label the result; do not silently change what is being tested.

An external builder solves only that builder's restrictions. Recheck destination
image/runtime/disk limits and private pull access separately. For updates, retain
the prior source/release/configuration and establish a supported rollback route;
the managed image export restriction may prevent a digest-based local rollback.

Source preparation does not require GitHub publishing. Forking/pushing a repo,
installing the GitHub App, creating a release, or changing an endpoint follows the
user's existing authorization and any human-only account approval. If blocked,
deliver the completed project plus the exact remaining action and validation status.
