# Migrate a runpod-flash project to the Runpod SDK

## Prompt

This repo uses runpod-flash: `main.py` has `from runpod_flash import Endpoint, GpuGroup`, a
queue `@Endpoint(name="embed", gpu=GpuGroup.ADA_24, dependencies=["sentence-transformers"])`
function, and an `api = Endpoint(name="search", cpu="cpu5c-2-4")` with `@api.post("/query")`.
CI runs `flash deploy`. I heard runpod-flash is deprecated. Move it over.

## Expected behavior

The agent should:

1. Inventory the `runpod_flash` imports, every `Endpoint`, and every `flash` CLI call (CI too)
2. Check the known differences (multi-file project, `id=`/`template=`, path params, volume lists)
   and report any that apply before converting
3. Install `runpod>=2.0.0rc1`, convert to `runpod.App` with `@app.queue` for `embed` and an
   `@app.api` class with `@runpod.post("/query")` for `search`, and add a
   `@runpod.local_entrypoint`
4. Update CI from `flash deploy` to `rp flash deploy`
5. Smoke-test with `rp flash dev main.py --once` before deploying
6. Tell the user the load-balanced route's raw HTTP body changes (no `{"data": ...}` wrapper),
   that default `workers` is now `(0, 3)`, and to remove the old runpod-flash endpoints after
   the new deploy works

## Assertions

- Removes every `runpod_flash` import; uses `import runpod`
- `embed` becomes `@app.queue(gpu="ADA_24" or GpuGroup.ADA_24, dependencies=[...])`
- `search` becomes an `@app.api` class whose POST method takes one `body` argument
- CI calls `rp flash deploy`, not `flash deploy`
- Runs or recommends `rp flash dev main.py --once` before `rp flash deploy`
- Mentions the `workers` default change or sets `workers` explicitly
- Does NOT delete the old endpoints before the new deployment is confirmed
- Does NOT claim the October 29, 2026 deprecation stops existing endpoints
