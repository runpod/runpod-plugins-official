---
name: runpod-usage
description: >-
  Explain Runpod architecture and design choices: Pods versus Serverless, GPU/VRAM,
  image construction, storage, networking, and workload development. For creating
  or improving a complete template project use runpod-build-template; execute
  infrastructure with runpodctl/runpod-mcp and code-first work with flash.
metadata:
  author: runpod
  version: "1.7.1" # x-release-please-version
  concepts: [pod, serverless-endpoint, network-volume, container-disk, pod-volume-disk, gpu-type, exposed-port, worker]
license: Apache-2.0
---

# Runpod usage (concepts)

Background knowledge for making the right choice before you act. This skill runs
nothing — once you know what to do, execute with **runpod-mcp**/**runpodctl**
(infra), **flash** (your own code), or **companion-clis** (models/images/data).

**This skill explains; the golden paths demonstrate.** When the question is really "how do I
do X" rather than "how does X work", the verified end-to-end example is the faster answer —
[runpod/golden-paths/README.md](../runpod/golden-paths/README.md). Read the concept here, then
follow the path.

To author files for a custom template, use
[runpod-build-template](../runpod-build-template/SKILL.md); this lane supplies the
shared concepts, not a competing packaging workflow.

Read the one reference file that matches the question:

| Question | Read |
| --- | --- |
| First-run setup / auth — get + set `RUNPOD_API_KEY`, SSH, companion creds | `reference/getting-started.md` |
| Pods vs serverless, workers, cold starts, FlashBoot, queue vs load-balanced | `reference/concepts.md` |
| **The development loop for ANY workload (start here)** — plan → prefer prebuilt → provision → verify → teardown | `reference/development-loop.md` |
| **Stand up / iterate a workload on a pod** — the pod sub-loop | `reference/pod-workflows.md` |
| **Deploy / iterate a serverless endpoint** — Hub vs flash vs custom, invoke + verify | `reference/endpoint-workflows.md` |
| **Install software on a pod** — package hygiene, `uv`, non-interactive, caching | `reference/on-pod-setup.md` |
| Build a Docker image Runpod can run (handler contract, Dockerfile, `--platform=linux/amd64`) | `reference/docker.md` |
| **How to build an image well** — base image, layering, bake-in vs volume, pod vs serverless (queue/LB) contract | `reference/building-images.md` |
| Where data lives — container disk vs network volume, model caching, S3 access | `reference/storage.md` |
| Which GPU / how much VRAM / **which CUDA version** / cost & availability / data centers | `reference/gpu-selection.md` |
| Why a stopped pod may not restart with a GPU — pods are bound to one machine; what else is per machine | `reference/pods-and-machines.md` |
| Endpoint releases, rolling updates, version overlap, GitHub builds | `reference/endpoint-builds-and-releases.md` |
| Storing API tokens and keys as secrets and referencing them from env vars | `reference/secrets.md` |
| Reaching a pod or endpoint over HTTP (proxy URLs, exposed ports) | `reference/networking.md` |
| Common mistakes and how to avoid them | `reference/gotchas.md` |

## Exact facts: the concept files

The reference files explain. For a precise fact, or a rule an action must satisfy, read
the concept files in `concepts/` next to this file. There is one YAML file per concept
(`pod.yaml`, `network-volume.yaml`, `machine.yaml`, …), each with its fields, states,
relations and rules, and every rule cites the public source it comes from.

```bash
grep -il "volume disk" concepts/*.yaml    # find the concept by name or alias
grep -n "statement:" concepts/pod-volume-disk.yaml
```

- `rules[].statement` is the fact. `see:` points at related rules on other concepts.
- A rule with `conflict: true` records two public sources that disagree. Give both readings.
- A `kind: process` file explains a flow step by step. `pod-deployment.yaml` covers deploy,
  stop and restart, including why a restart can fail while the data center has stock.
