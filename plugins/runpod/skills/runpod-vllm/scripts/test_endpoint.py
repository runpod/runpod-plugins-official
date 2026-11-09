#!/usr/bin/env python3
"""End-to-end check of a vLLM OpenAI-compatible server on Runpod.

Works against any of the three vLLM setups the runpod-vllm skill deploys:
  Pod:                      https://<pod-id>-8000.proxy.runpod.net/v1          (key: the Pod's VLLM_API_KEY)
  Load-balancing endpoint:  https://<endpoint-id>.api.runpod.ai/v1              (key: RUNPOD_API_KEY)
  Queue endpoint (Hub):     https://api.runpod.ai/v2/<endpoint-id>/openai/v1    (key: RUNPOD_API_KEY)

Usage:
  pip install openai
  python3 test_endpoint.py --base-url <url>/v1 --api-key-env RUNPOD_API_KEY --model <served-model-id> \
      [--wait-for-ready 1800] [--skip-tools] [--thinking-switch] [--vision] [--json out.json]

The key can come from the environment instead of argv (so it stays out of `ps`):
  --api-key-env RUNPOD_API_KEY   (or VLLM_API_KEY for a Pod); RUNPOD_API_KEY is the default.

Checks: the server lists the model, a chat completion returns text, a streamed completion
returns chunks (time to first token), a tool call names the right function, and optionally
the Qwen-style thinking switch and an image input. Exits 1 if any enabled check fails.
"""

import argparse
import json
import os
import sys
import time

RESULTS = []
ARGS = None

# A 48x48 PNG as a data URI, so the vision check does not depend on the server
# being able to fetch a remote URL.
IMAGE_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAIAAADYYG7QAAAAQ0lE"
    "QVR4nO3OMREAMAwDsSAxfygFUSSdisFLJv09AM1Nql9ZcqoHCAgICAgICAgICAgICAgICAgICA"
    "gICAgICGgP9AFzCR7ihS3OIQAAAABJRU5ErkJggg=="
)


def reasoning_of(obj):
    """vLLM names the thinking field `reasoning`; older versions used `reasoning_content`."""
    return getattr(obj, "reasoning", None) or getattr(obj, "reasoning_content", None) or ""


def tool_call_ok(name, arguments, want_name="get_weather", want_city="reykjavik"):
    """True when a tool call names the right function and its arguments are a JSON object with the city."""
    try:
        args = json.loads(arguments)
    except (TypeError, ValueError):
        return False
    city = args.get("city") if isinstance(args, dict) else None
    return name == want_name and isinstance(city, str) and want_city in city.lower()


def record(name, passed, detail="", elapsed=None):
    entry = {"test": name, "passed": bool(passed), "elapsed_s": elapsed, "detail": detail}
    RESULTS.append(entry)
    mark = "PASS" if passed else "FAIL"
    timing = f" [{elapsed:.1f}s]" if elapsed is not None else ""
    print(f"[{mark}]{timing} {name} -- {detail}", flush=True)
    return entry


def finish():
    summary = {
        "base_url": ARGS.base_url,
        "model": ARGS.model,
        "all_passed": all(r["passed"] for r in RESULTS),
        "tests": RESULTS,
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    if ARGS.json:
        with open(ARGS.json, "w") as f:
            json.dump(summary, f, indent=2, default=str)
    sys.exit(0 if summary["all_passed"] else 1)


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True, help="OpenAI base URL, ending in /v1")
    ap.add_argument("--api-key", help="API key; prefer --api-key-env so the key is not in argv")
    ap.add_argument("--api-key-env", default="RUNPOD_API_KEY",
                    help="environment variable to read the key from when --api-key is not given")
    ap.add_argument("--model", required=True, help="served model id (GET /v1/models)")
    ap.add_argument("--wait-for-ready", type=int, default=0,
                    help="seconds to keep polling /models through a cold start (default: fail fast)")
    ap.add_argument("--timeout", type=float, default=600.0, help="per-request timeout in seconds")
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--skip-tools", action="store_true", help="the server has no tool-call parser")
    ap.add_argument("--thinking-switch", action="store_true",
                    help="also test chat_template_kwargs enable_thinking=false (Qwen3-style models)")
    ap.add_argument("--vision", action="store_true", help="also test an image input (multimodal models)")
    ap.add_argument("--json", help="write the summary JSON to this path")
    ARGS = ap.parse_args()
    api_key = ARGS.api_key or os.environ.get(ARGS.api_key_env)
    if not api_key:
        ap.error(f"no API key: pass --api-key or set {ARGS.api_key_env}")

    from openai import OpenAI  # imported here so the pure helpers can be tested without the SDK

    client = OpenAI(base_url=ARGS.base_url, api_key=api_key, timeout=ARGS.timeout)

    # 0. Wait for the server: covers image pull, weight download, compile.
    t0 = time.monotonic()
    deadline = t0 + max(ARGS.wait_for_ready, 0)
    while True:
        try:
            remaining = deadline - time.monotonic()
            probe = client.with_options(timeout=min(ARGS.timeout, max(remaining, 10.0)), max_retries=0)
            served = [m.id for m in probe.models.list().data]
            record("wait_ready", ARGS.model in served, f"served models: {served}", time.monotonic() - t0)
            if ARGS.model not in served:
                finish()
            break
        except Exception as e:  # noqa: BLE001 - any error means "not ready yet"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                record("wait_ready", False, f"{type(e).__name__}: {e}", time.monotonic() - t0)
                finish()
            time.sleep(min(15.0, remaining))

    # 1. Chat completion. The first request after a boot is often the slowest.
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model=ARGS.model,
            messages=[{"role": "user", "content": "Explain in two sentences what a GPU is."}],
            max_tokens=ARGS.max_tokens,
        )
        msg = r.choices[0].message
        text = (msg.content or "").strip()
        elapsed = time.time() - t0
        tok = r.usage.completion_tokens if r.usage else 0
        e = record("chat", bool(text),
                   f"{tok} tok, {tok / elapsed:.1f} tok/s, finish={r.choices[0].finish_reason}", elapsed)
        e["output_preview"] = text[:300]
        e["reasoning_preview"] = reasoning_of(msg)[:300]
    except Exception as e:  # noqa: BLE001
        record("chat", False, f"{type(e).__name__}: {e}", time.time() - t0)

    # 2. Streaming, with time to first token (thinking tokens count as the first token).
    t0 = time.time()
    try:
        stream = client.chat.completions.create(
            model=ARGS.model,
            messages=[{"role": "user", "content": "Write one haiku about GPUs."}],
            max_tokens=ARGS.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        ttft, chunks, usage, parts = None, 0, None, []
        for chunk in stream:
            if not chunk.choices:
                usage = chunk.usage
                continue
            delta = chunk.choices[0].delta
            piece = reasoning_of(delta) or delta.content
            if piece:
                if ttft is None:
                    ttft = time.time() - t0
                parts.append(piece)
                chunks += 1
        elapsed = time.time() - t0
        ok = ttft is not None
        detail = f"TTFT {ttft:.2f}s, {chunks} chunks" if ok else "no content chunks"
        if usage and elapsed > 0:
            detail += f", {usage.completion_tokens / elapsed:.1f} tok/s"
        e = record("stream", ok, detail, elapsed)
        e["ttft_s"] = ttft
        e["output_preview"] = "".join(parts)[:300]
    except Exception as e:  # noqa: BLE001
        record("stream", False, f"{type(e).__name__}: {e}", time.time() - t0)

    # 3. Tool calling (needs --enable-auto-tool-choice and a --tool-call-parser on the server).
    if not ARGS.skip_tools:
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=ARGS.model,
                messages=[{"role": "user", "content": "What's the weather in Reykjavik right now? Use the tool."}],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the current weather for a city",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }],
                tool_choice="auto",
                max_tokens=ARGS.max_tokens,
            )
            calls = r.choices[0].message.tool_calls or []
            ok = any(tool_call_ok(c.function.name, c.function.arguments) for c in calls)
            record("tool_call", ok, f"{[(c.function.name, c.function.arguments) for c in calls]}",
                   time.time() - t0)
        except Exception as e:  # noqa: BLE001
            record("tool_call", False, f"{type(e).__name__}: {e}", time.time() - t0)

    # 4. Thinking switch (Qwen3-style chat templates).
    if ARGS.thinking_switch:
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=ARGS.model,
                messages=[{"role": "user", "content": "What is 17 * 23? Answer with just the number."}],
                max_tokens=256,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            msg = r.choices[0].message
            text = msg.content or ""
            record("thinking_off", "391" in text and not reasoning_of(msg).strip(),
                   f"answer: {text[:80]!r}", time.time() - t0)
        except Exception as e:  # noqa: BLE001
            record("thinking_off", False, f"{type(e).__name__}: {e}", time.time() - t0)

    # 5. Image input (multimodal models).
    if ARGS.vision:
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=ARGS.model,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": IMAGE_URL}},
                    {"type": "text", "text": "Describe this image in one sentence."},
                ]}],
                max_tokens=ARGS.max_tokens,
            )
            text = r.choices[0].message.content or ""
            record("vision", bool(text.strip()), f"answer: {text[:100]!r}", time.time() - t0)
        except Exception as e:  # noqa: BLE001
            record("vision", False, f"{type(e).__name__}: {e}", time.time() - t0)

    finish()


if __name__ == "__main__":
    main()
