---
lanes: [docker, runpod-mcp, runpodctl, console]
mcp: partial
concepts: [container-image, template, pod, serverless-endpoint, serverless-handler, endpoint-build]
---

# Golden path 26 — author a complete template project

## Goal

Turn source or an application request into a documented Dockerfile, required app files,
and an exact Runpod configuration handoff. Create and improve share the same contract;
improve additionally preserves a baseline and compares the relevant measurements.

## Status

**Spec — not live-verified on Runpod.** The included small CPU workload makes local and
container checks possible; those do not establish GPU/platform behavior. Record actual
checks and limits when executing a variant. No timing or optimization result is asserted.

Local verification on **2026-10-06** used Docker **29.7.2**, Linux **x86_64** in WSL Ubuntu:

| Check | Observed result |
| --- | --- |
| Host Python and both image `test` stages | Two test cases passed: useful adapter output, invalid-input recovery, local HTTP and 20 isolated concurrent requests. |
| HTTP final image command | `/ping`, expected `/analyze` output, invalid → valid request, repeated requests and restart passed. |
| Queue final image / SDK 1.10.1 local-input mode | Expected `words=3`, counts `a=2,b=1` returned; empty text surfaced ValueError and exited nonzero. |
| Runpod Pod/queue/LB, managed GitHub route, GPU/layers/retained workspace | Unverified; no cloud deployment or GPU test performed. |

The queue build encountered one package-download timeout; one unchanged retry succeeded.
That was a transport failure, not evidence of a dependency incompatibility. These local
results validate this CPU fixture only, not the user's future application.

## Lane(s)

[runpod-build-template](../../../runpod-build-template/SKILL.md) → companion-clis for
the selected build/push operation → infra lanes only for authorized deployment.

## When to use / which variant?

| Request | Variant |
| --- | --- |
| Package an app users open on a Pod | [Pod](variant-pod.md) |
| Turn an operation into a submitted job | [Queue Serverless](variant-queue.md) |
| Keep an existing HTTP API on Serverless | [Load-balanced Serverless](variant-load-balanced.md) |
| Reduce heavy dependency copying and preserve an editable Pod workspace | [PyTorch layering and retained storage](variant-pytorch.md) |

The [text-statistics fixture](template/README.md) performs a real deterministic CPU
operation, shared by HTTP and queue adapters. It demonstrates the packaging contract;
it is not evidence that an arbitrary model/application is supported. The PyTorch
fixture is a separate device/layer/storage probe, not a replacement for the user's
representative ML workload.

## Prerequisites

Files-only authoring requires accessible source, not Docker, SSH, or cloud auth. Local
container tests need a working Linux builder. Live tests additionally need the selected
account/registry permissions and a bounded cost/time plan. Read only prerequisites of
that route; [managed GitHub builds](../../../runpod-build-template/reference/github-integration.md)
can avoid a local Docker installation for eligible Serverless projects.

## Walkthrough

1. Identify input → operation → output and target. Inspect source/locks/entrypoint;
   resolve material ambiguity instead of fabricating a wrapper.
2. Select a compatible base and build route. Keep heavy dependencies outside mounts;
   document source, image and model identities and provisional hardware requirements.
3. Add the files the chosen target needs, preserving existing layout. Follow one variant.
4. Write a README quickstart and concrete deployment settings, not an invented schema.
5. Execute available checks and deliver a precise next action for unavailable stages.

## Verify

From the repository root, without Docker or third-party Python packages:

```bash
python3 -B -m unittest discover -s plugins/runpod/skills/runpod/golden-paths/26-template-project/template -p test_app.py -v
```

This verifies text-statistics output, queue input failures/recovery, actual local HTTP
readiness/errors and concurrent request isolation. Container `test` stages exercise
the same checks on each image's runtime. The variants then test the actual default
entrypoint and, when authorized, the selected external Runpod interface.

## Gotchas

- Explicit authoring does not become a prebuilt deployment merely because one exists.
- Hosted-build limits and source-access boundaries can change the build route.
- An image build, local HTTP 200, or CPU matrix operation is not a Runpod GPU pass.
- Existing golden-path commands are historical examples; confirm current live syntax.

## Cost & cleanup

No billable resource is needed to write or statically test the project. Use only
disposable, budgeted resources for live acceptance; save evidence and verify cleanup.
Remove only the local test containers/images and temporary data created for this run.

## Skill gaps / verification remaining

These examples demonstrate app-specific outputs and honest evidence boundaries. Live
Pod, queue, load-balancer, managed-GitHub and GPU acceptance remain to be executed.
An independent invoice-total application was forward-tested locally on 2026-10-06:
the generated queue image built, six application checks passed, and its real SDK
entrypoint returned the expected result. A second reviewer independently followed
the generated README and reproduced the build, tests, worker result and original CLI.
This establishes transfer to a second CPU application, not live Runpod or GPU acceptance.
