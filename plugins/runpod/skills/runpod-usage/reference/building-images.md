---
concepts: [container-image, network-volume, container-disk, model-store]
---

# Building container images for Runpod

How to think about building an image for Runpod: pick the right base, layer for speed,
decide what to **bake in** vs **mount at runtime**, and match the **image contract** to your
target (pod vs serverless queue vs serverless load-balanced). CLI mechanics (login, tag,
push) live in [companion-clis docker](../../companion-clis/reference/docker.md) and
[docker.md](docker.md); this is the strategy layer.

## Start from an official Runpod base image

**For a PyTorch GPU workload, prefer a compatible official `runpod/pytorch:<tag>` image.**
Reuse its framework/CUDA stack rather than installing a second copy. Check the application's
dependency requirements and run a representative operation on the intended GPU before
claiming compatibility. The [custom Pod guide](https://docs.runpod.io/pods/templates/create-custom-template)
shows how to extend these bases.

Existing host-cached layers can avoid transfer, but do not promise that every selected
host already has the base. Verify layer reuse and cold-start time separately.

**Exceptions (both shown in the golden paths):** a trivial CPU-only workload may use a slim
base (e.g. `python:3.11-slim`) — see [GP23](../../runpod/golden-paths/23-minimal-queue-image/README.md);
and if you build from a **non-Runpod base you must reproduce SSH yourself** when the pod
promises SSH access (see the section below and [GP22](../../runpod/golden-paths/22-minimal-pod-image/README.md)).
For a different runtime, a pinned Ubuntu base with explicit dependencies can be suitable;
do not add PyTorch to an application that does not use it.

Then, whatever the base:

- **Pin an exact published tag**, e.g. `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`,
  and record its resolved digest, source revision, dependency locks and model revision.
  A versioned base alone does not pin later downloads. See
  [image versioning](https://docs.runpod.io/serverless/workers/deploy#image-versioning).
- **Build for x86_64:** `docker build --platform=linux/amd64 …` — Runpod hosts are x86_64
  (see [docker.md](docker.md)).

## Layer for fast, cacheable pulls

Order layers **least- to most-frequently-changing** so a code edit doesn't invalidate the
heavy dependency layers, and independent layers pull in parallel:

1. base image (`FROM runpod/pytorch:…`)
2. system deps (`apt-get …`)
3. Python deps (`pip install …`)
4. **your code last**

Unchanged build steps can reuse the builder's cache. A deployment host separately reuses
image layers it already has. Extending the **same published dependency image** preserves
its heavy layers across your templates; independently reinstalling the same PyTorch
version does not establish identical layers. Compare layer digests after a code-only edit.

## Dockerfile best practices

- **`.dockerignore`** — exclude `.git`, virtualenvs, datasets, local caches so the build context stays small and pushes fast.
- **Cache the dependency layer** — `COPY requirements.txt` and `pip install` *before* you `COPY` your code, so a code edit doesn't reinstall everything:
  ```dockerfile
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  ```
- **Shrink the image** (smaller = faster pull + cold start) with concrete steps: `apt-get install --no-install-recommends …` then `rm -rf /var/lib/apt/lists/*`; `pip install --no-cache-dir`; use a **multi-stage** build when heavy build tools aren't needed at runtime.
- **BuildKit cache mounts** for fast rebuilds: `RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt`.
- **Never bake secrets** into layers (API keys, tokens) — layers are extractable; pass secrets as runtime env.
- **`ENV PYTHONUNBUFFERED=1`** — so logs stream unbuffered. (Pin the base image tag too — see above.)

Keep changing build arguments near their first use so a source-version change does not
invalidate an earlier dependency install. See Docker's
[cache examples](https://docs.docker.com/build/cache/optimize/).

## Don't clobber the base image's startup (SSH / web terminal) — **pods**

Runpod PyTorch bases provide `/start.sh` for their interactive services: it reads
`$PUBLIC_KEY` into `~/.ssh/authorized_keys`, runs `ssh-keygen -A`,
starts `sshd`, and brings up the web terminal / Jupyter. It also runs `/pre_start.sh` before
and `/post_start.sh` after, if those exist.

**For a pod that promises these services:** inherit `/start.sh`, or invoke it from your
custom startup. Inspect the selected tag's command and hooks before overriding them.
Application-only pods may intentionally omit SSH/Jupyter; queue workers use their handler.

Why: if a custom `CMD`/`ENTRYPOINT` doesn't chain `/start.sh`, none of that startup runs — you
get **no SSH, no web terminal**, and can be locked out of the pod. For a pod this is the #1
footgun.

Three safe patterns, in order of preference:

1. **Don't override `CMD` at all** (default — use this unless you need your own foreground
   process). Add your layers, leave `CMD ["/start.sh"]`. Do per-pod work via the env-driven
   hooks the base already runs:
   ```dockerfile
   FROM runpod/pytorch:<tag>
   COPY post_start.sh /post_start.sh   # base runs this AFTER sshd is up
   RUN chmod +x /post_start.sh
   # no CMD — inherit the base's /start.sh
   ```
2. **Override only if you need your own foreground process** (a long-running service as PID 1):
   call the base start first, then `exec` your workload:
   ```dockerfile
   COPY run.sh /run.sh
   RUN chmod +x /run.sh
   CMD ["/run.sh"]
   ```
   ```bash
   #!/usr/bin/env bash
   /start.sh &        # SSH + web terminal (base startup), backgrounded
   exec python -u my_service.py   # your long-running workload in the foreground
   ```
   This starts both independently; it does not prove base services are ready. If the app
   needs completed base initialization, use the supported `/post_start.sh` hook instead.
   Verify SSH and the app separately, and use explicit supervision if both must fail
   together. A fixed sleep is not a readiness check.
3. **From a non-Runpod base, reproduce SSH yourself** (only if you can't start from
   `runpod/pytorch`). Minimum to not get locked out of a pod:
   ```dockerfile
   RUN apt-get update && apt-get install -y --no-install-recommends openssh-server python3 \
       && rm -rf /var/lib/apt/lists/*
   COPY start.sh /start.sh
   RUN chmod +x /start.sh
   CMD ["/start.sh"]
   ```
   ```bash
   #!/usr/bin/env bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   [ -n "$PUBLIC_KEY" ] && echo "$PUBLIC_KEY" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
   ssh-keygen -A                       # host keys
   service ssh start                   # or: /usr/sbin/sshd -D
   exec python3 -u -m http.server "${PORT:-8000}"  # concrete long-running workload
   ```

Reference implementation: `justinwlin/Runpod-GPU-And-Serverless-Base` (a dual pod+serverless
base) and the vendored `start.sh` in
[golden path 09](../../runpod/golden-paths/09-custom-serverless-dev-loop/README.md). Worked
end-to-end in [golden path 22 — minimal pod image](../../runpod/golden-paths/22-minimal-pod-image/README.md).

## Bake in vs mount at runtime (this drives startup speed)

The **image** and its baked files live on the host's **local disk** — fast.
When a **network volume** is attached it takes over the working directory (`/workspace` on a
pod, `/runpod-volume` on serverless); anything written there lives on **networked storage**,
which is slower — **especially for many small files**.

Keep runtimes outside volume mount points, for example `/opt/venv`: a mount can hide
baked files. Avoid copying the entire Python/PyTorch environment into `/workspace` at
every startup. Persist the mutable outputs and files the application actually needs.

Live proof that this is a real filesystem boundary (baked = `overlay`/local, volume =
`fuse`/MooseFS network mount): [golden path 25 — bake vs mount](../../runpod/golden-paths/25-bake-vs-mount/README.md).

- **Bake into the image:** packages, libraries, and lots of small static files → local, fast.
- **Mount a volume:** large/few files (model weights, datasets), anything that must persist
  across pods, or data you stream/live-load.
- **High-throughput / I/O-bound training:**
  - **temporary / one-off run** → a **pod using local (non-network) storage** is fastest;
  - **persistent, many small files, or I/O-bound** → a **high-performance network volume**.

  See [golden path 21 — storage tiers](../../runpod/golden-paths/21-storage-tiers.md).

## Match the image contract to the target

| Target | Needs a handler? | Entry point |
| --- | --- | --- |
| **Pod** | No | your `CMD`/entrypoint — a long-running service; bind `0.0.0.0`, expose ports |
| **Serverless — queue-based** | **Yes** | `runpod.serverless.start({"handler": handler})` |
| **Serverless — load-balanced** | No (different contract) | your own **HTTP server** exposing routes (no queue handler) |

Minimal runnable image per contract (each built + deployed live): pod →
[golden path 22](../../runpod/golden-paths/22-minimal-pod-image/README.md), queue →
[golden path 23](../../runpod/golden-paths/23-minimal-queue-image/README.md), load-balanced →
[golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md).

Queue vs load-balanced request/response shapes and when to pick each are covered in
[endpoint-workflows.md](endpoint-workflows.md) and golden paths
[12 (streaming)](../../runpod/golden-paths/12-serverless-streaming.md),
[14 (load-balancing)](../../runpod/golden-paths/14-load-balancing-endpoint.md), and
[17 (WebSocket)](../../runpod/golden-paths/17-serverless-websocket.md). One image can be
**dual-mode** (pod dev + serverless) — see
[golden path 09](../../runpod/golden-paths/09-custom-serverless-dev-loop/README.md).

## Test locally before deploying

- Build for the right platform: `docker build --platform=linux/amd64 …`.
- **Queue handler:** run the container and invoke `handler.py` locally (the dual-mode
  `python handler.py` loop in [golden path 09](../../runpod/golden-paths/09-custom-serverless-dev-loop/README.md))
  before pushing.
- **Load-balanced:** run the container and hit the HTTP routes locally.
- Then push ([companion-clis docker](../../companion-clis/reference/docker.md)) and deploy
  (runpodctl or runpod-mcp).

Run the actual container entrypoint as well as unit checks. For an interactive pod, a
successful one-shot verification script is not the long-running process that keeps the
pod usable. Preserve base startup and run such checks through a hook or a separate command.
Report GPU execution and cloud behavior as unverified when only local checks ran.

## Exact rules

See [container images](../concepts/container-image.yaml),
[container disk](../concepts/container-disk.yaml),
[network volumes](../concepts/network-volume.yaml) and
[model delivery](../concepts/model-store.yaml).
