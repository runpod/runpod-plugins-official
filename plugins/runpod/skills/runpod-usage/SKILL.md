---
name: runpod-usage
description: >-
  How Runpod works and how to work it — pods vs serverless, GPU/VRAM selection,
  storage, building a container, networking, plus the agentic pod development loop
  (provision → ssh-exec → set up → poll readiness) and on-pod install hygiene
  (uv/apt). Use to answer "how does X work", "which GPU", "how do I build a
  container", or "how do I stand up a workload on a pod". Guidance, not a tool —
  execute with runpodctl, runpod-mcp, or flash.
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Runpod usage (concepts)

Background knowledge for making the right choice before you act. This skill runs
nothing — once you know what to do, execute with **runpod-mcp**/**runpodctl**
(infra), **flash** (your own code), or **companion-clis** (models/images/data).

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
| Which GPU / how much VRAM / cost & availability / data centers | `reference/gpu-selection.md` |
| Reaching a pod or endpoint over HTTP (proxy URLs, exposed ports) | `reference/networking.md` |
| Common mistakes and how to avoid them | `reference/gotchas.md` |
