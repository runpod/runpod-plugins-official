---
concepts: [flash, serverless-handler, job, container-disk]
---

# Legacy `runpod-flash` reference

Use this only to maintain a project that still imports `runpod_flash`. `runpod-flash` is
deprecated on October 29, 2026 and gets no fixes after that date; propose
[migrating](migrate-from-runpod-flash.md). New code goes on the Runpod SDK
([../SKILL.md](../SKILL.md)). `flash --help` is authoritative for the installed version.

## Setup and CLI

```bash
uv tool install runpod-flash          # Python 3.10-3.13; or: pip install runpod-flash
flash login                           # saves a key to ~/.runpod/config.toml (--no-open for headless)
flash init my-project                 # scaffold (writes AGENTS.md + CLAUDE.md)
flash dev                             # local server on :8888; functions run on remote workers
flash dev --auto-provision            # pre-provision endpoints to skip the first cold start
flash deploy [--env NAME]             # build (<=1500 MB, torch excluded) and deploy
flash app list | get APP | delete APP
flash env list | create NAME | get NAME | delete NAME
flash undeploy NAME [--force]         # one endpoint
flash update                          # upgrade the CLI
```

1.21.0 and later print a deprecation notice; `RUNPOD_FLASH_SILENCE_DEPRECATION=1` silences it.

## Modes

```python
from runpod_flash import Endpoint, GpuGroup, PodTemplate

@Endpoint(name="worker", gpu=GpuGroup.AMPERE_80, workers=5, dependencies=["torch"])
async def compute(data):                       # queue-based: one function, one endpoint
    import torch
    return {"sum": torch.tensor(data, device="cuda").sum().item()}

api = Endpoint(name="my-api", gpu=GpuGroup.ADA_24, workers=(1, 5))
@api.post("/predict")                          # load-balanced: routes share one worker pool
async def predict(data: list[float]): ...

server = Endpoint(name="srv", image="org/img:tag", gpu=GpuGroup.AMPERE_80,
                  template=PodTemplate(containerDiskInGb=100))   # client mode: prebuilt worker image
ep = Endpoint(id="abc123")                                       # client mode: existing endpoint
job = await ep.runsync({"prompt": "hello"}, timeout=120)
```

`name=` only is decorator mode; `image=` or `id=` is client mode. `gpu=` and `cpu=` are
exclusive. A class `@Endpoint` whose `__init__` loads a model runs that load once per worker.

## Defaults

`Endpoint` defaults: `workers` `(0, 1)`, `idle_timeout` 60 seconds, `execution_timeout_ms` 0
(unlimited), `flashboot=True`, `min_cuda_version` 12.8 (the `runpod/flash` image needs it; lower
it only with an image that supports older CUDA), `PodTemplate(containerDiskInGb=64)`. These
differ from the platform defaults.

## Dev server loop

```bash
flash dev > /tmp/flash-dev.log 2>&1 &
for i in $(seq 1 60); do grep -q "flash dev  localhost:" /tmp/flash-dev.log && break; sleep 2; done
URL=$(grep -o "localhost:[0-9]*" /tmp/flash-dev.log | head -1)   # the port bumps if 8888 is taken
```

- Routes are namespaced by file: `main.py`'s `/predict` is `/main/predict`.
- Load-balanced routes take the handler argument at the top level: `def predict(data)` wants
  `{"data": {...}}`.
- Queue endpoints are served at `/main/runsync` and want the body double-wrapped:
  `def synthesize(data)` wants `{"input": {"data": {...}}}`. The worker calls
  `handler(**job_input)`, so `input` keys must match parameter names, and an empty `input` is
  rejected with `Job has missing field(s): id or input`.

## Gotchas

1. **`flash dev` ships only the function body.** Module-level constants and imports raise
   `NameError` on the worker under `flash dev`, while `flash deploy` imports the whole module
   and hides the bug. Put imports and helpers inside the function. To cache a model in
   function form, use a module global set inside the body
   (`global _M` / `try: _M` / `except NameError: _M = load()`).
2. **Every decorated function and client call needs `await`.**
3. **`runsync` times out after 60 seconds**; raise `timeout=` or use `run()` + `job.wait()` for
   cold starts.
4. **A set `RUNPOD_API_KEY` overrides `flash login`.** A bad key logs
   `GraphQL request failed: 401` while `flash dev` still prints its ready line.
5. **Teardown with `flash app delete APP`.** `flash undeploy list` can miss a deployed app.
6. **10 MB payload limit**; native CUDA libraries go in `dependencies`; `system_dependencies`
   add to cold start; automatic GPU switching needs `workers` ≥ 5. These carry over to the SDK.

## Exact rules

- [flash](../../runpod-usage/concepts/flash.yaml)
