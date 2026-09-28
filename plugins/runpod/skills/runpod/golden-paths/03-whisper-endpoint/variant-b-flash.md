---
lanes: [flash]
mcp: none
concepts: [flash, serverless-endpoint, worker, serverless-handler, gpu-type]
---

# Golden path 03 — Whisper — Variant B: from scratch with flash

**Status:** COVERED — live-verified 2026-07-07. **Lane:** flash (code-first
serverless). **When to use this variant:** you want a **custom/lighter** worker than
any Hub image — your own model size, your own I/O schema, your own pre/post-
processing — or no good Hub worker fits. You write and own a faster-whisper
handler, iterate on a real GPU with `flash dev`, then `flash deploy`. For a heavy
prebuilt model with a solid Hub worker, prefer
[Variant A — Hub](variant-a-hub.md) (flash would just be re-implementing it).
Shared schema, gotchas, and cost notes live in the [folder README](README.md); the
flash skill is at [../../../flash/SKILL.md](../../../flash/SKILL.md).

## Prerequisites

- Python 3.10–3.13 and the flash CLI:
  ```bash
  uv tool install runpod-flash          # or: pip install runpod-flash
  ```
- A Runpod API key exported for non-interactive use:
  ```bash
  export RUNPOD_API_KEY=...             # https://console.runpod.io/user/settings
  ```

## Walkthrough

1. **Write the handler — declare deps + GPU IN the decorator (NOT pyproject.toml).**
   flash ships only the function body to the worker, so imports and the model cache
   live *inside* the body; the pip deps and GPU tier are declared on `@Endpoint`.
   ```python
   # whisper_worker.py  — deps + GPU declared in the decorator (NOT pyproject.toml)
   from runpod_flash import Endpoint, GpuGroup

   @Endpoint(
       name="whisper-flash",
       gpu=GpuGroup.AMPERE_16,                 # whisper base needs <2GB; broad supply
       workers=(0, 3), idle_timeout=60,        # scale-to-zero
       dependencies=["faster-whisper",
                     "nvidia-cublas-cu12", "nvidia-cudnn-cu12"],  # CTranslate2 GPU libs
   )
   async def transcribe(input_data: dict) -> dict:
       import base64, tempfile, urllib.request
       from faster_whisper import WhisperModel
       global _MODEL                            # load once per worker (see flash gotcha 11)
       try: _MODEL
       except NameError: _MODEL = WhisperModel("base", device="cuda", compute_type="float16")
       # download input_data["audio_url"] (or decode audio_base64) -> temp file -> transcribe
   ```
   Two flash rules are load-bearing here (both from
   [../../../flash/SKILL.md](../../../flash/SKILL.md)): **native CUDA libs go in
   `dependencies=[]` too** — `nvidia-cublas-cu12` + `nvidia-cudnn-cu12`, or
   CTranslate2/faster-whisper silently falls back to CPU (gotcha 12); and **load the
   model once per worker** via the module-level `global _MODEL` cache *inside* the
   body so it works under both `flash dev` and `flash deploy` (gotchas 1 + 11).

2. **Scaffold a project** (outside your git repos):
   ```bash
   flash init ~/whisper-flash            # scaffold (writes AGENTS.md + CLAUDE.md)
   ```

3. **Iterate on a real remote GPU with hot-reload** — cheap, and this is where you
   catch the payload shape before shipping:
   ```bash
   flash dev                             # runs the function on a remote GPU, streams live worker logs
   ```

4. **Ship it** — builds an artifact and deploys a stable endpoint:
   ```bash
   flash deploy                          # returns an endpoint id
   ```

## Verify it works

Call it over the Runpod job API. **The payload nests under the handler's parameter
name** — because the handler param is `input_data`, the wire body is
`{"input":{"input_data":{...}}}`, not a plain `{"input":{...}}` (see the gotcha
below):

```bash
curl -s https://api.runpod.ai/v2/<endpoint-id>/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"input_data":{"audio_url":"https://github.com/runpod-workers/sample-inputs/raw/main/audio/gettysburg.wav"}}}'
```

Verified: cold ~55–75 s (image pull + model download), **warm <1 s**; returns
`{text, language, ...}` with the correct Gettysburg transcript ("Four score and
seven years ago…"). For the first (cold) call, cold start can exceed `runsync`'s
60 s — use `/run` + poll `/status/<id>`, or `ep.runsync(data, timeout=120)` from the
flash client, then `runsync` once warm.

## Variant-specific gotchas

- **Raw-HTTP callers nest under the parameter name** (flash gotcha 10). When
  something other than the flash client hits the deployed endpoint
  (`curl .../runsync`, another service), the wire body is
  `{"input": {"<handler_param_name>": <value>}}`. A handler
  `async def transcribe(input_data: dict)` therefore expects
  `{"input":{"input_data":{...}}}`. **Name the parameter `input`** if you want the
  plain Runpod contract (matching Variant A's schema). The flash client's
  `ep.runsync(x)` hides this — it's only a gotcha for external callers.
- **Only the function body ships to the worker** (flash gotcha 1). Put imports and
  any module-level constants/helpers *inside* the decorated body, or `flash dev`
  raises `NameError` (and `flash deploy` can mask it). This is why the model cache
  is written as an in-body `global _MODEL` (gotcha 11).
- **Native CUDA libs must be listed in `dependencies=[]`** (flash gotcha 12) —
  `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` alongside `faster-whisper`, or it
  silently runs on CPU.
- **`runsync` is 60 s / payload limit 10 MB** (flash gotchas 9 + 6) — pass a URL for
  large audio, not bytes; use `/run` + poll for cold starts.

## Cost & cleanup (link back to README for shared)

Scale-to-zero (`workers=(0, 3)` in the decorator) means ~$0 while idle. Teardown:

```bash
flash app delete whisper-flash          # reliable even if `flash undeploy list` shows "no endpoints"
# or: runpodctl serverless delete <endpoint-id>
```

Full shared cost/cleanup and the 204-on-delete note are in the
[folder README](README.md#cost--cleanup-shared).
