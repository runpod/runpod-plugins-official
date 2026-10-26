---
concepts: [pod-migration]
---

# Common gotchas

Cross-cutting mistakes that bite people deploying on Runpod, as
symptom → cause → fix. See `docker.md` and `storage.md` for the full mechanics.

## Image built for the wrong CPU architecture

- **Symptom:** worker/pod fails to start, "exec format error", or the container
  never comes up — often only after building on an Apple Silicon / ARM machine.
- **Cause:** the image was built for arm64. Runpod hosts are x86_64.
- **Fix:** rebuild with `docker build --platform=linux/amd64 ...` and re-push.
  This is the #1 deploy failure.

## CUDA / driver mismatch — container dies at startup, or silently runs on CPU

- **Symptom:** the image pulls fine but the container exits immediately with a CUDA
  init / driver error (`CUDA driver version is insufficient for CUDA runtime version`,
  `no kernel image is available for execution on the device`, a cuDNN load failure), or
  it *starts* and `torch.cuda.is_available()` is `False` so everything crawls on CPU.
  Most common on the first run of a newly created pod, and on Blackwell cards
  (RTX 5090, RTX PRO 6000 Blackwell, B200).
- **Cause:** the host machine's CUDA version is **older than the image was built for**.
  A create with no CUDA constraint accepts any host, so an image built for 12.8 or 13.0
  can be scheduled onto an older host. Nothing at create time rejects the pairing.
- **Diagnose:** read the host's version off the pod itself — `runpodctl pod get <id>`
  (v2 `GET /v2/pods/{id}`) returns `cudaVersion`, e.g. `"12.8"`. Compare it to the `cu`
  tag in the image name (`…-cu1281-…` = 12.8.1, `runpod/comfyui:cuda13.0` = 13.0).
  Host older than the image is the bug. `runpodctl pod logs <id> --source container`
  shows the actual init error.
- **Fix:** recreate with a floor — `runpodctl pod create … --min-cuda-version 12.8`
  (or `gpu.minCudaVersion` on REST v2). Editing a running pod won't move it to a
  different host. Default the floor to `12.8`; use `13.0` only for a CUDA-13 image.
  Full rule, the `allowedCudaVersions` variant, and how to check which versions have
  capacity: [`gpu-selection.md`](gpu-selection.md#step-3-pin-the-cuda-floor).
- **Related trap:** picking the wrong CUDA-line *variant* of a template (the ComfyUI
  12.8 image does not support Blackwell / CUDA 13) — see
  `../../runpod-templates/reference/comfyui.md`.

## Using the `latest` tag

- **Symptom:** you push new code but workers keep running old behavior; you can't
  tell which version is live.
- **Cause:** `latest` is mutable and Runpod caches images per host, so workers
  serve a stale cached `latest`.
- **Fix:** use explicit tags (`v1.0.0`, `v1.0.1`) or pin the digest
  (`name:tag@sha256:...`). Bump the tag on every change.

## Private image won't pull

- **Symptom:** endpoint/pod stuck initializing; logs show an image pull /
  authentication error.
- **Cause:** the image is private and Runpod has no registry credentials.
- **Fix:** add container-registry credentials in Console → Settings → Container
  Registry, then select them on the template/endpoint. Runpod uses
  `docker login`-style creds. Headless equivalent: MCP
  `create-container-registry-auth`, then pass the id as `containerRegistryAuthId`
  on create-pod/create-endpoint.
- **Fix for AWS ECR:** you can register the repository instead of storing
  credentials — MCP `create-registry-delegation` grants Runpod scoped pull access
  to an ECR repo ARN. See that tool's parameter descriptions for the specifics.

## Image builds, then inference crashes with "Numpy is not available"

- **Symptom:** the image builds fine and the worker **starts**, but the first job
  fails at inference with `RuntimeError: Numpy is not available` (often preceded at
  import by `UserWarning: Failed to initialize NumPy: _ARRAY_API not found`).
- **Cause:** a NumPy 2.x / older-torch ABI mismatch. `pip install torch==2.2.2`
  pulls the latest `numpy` (2.x) by default, but that torch wheel was built against
  NumPy 1.x and can't use 2.x — any `.numpy()` call at inference throws.
- **Fix:** pin `numpy<2` in `requirements.txt` (or upgrade torch to a numpy-2-aware
  build). Catch it **before deploy** by running the container locally against a
  `test_input.json` (`docker.md` "Test the container locally") — the import warning
  is the early tell; the crash only surfaces on an actual job, not at startup.

## `pip install runpod` fails on a `runpod/pytorch` base ("Cannot uninstall cryptography")

- **Symptom:** building/setting up on an official `runpod/pytorch` image, `pip install
  runpod` (or `-r requirements.txt`) aborts with `Cannot uninstall cryptography 41.0.7 …
  no RECORD file was found` (and/or `error: externally-managed-environment`).
- **Cause:** the base ships a **Debian-managed** `cryptography`, so pip can't uninstall
  it to install the newer version `runpod` depends on. PEP-668 also marks the base pip
  "externally managed".
- **Fix:** `pip install --break-system-packages --ignore-installed cryptography runpod`.
  Install conflict-free deps (e.g. `faster-whisper`) first, separately, so
  `--ignore-installed` stays scoped to the `cryptography`/`runpod` pair. Verified live
  2026-07-10 (golden path 09); bake it into the Dockerfile as two `pip install` steps.

## Cold starts and timeouts

- **Symptom:** first request after idle is slow or times out; `/runsync` returns
  a timeout while the model is still loading.
- **Cause:** cold start = container pull + start + model load. `runsync` has a
  ~60s ceiling; large model loads can exceed it.
- **Fix:** use `/run` + poll status (or raise the sync timeout); enable FlashBoot;
  keep workers warm with `min_workers` / longer `idle_timeout`; load the model at
  module level, not inside the handler; use cached models or a network volume so
  the model isn't re-downloaded each start.

## Pod shows "Running" but ports/services aren't reachable yet

- **Symptom:** the pod is green/"Running" but the proxy URL 502s, the public IP
  or TCP port mapping is blank, or JupyterLab is a white screen.
- **Cause:** "Running" only means the container exists — services and port
  assignments take extra time to initialize.
- **Fix:** wait ~30–60s; check the **Telemetry** tab to confirm readiness; read
  the assigned public IP / external TCP port from the **Connect** menu once
  populated. Note external TCP port mappings change on every pod reset, and
  Community Cloud public IPs can change on migration/restart.
- **Variant — after a `pod stop`→`start`, the external TCP port is reassigned AND
  `runpodctl ssh info` can hand you a STALE port.** Live case (dev pod, 2026-07-10):
  the pod first came up on port `17740`; after stop/start the *first* `ssh info`
  still reported `17740` (all SSH connections refused) and reported `READY` while
  sshd was still down for ~90s — a moment later a fresh `ssh info` returned the real
  new port `12890`. **Fix:** after a restart don't trust the first `READY` or the
  first port — re-run `ssh info` until you get a port that actually accepts an `ssh`
  connection, then update your `~/.ssh/config` `Port`. This is what breaks VS Code
  Remote-SSH reconnects (see golden path 06).

## Proxy 524 / 100-second timeout

- **Symptom:** requests through `https://<pod-id>-<port>.proxy.runpod.net` die at
  ~100s with a `524`.
- **Cause:** the HTTP proxy runs through Cloudflare, which caps connection time at
  100 seconds.
- **Fix:** don't hold a single request open that long — return a job id and poll,
  use background queues/progress endpoints, or use direct TCP (public IP) instead
  of the proxy for long-lived connections.

## Network volume locked to a data center

- **Symptom:** can't get GPUs, or the endpoint won't schedule workers after
  attaching a volume.
- **Cause:** a network volume lives in one DC; attaching it forces all compute
  into that DC, shrinking GPU availability.
- **Fix:** confirm your target GPU exists in the volume's DC before attaching; or
  attach multiple volumes from different DCs (one per DC) to spread workers —
  remembering data doesn't sync between them automatically.

## Model not baked or mounted

- **Symptom:** handler errors with "model not found," or OOM/download stalls on
  first request.
- **Cause:** the worker has no model — it wasn't baked into the image, cached, or
  mounted from a volume.
- **Fix:** pick one delivery path (bake in, cached HF model at
  `/runpod-volume/huggingface-cache/hub/`, or network volume) and make the handler
  read from that path. For gated/private HF models set `HF_TOKEN`.

## Data disappeared after stop

- **Symptom:** files written during a run are gone after stopping the pod or the
  worker scaling down.
- **Cause:** you wrote to container/ephemeral disk, which is wiped on stop.
- **Fix:** write to `/workspace` (pod volume disk) or a network volume
  (`/runpod-volume` on serverless). Editing/resetting a pod also wipes anything
  outside `/workspace`.

## Huge log or job output

- **Symptom:** logs stop appearing (throttled), or job submission/result is
  rejected for size.
- **Cause:** excessive logging triggers throttling; job payloads exceed limits
  (`/run` ~10 MB, `/runsync` ~20 MB).
- **Fix:** reduce log verbosity / use structured logging; write bulky output to a
  network volume or external S3 and return a URL/reference instead of inlining it.

## GPU out of memory

- **Symptom:** job fails with an OOM/CUDA memory error.
- **Cause:** model or batch size exceeds the selected GPU's VRAM.
- **Fix:** reduce batch size / context length, or pick a larger-VRAM GPU. For
  vLLM, lower `GPU_MEMORY_UTILIZATION` and/or `MAX_MODEL_LEN`.

## CPU-bound work on a GPU pod is slower than it should be

- **Symptom:** preprocessing, decoding, CPU inference or a data loader runs slowly,
  and gets worse when you add threads or workers.
- **Cause:** the pod can see every core on the machine (`nproc` and
  `os.cpu_count()` may say 48 or 96), but it can only use the vCPUs it rents.
  PyTorch, OpenMP, MKL and similar libraries start a thread per visible core,
  and the extra threads get throttled.
- **Fix:** read the real limit from the cgroup and cap threads to it. Rising
  `nr_throttled` in the cgroup's `cpu.stat` confirms the problem. A test pod with
  5.1 cores of CPU ran a CPU matmul about 1.7 times faster at 5 threads than at
  PyTorch's default of 24.

  In a shell or start script, source this before launching the workload. It
  handles cgroup v2 (`cpu.max`) and v1 (`cpu.cfs_quota_us`), and falls back to
  the visible cores when there is no limit:

  ```bash
  # CPUs this container can actually use: its cgroup CPU limit rounded down,
  # capped at the cores it can see. Falls back to nproc when there is no limit.
  cpu_limit() {
    local quota="" period="" visible n
    visible=$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc)
    if [ -r /sys/fs/cgroup/cpu.max ]; then                 # cgroup v2
      read -r quota period < /sys/fs/cgroup/cpu.max
    elif [ -r /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then  # cgroup v1
      quota=$(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)
      period=$(cat /sys/fs/cgroup/cpu/cpu.cfs_period_us)
    fi
    if [ -z "$quota" ] || [ "$quota" = max ] || [ "$quota" -le 0 ]; then
      echo "$visible"; return
    fi
    n=$(( quota / period ))
    [ "$n" -lt 1 ] && n=1
    [ "$n" -gt "$visible" ] && n=$visible
    echo "$n"
  }
  export CPUS=$(cpu_limit)
  export OMP_NUM_THREADS=$CPUS MKL_NUM_THREADS=$CPUS OPENBLAS_NUM_THREADS=$CPUS NUMEXPR_NUM_THREADS=$CPUS
  ```

  In Python, run this before importing `torch` or `numpy`, and also set data
  loader `num_workers` to at most `CPUS`:

  ```python
  import os
  from pathlib import Path

  def cpu_limit() -> int:
      """CPUs this container can actually use: its cgroup CPU limit rounded down,
      capped at the cores it can see. Falls back to the visible cores when there
      is no limit."""
      visible = len(os.sched_getaffinity(0))
      try:
          quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()  # cgroup v2
      except OSError:
          try:  # cgroup v1
              quota = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip()
              period = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip()
          except OSError:
              return visible
      if quota == "max" or int(quota) <= 0:
          return visible
      return max(1, min(visible, int(quota) // int(period)))

  CPUS = cpu_limit()
  # Set these before importing torch or numpy so their thread pools pick them up.
  for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
      os.environ[var] = str(CPUS)

  import torch  # noqa: E402  (drop these two lines if you don't use torch)
  torch.set_num_threads(CPUS)
  ```

  Both snippets give one process the whole limit. When you launch several
  processes, such as `torchrun --nproc_per_node=N` ranks or parallel workers,
  give each one `CPUS / N` threads instead, or every process starts `CPUS`
  threads and they throttle again. After sourcing the bash snippet:

  ```bash
  N=4  # number of processes you launch
  PER=$(( CPUS / N > 0 ? CPUS / N : 1 ))
  export OMP_NUM_THREADS=$PER MKL_NUM_THREADS=$PER OPENBLAS_NUM_THREADS=$PER NUMEXPR_NUM_THREADS=$PER
  ```

## Serverless worker "ready" but jobs never run

- **Symptom:** the endpoint has `ready` workers but jobs sit `IN_QUEUE` with
  `inProgress: 0` and never complete.
- **Cause:** a broken/mis-dispatching worker image, or workers `throttled` on a
  scarce GPU pool the model doesn't need.
- **Fix:** switch to a different (maintained) Hub worker on a **broad, high-
  availability GPU pool** — don't wait it out. Diagnose via the endpoint `/health`
  worker counts — `runpodctl serverless health <id>` reads them for you (v2.9.0+) —
  and then read the worker logs. There is no serverless worker-log command in
  runpodctl and no worker-log path on REST v1; use the MCP `stream-worker-logs`
  tool, the v2 REST logs path, or the Console Workers tab.

## Serverless job goes `IN_PROGRESS` then times out

- **Symptom:** a worker *picks up* the job (`IN_PROGRESS`) but never returns output;
  the job fails with `"job timed out after 1 retries"` after ~30–50 s.
- **Cause:** this looks like a broken worker but is often a **job-reject by a healthy
  worker** — usually a handler-signature or empty-`input` bug in *your* request, not the
  image.
- **Fix:** get the **worker logs** (MCP `stream-worker-logs` or the Console) before
  assuming the image is bad. Real case (flash endpoint, 2026-07-10): fitness checks
  passed, then it logged `read() got an unexpected keyword argument …` /
  `Job has missing field(s): id or input` — a handler-signature + empty-input bug (see
  flash gotcha "Request body shape"). Only if the logs show a genuinely dead/looping
  worker should you switch workers or try a different data center.

## Handler swallowing errors

- **Symptom:** jobs report success but return nothing useful; failures are
  invisible.
- **Cause:** a broad `try/except` suppresses the exception, so the SDK never marks
  the job `FAILED`.
- **Fix:** return a structured error for graceful failures, or re-raise to flag
  the job `FAILED`. Don't silently swallow.
