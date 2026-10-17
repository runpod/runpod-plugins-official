---
lanes: [flash]
mcp: none
concepts: [flash, serverless-endpoint, worker, serverless-handler, gpu-type]
---

# Golden path 03 — Whisper — Variant B: from scratch with the Runpod SDK

**Status:** COVERED — live-verified on the Runpod SDK (`runpod` 2.0.0rc1) 2026-10-16 with
`rp flash dev main.py --once`: the worker returned the Gettysburg transcript in 70 s from cold.
The `runpod-flash` version was live-verified 2026-07-07. **Lane:** flash (code-first serverless). **When to use this variant:** you want a
**custom/lighter** worker than any Hub image — your own model size, your own I/O schema, your
own pre/post-processing — or no good Hub worker fits. You write a faster-whisper function,
iterate on a real GPU with `rp flash dev`, then `rp flash deploy`. For a heavy prebuilt model
with a solid Hub worker, prefer [Variant A — Hub](variant-a-hub.md). Shared schema, gotchas,
and cost notes live in the [folder README](README.md); the flash skill is at
[../../../flash/SKILL.md](../../../flash/SKILL.md).

## Prerequisites

- Python 3.10–3.14 and the Runpod SDK in the project environment:
  ```bash
  pip install "runpod>=2.0.0rc2"        # installs the rp CLI
  ```
- A Runpod API key for non-interactive use:
  ```bash
  export RUNPOD_API_KEY=...             # https://console.runpod.io/user/settings (or: rp login)
  ```

## Walkthrough

1. **Write the app — declare dependencies and GPU on the decorator.**
   ```python
   # main.py
   import runpod

   app = runpod.App("whisper")

   _MODEL = None


   @app.queue(
       gpu="AMPERE_16",                        # whisper base needs <2 GB; broad supply
       workers=(0, 3), idle_timeout=60,        # scale-to-zero
       dependencies=["faster-whisper", "av<19",              # av 19 drops an arg faster-whisper passes
                     "nvidia-cublas-cu12", "nvidia-cudnn-cu12"],  # CTranslate2 GPU libs
   )
   def transcribe(audio_url: str = "", audio_base64: str = "") -> dict:
       import base64, tempfile, urllib.request
       from faster_whisper import WhisperModel

       global _MODEL
       if _MODEL is None:                       # once per worker
           _MODEL = WhisperModel("base", device="cuda", compute_type="float16")

       with tempfile.NamedTemporaryFile(suffix=".audio") as f:
           if audio_url:
               f.write(urllib.request.urlopen(audio_url).read())
           else:
               f.write(base64.b64decode(audio_base64))
           f.flush()
           segments, info = _MODEL.transcribe(f.name)
           return {"text": "".join(s.text for s in segments).strip(), "language": info.language}


   @runpod.local_entrypoint
   def main():
       out = transcribe.remote(audio_url="https://github.com/runpod-workers/sample-inputs/raw/main/audio/gettysburg.wav")
       print(out)
       assert "four score" in out["text"].lower(), out
   ```
   Two rules matter here (both in [../../../flash/SKILL.md](../../../flash/SKILL.md)):
   **native CUDA libraries go in `dependencies` too** — `nvidia-cublas-cu12` +
   `nvidia-cudnn-cu12`, or faster-whisper silently falls back to CPU; and **load the model
   once per worker** with the module-level cache. The whole module ships to the worker, so the
   global works in dev and deploy alike.

2. **Check the build offline** (no account changes):
   ```bash
   rp flash deploy main.py --build-only
   ```

3. **Iterate on a real remote GPU.** This is where you catch the payload shape and the CUDA
   libraries before shipping:
   ```bash
   rp flash dev main.py --once           # temporary endpoint, runs main(), cleans up
   ```
   For repeated edits, run a background session as shown in the flash skill's *Autonomous dev
   loop* (`kill` stops it and deletes its endpoint); each save re-runs `main()` against the
   refreshed endpoint.

4. **Ship it:**
   ```bash
   rp flash deploy main.py               # app "whisper", environment "default"
   rp flash env get default --app whisper   # shows the endpoint id
   ```

## Verify it works

From Python:

```python
import runpod
transcribe = runpod.Queue(app="whisper", name="transcribe")
print(transcribe.remote(audio_url="https://github.com/runpod-workers/sample-inputs/raw/main/audio/gettysburg.wav"))
```

Over the Runpod job API, the function's keyword arguments are the `input` object:

```bash
curl -s https://api.runpod.ai/v2/<endpoint-id>/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"audio_url":"https://github.com/runpod-workers/sample-inputs/raw/main/audio/gettysburg.wav"}}'
```

Verified result (2026-10-16, dev session, cold):
```
{'language': 'en', 'text': 'Four score and seven years ago, our fathers brought forth on this continent a new nation, ...'}
```
The `runpod-flash` run measured cold ~55–75 s (image pull + model download) and warm <1 s.
For the first, cold call use `/run` + poll `/status/<id>`, or `.remote()` from the SDK, which
has no timeout by default.

## Variant-specific gotchas

- **The `input` keys are the function's parameter names.** `transcribe(audio_url=...)` takes
  `{"input": {"audio_url": ...}}`, the same plain contract as Variant A. (The `runpod-flash`
  version used one `input_data: dict` parameter and needed `{"input":{"input_data":{...}}}`.)
- **Arguments must be JSON-serializable** — pass a URL or base64, not bytes.
- **Native CUDA libraries must be listed in `dependencies`** — or faster-whisper runs on CPU.
- **Pin `av<19`.** PyAV 19 removed the `metadata_errors` argument that faster-whisper passes
  to `av.open`, so an unpinned install fails with `open() got an unexpected keyword argument
  'metadata_errors'`.
- **10 MB payload limit** — pass a URL for large audio.
- **The artifact is ~1.05 GB of the 1,500 MB cap**, mostly the cuDNN and cuBLAS wheels. Adding
  another large package can push it over; check with `--build-only`.

## Cost & cleanup (link back to README for shared)

Scale-to-zero (`workers=(0, 3)`) means ~$0 while idle. Teardown:

```bash
rp flash app delete whisper --yes       # every environment in the app
# or: runpodctl serverless delete <endpoint-id>
```

Full shared cost/cleanup and the 204-on-delete note are in the
[folder README](README.md#cost--cleanup-shared).
