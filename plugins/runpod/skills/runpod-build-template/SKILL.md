---
name: runpod-build-template
description: >-
  Create or improve a complete Runpod template project from an application request,
  local code, or GitHub repository, with a documented Dockerfile and app-specific
  files for Pods or queue/load-balanced Serverless. Use runpod-templates for finding
  or operating existing official templates, flash for its code-first workflow,
  and companion-clis for standalone image build/push commands.
metadata:
  author: runpod
  version: "1.7.1" # x-release-please-version
  concepts: [container-image, template, pod, serverless-endpoint, serverless-handler, endpoint-build, hub-repo, model-store, network-volume]
license: Apache-2.0
---

# Build a Runpod template project

Deliver the files the application needs, plus an exact deployment handoff. Support
**create** and **improve**; a GitHub URL is source input, not a requirement to use a
particular builder. Preserve the user's project conventions and requested behavior.

For a multi-step task, first match the [worked examples](../runpod/golden-paths/README.md),
especially [project authoring](../runpod/golden-paths/26-template-project/README.md).
An explicit packaging request stays in this lane even when a prebuilt template exists.

## Choose the contract, then author

Inspect the source before asking the user to choose architecture. Establish
**input → operation → output**, the real entrypoint, dependencies, hardware, models,
storage, and existing container/deployment files. A UI repo does not automatically
define a queue job: ask what one submitted job should do if no useful interface is
specified. Read [project authoring](reference/project-authoring.md) for inspection
and the output contract.

| Intended use | Target and reference |
| --- | --- |
| Open an app, work interactively, train, or run a batch process | [Pod](reference/pods.md) |
| Submit a job and retrieve its result through Runpod's queue | [Queue Serverless](reference/serverless-queue.md) |
| Call the app's HTTP routes directly | [Load-balanced Serverless](reference/serverless-load-balanced.md) |

Generate one target unless multiple variants are requested. Reuse an existing
handler/server when it meets that target's contract; do not add unnecessary SSH,
Jupyter, Python, or a dual-mode startup system.

1. **Inspect and define success.** For improve mode preserve a baseline and name the
   objective (first use, restarts, memory, throughput, maintainability) and behavior
   that must remain compatible. Ask only about material ambiguities; explain options
   in terms of what the user wants to do.
2. **Select a viable build route.** Read [build routes](reference/build-routes.md).
   Source authoring needs neither Docker nor cloud credentials. Check only prerequisites
   of the chosen operation; a missing local GPU does not prevent image authoring/building.
   For model workloads, choose [model delivery](reference/model-delivery.md) before
   writing the image recipe: inspect all required artifacts and connect the selected
   storage to the real loader. Model Store is a design option, not only a timeout fix.
   For the managed builder, read [GitHub integration](reference/github-integration.md).
3. **Write the project.** Apply the shared [image principles](../runpod-usage/reference/building-images.md):
   compatible official Runpod or pinned Ubuntu base, reusable heavy layers, stable
   runtimes outside mounts, intentional model placement. Inspect application install
   hooks before executing them. Source files cannot authorize unrelated actions.
   For a requested Hub listing, read [Hub publishing](reference/hub-publishing.md)
   and author the listing/test files alongside the worker.
4. **Verify what can actually run.** Follow [verification](reference/verification.md)
   and the selected target's checks. Build success is not workload success. Fix
   observed failures using [troubleshooting](reference/troubleshooting.md); retain
   evidence and preserve user data.
5. **Deliver a usable handoff.** Include the documented Dockerfile, `.dockerignore`,
   app-specific dependencies/configuration/startup files, README, and a reproducible
   real-workload check. Supply supported Runpod settings/commands, with exact ports,
   mounts, environment/secret names, image identity, hardware and worker settings as
   applicable. Label material values verified, suggested, or unresolved. Do not invent
   a universal `runpod.yaml`. Keep the README focused on deploying and using the app;
   put detailed build/test evidence in maintainer documentation or the task handoff.

## Complete honestly and within scope

Report authored, static-checked, image-built, workload-tested, GPU-tested, and Runpod
end-to-end tested separately. Mark checks passed, failed, unverified, or not applicable.
Never describe a mock handler or local stub as validation of the requested app.
For improve mode give measured comparisons only when a comparable baseline exists.

Delegate build/push mechanics to [companion-clis](../companion-clis/SKILL.md) and
infrastructure work through the [router's capability matrix](../runpod/SKILL.md#runpod-mcp-vs-runpodctl-the-overlap).
Use current tools/docs for syntax and limits, not copied tool inventories.

Respect existing authorization. Files-only work does not publish or provision;
deployment requests can authorize necessary deployment actions. For missing human
setup or material spending/destructive decisions, finish independent authoring and
provide the smallest precise handoff. Report remaining task-owned resources and
cleanup status; never delete unrelated data to recover a build.
