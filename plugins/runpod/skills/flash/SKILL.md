---
name: flash
description: >-
  Code-first serverless with the Runpod Python SDK (`runpod` 2.0): define a
  `runpod.App` with `@app.queue` / `@app.api` / `@app.task`, iterate on remote
  GPUs/CPUs with `rp flash dev`, ship with `rp flash deploy`. Also covers
  maintaining and migrating legacy `runpod-flash` projects (`from runpod_flash
  import Endpoint`). Use runpod-build-template for explicit Dockerfile/template
  project authoring, and runpodctl/runpod-mcp for infrastructure management.
user-invocable: true
metadata:
  author: runpod
  version: "1.8.0" # x-release-please-version
  concepts: [flash, serverless-endpoint, serverless-handler, worker, volume-cache, model-store]
license: Apache-2.0
---

# Runpod SDK apps (Flash)

For an explicit Dockerfile/template project request, use
[runpod-build-template](../runpod-build-template/SKILL.md). Do not replace that
deliverable with Flash unless the user chooses its code-first workflow.

Write Python locally, run it on remote Runpod GPUs/CPUs with `rp flash dev`, then
`rp flash deploy` to ship. Flash is now part of the `runpod` package (2.0): one SDK, one
`rp` CLI, one login. The standalone `runpod-flash` package is deprecated on
**October 29, 2026** and gets no fixes after that date.

**`rp --help` and `rp flash <command> --help` are authoritative for the command surface.**
This skill is the mental model, the decision rules, and the gotchas that help output does not
carry. Confirm the installed version with `pip show runpod` before concluding a command or
parameter is unavailable.

## Which SDK is this project on?

Check before writing code. The two APIs do not mix.

| You see | Project is on | Do |
|---|---|---|
| `import runpod`, `runpod.App(...)`, `@app.queue`, `rp flash ...` | **Runpod SDK 2.0** | This file + `reference/` |
| `from runpod_flash import Endpoint`, `@Endpoint(...)`, `flash dev`, `runpod-flash` in deps | **Legacy runpod-flash** | [reference/runpod-flash-legacy.md](reference/runpod-flash-legacy.md) to maintain it, [reference/migrate-from-runpod-flash.md](reference/migrate-from-runpod-flash.md) to move it |
| A new project | Runpod SDK 2.0 | Start below |

Write new code on the SDK. For an existing `runpod-flash` project, propose migrating and
check its *Known differences* first; don't migrate silently.

**Worked examples first for anything multi-step.** Flash appears in end-to-end paths:
[03 variant B (whisper endpoint)](../runpod/golden-paths/03-whisper-endpoint/variant-b-flash.md),
[07 (network-volume handoff)](../runpod/golden-paths/07-network-volume-handoff.md) and
[08 (fine-tune → serve)](../runpod/golden-paths/08-finetune-to-serverless.md); the full index is
[runpod/golden-paths/README.md](../runpod/golden-paths/README.md). Runnable single-file apps
live in [`examples/`](examples/).

**Load on demand:**

| Need | Read |
|------|------|
| Install, `rp login`, `rp flash init`, every `rp` command | [reference/setup-and-cli.md](reference/setup-and-cli.md) |
| Decorator parameters, call styles, `Queue`/`Api`/`Endpoint` clients, volumes, `Model`, `Secret`, GPU & CPU names | [reference/api.md](reference/api.md) |
| Worked patterns: choosing a model, warm model loading, CPU→GPU pipeline, fan-out, tasks, raw HTTP | [reference/patterns.md](reference/patterns.md) |
| Moving a `runpod-flash` project to the SDK | [reference/migrate-from-runpod-flash.md](reference/migrate-from-runpod-flash.md) |
| Maintaining a `runpod-flash` project as it is | [reference/runpod-flash-legacy.md](reference/runpod-flash-legacy.md) |

Quick start: `uv add "runpod>=2.0.0rc1"` (or `pip install "runpod>=2.0.0rc1"`; this resolves
to the release candidate until 2.0.0 is stable) → `rp login` (or `export RUNPOD_API_KEY=...`)
→ `rp flash init my-app` → `cd my-app && rp flash dev main.py`.

## The app model

```python
import runpod

app = runpod.App("my-app")                     # names the group of resources

@app.queue(gpu="4090", dependencies=["torch"]) # queue-based serverless endpoint
def infer(x: list[float]):
    import torch
    return {"sum": torch.tensor(x, device="cuda").sum().item()}

@runpod.local_entrypoint                       # runs on YOUR machine
def main():
    print(infer.remote([1.0, 2.0, 3.0]))       # runs on a Runpod worker
```

| Decorator | Creates | Use for |
|---|---|---|
| `@app.queue(...)` on a function | Autoscaling queue-based endpoint | Request/response inference, batch jobs |
| `@app.api(...)` on a class | Load-balanced endpoint serving routes (`@runpod.get`/`@runpod.post`, setup in `@runpod.init`) | HTTP services, multi-route APIs, load-once model state |
| `@app.task(...)` on a function | One ephemeral **Pod per call**, terminated when it returns | Training, fine-tuning, long jobs |

Call styles on a queue or task handle: `fn.remote(...)` (blocks), `await fn.remote.aio(...)`,
`fn.spawn(...)` (returns a `Job`), `fn.stream(...)` (generator functions), `fn.local(...)`
(runs on your machine). API classes are called by route: `MyApi.post("/path", body)`.

## Dev vs deploy

- `rp flash dev main.py` — **iterate.** Creates temporary endpoints (`dev-<app>-<resource>-<hash>`),
  runs the `@runpod.local_entrypoint` on your machine, streams the workers' `print` output to
  your terminal, and re-runs after every file save. Ctrl-C deletes the endpoints. There is **no
  local HTTP server**; the entrypoint is how you exercise the code.
- `rp flash dev main.py --once` — run the entrypoint once, tear down, exit non-zero on failure.
  The smoke test for CI and for "does the migrated code work".
- `rp flash deploy` — **ship.** Builds an artifact (≤1,500 MB, torch excluded on built-in GPU
  images) and creates persistent endpoints in the `default` environment (`--env NAME` for
  others). Re-run to update. `--build-only` packages without deploying, a cheap offline check
  that discovery and dependency resolution work.

Dev and deploy run the **same module source**: the whole file ships, so module-level imports,
constants and helpers behave identically in both. The app must live in **one file** today
(multi-file projects are a known gap).

## Autonomous dev loop

A dev session is long-running. Three rules:
- **Run it in the background with stdin closed** (`< /dev/null`). With no stdin it re-runs
  the entrypoint on every file save, so you never need to press Enter.
- **Capture its output** to a log file and read it. Worker `print`s, tracebacks, `✗ remote execution failed: ...` and the per-run
  `✓ done in ...` / `✗ failed in ...` lines land there.
- **Stop it with SIGINT**, so it deletes its endpoints, and confirm the log ends with
  `cleaning up N deleted`. A non-interactive shell starts `&` jobs with SIGINT ignored, and
  SIGTERM or `kill -9` exit without cleanup, so launch through the wrapper below, which
  restores SIGINT. When one run is enough, prefer `--once`; it cleans up on its own.

```bash
# restore SIGINT for the background job, then exec rp
python3 -c 'import os,signal,sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execvp(sys.argv[1], sys.argv[1:])' \
  rp flash dev main.py < /dev/null > /tmp/rp-dev.log 2>&1 &
DEV=$!
# poll the log (bounded) for the run result: "✓ done in ..." or "✗ failed in ..."
for i in $(seq 1 120); do grep -qE "✓ done in|✗ failed in" /tmp/rp-dev.log && break; sleep 3; done
tail -40 /tmp/rp-dev.log
# edit main.py and save -> the session re-scans, refreshes endpoints, re-runs main()
# (each run appends a new result line; read the last one)
kill -INT $DEV; wait $DEV; tail -3 /tmp/rp-dev.log   # expect "cleaning up N deleted"
```

For a single check, `rp flash dev main.py --once` is simpler and cleans up on its own. If a
session died without cleanup, list leftovers with `runpodctl serverless list` and delete the
`dev-<app>-...` endpoints **this session created**, by ID.

## Choosing the resource shape

Default to plain Python on the Runpod runtime image: `dependencies=[...]` and
`system_dependencies=[...]` install on the worker, so no Dockerfile is needed, and even large
HuggingFace models stay in code (see [reference/patterns.md](reference/patterns.md#loading-ml-models)).

- **`image="org/image:tag"`** on any decorator runs your function on that image; it needs
  Python 3, not a Serverless handler. Use it for system libraries or a specific CUDA stack.
  `registry_auth=` names saved credentials for a private image (`rp registry add`).
- **A prebuilt inference server image** (vLLM, worker-comfyui) that already implements a
  Serverless handler is not an SDK app. Deploy it with runpodctl or runpod-mcp and call it
  with `runpod.Endpoint("ENDPOINT_ID")`.
- **An existing endpoint** by ID: `runpod.Endpoint("ENDPOINT_ID").run_sync({...})`.
- **A resource in another deployed app**: `runpod.Queue(app="media", name="transcribe")` /
  `runpod.Api(app="media", name="inference")`.

## Gotchas

1. **Queue arguments and results must be JSON-serializable.** Queue jobs are plain JSON in dev
   and deploy alike; a non-JSON argument fails with `arguments must be json-serializable`. Pass
   URLs or base64, not objects. Whole-number floats can arrive as integers (`1.0` → `1`), so
   cast numeric inputs explicitly (`torch.tensor(x, dtype=torch.float32)`).
2. **One file per app.** Discovery imports the module you point at. Helpers in a sibling local
   module are not shipped yet; keep them in the same file or in an installable package.
3. **Keep blocking work out of module scope.** The SDK imports your module to discover
   resources, locally and on every worker. Put heavy imports (`torch`) and work inside
   functions; guard local-only code with `runpod.is_local()`.
4. **`gpu=` and `cpu=` are exclusive** (`gpu and cpu are mutually exclusive`). GPU strings can
   be short (`"4090"`, `"H100"`) or a list of acceptable GPUs.
5. **Default `workers=(0, 3)`** (runpod-flash was `(0, 1)`). Set it explicitly when cost or
   concurrency matters. `idle_timeout` is seconds (default 60).
6. **Auto GPU switching needs `workers` max ≥ 5** when you pass a list of GPUs.
7. **10 MB payload limit** on requests. Return large outputs via a volume or object storage URL.
8. **Volumes outlive everything.** Dev sessions and `rp flash undeploy` delete endpoints, not
   the `NetworkVolume`s they created, and those keep billing. Queue and API resources mount one
   volume at `/runpod-volume`; read `vol.path` inside the remote function, never at import time.
9. **Tasks bill until they return.** A `.spawn()`ed task that you never `wait()` or `cancel()`
   keeps its Pod running after your script exits.
10. **Native CUDA libraries go in `dependencies` too**, e.g. faster-whisper needs
    `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` or it silently falls back to CPU.
11. **Local Python must be 3.10–3.14.** Dev sessions and tasks ship code pickled by your
    interpreter, so the worker matches your local version. `rp flash deploy --python-version`
    sets it for deploys.
12. **A set `RUNPOD_API_KEY` wins over `rp login`.** A stale exported key causes 401s while the
    saved login is fine. Check with `runpodctl user`, then `unset RUNPOD_API_KEY` or export a
    good key.
13. **Check the artifact when a dependency needs torch.** Auto-exclusion drops `torch` only when
    it is listed directly. In `runpod` 2.0.0rc1, a package that depends on it (`peft`,
    `accelerate`, `sentence-transformers`) pulls `torch` into the artifact even on GPU images
    and with `--exclude torch`, so the artifact grows by hundreds of MB. Run
    `rp flash deploy --build-only` and check the size before deploying.
14. **Dev sessions run the runtime image's own `runpod`.** Deploys vendor your local package,
    but `rp flash dev` workers import the `runpod` baked into the built-in image. The
    `:latest` runtime images used by `runpod` 2.0.0rc1 predate `runpod.NetworkVolume` and
    `runpod.GlobalVolume`, so an app that declares one fails on the worker with
    `module 'runpod' has no attribute 'NetworkVolume'`. Deployed workers on the same images
    attach the volume, but `vol.path` raises `is not mounted in the current execution`; read
    the literal mount path instead (`/runpod-volume` for queue and API resources, the
    `mounts` key for tasks). An `AttributeError` on a `runpod.` name in a worker traceback
    means the image is behind your SDK.
15. **Teardown by app and environment:** `rp flash undeploy --app APP --env default -y`
    removes one environment's endpoints; `rp flash app delete APP` removes every environment.
    Then delete volumes you no longer need.

## Resources

- Setup & CLI: [reference/setup-and-cli.md](reference/setup-and-cli.md) · API: [reference/api.md](reference/api.md) · Patterns: [reference/patterns.md](reference/patterns.md) · Examples: [examples/](examples/)
- SDK source and upstream examples: https://github.com/runpod/runpod-python (`examples/apps/`)
- Docs: https://docs.runpod.io/sdk/overview · CLI: https://docs.runpod.io/sdk/cli · Migration: https://docs.runpod.io/sdk/migrate-from-flash
