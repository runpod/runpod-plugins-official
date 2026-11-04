"""Dual-mode Runpod handler — whisper (speech -> text) worked example.

One file, two modes, selected by the MODE_TO_RUN env var:

  MODE_TO_RUN=pod         (default) start.sh runs SSH + Jupyter and sleeps.
                          You SSH in and run `python handler.py` to exercise the
                          handler ONCE against a sample input — the interactive
                          dev loop.
  MODE_TO_RUN=serverless  start.sh calls this file, which hands `handler` to the
                          Runpod serverless SDK. Same code, now queue-driven.

The invariant that makes the loop work: the model is loaded at IMPORT time (module
level), and `handler(event)` is the exact function both modes call. So whatever you
prove with `python handler.py` on the pod is what the serverless worker will do.
"""

import os
import base64
import asyncio
import tempfile
import urllib.request

import runpod

MODE_TO_RUN = os.getenv("MODE_TO_RUN", "pod")
MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")  # tiny|base|small|medium|large-v3

# Keep the model cache on local disk. Loading weights straight off a network volume
# reads every byte over the network; to reuse downloads across workers, wrap the load
# below in VolumeCache (see the README's "Heavy things -> network volume").
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/app/whisper-cache")

# --- Load the model ONCE, at import (cold-start rule). Runs in BOTH modes. -------
print("------- BOOT -------")
print(f"mode={MODE_TO_RUN} model={MODEL_SIZE} cache={MODEL_CACHE_DIR}")

try:
    import torch
    _HAS_CUDA = torch.cuda.is_available()
except Exception:
    _HAS_CUDA = False

_DEVICE = "cuda" if _HAS_CUDA else "cpu"
_COMPUTE = "float16" if _HAS_CUDA else "int8"
print(f"device={_DEVICE} compute_type={_COMPUTE}")

from faster_whisper import WhisperModel

_MODEL = WhisperModel(
    MODEL_SIZE, device=_DEVICE, compute_type=_COMPUTE, download_root=MODEL_CACHE_DIR
)
print("------- MODEL READY -------")


def _resolve_audio(inp: dict) -> str:
    """Accept audio as a URL or base64 blob; write it to a temp file to transcribe."""
    if inp.get("audio_url"):
        fd, path = tempfile.mkstemp(suffix=".audio")
        os.close(fd)
        urllib.request.urlretrieve(inp["audio_url"], path)
        return path
    if inp.get("audio_base64"):
        fd, path = tempfile.mkstemp(suffix=".audio")
        with os.fdopen(fd, "wb") as f:
            f.write(base64.b64decode(inp["audio_base64"]))
        return path
    raise ValueError("input must include 'audio_url' or 'audio_base64'")


async def handler(event):
    """The one function both modes call. event = {'input': {...}}."""
    inp = event.get("input", {}) or {}
    audio_path = _resolve_audio(inp)
    segments, info = _MODEL.transcribe(audio_path, language=inp.get("language"))
    text = "".join(seg.text for seg in segments).strip()
    return {"text": text, "language": info.language, "duration": round(info.duration, 2)}


if MODE_TO_RUN == "pod":
    # Interactive dev loop: run the handler once against a known sample and print it.
    async def _main():
        sample = os.getenv(
            "SAMPLE_AUDIO_URL",
            "https://github.com/openai/whisper/raw/main/tests/jfk.flac",
        )
        result = await handler({"input": {"audio_url": sample}})
        print("RESULT:", result)

    asyncio.run(_main())
else:
    # Serverless: identical handler, now driven by the Runpod queue.
    runpod.serverless.start(
        {
            "handler": handler,
            "concurrency_modifier": lambda current: int(os.getenv("CONCURRENCY_MODIFIER", "1")),
        }
    )
