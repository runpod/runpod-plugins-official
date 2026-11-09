---
concepts: [pod, exposed-port, container-disk, pod-command-exec]
---

# vLLM on a Pod you already have

Use this recipe when the user already runs a GPU Pod on a general image (for example an official PyTorch template) and wants vLLM installed and served on it, with no new Pod and no image change. The other products are in [SKILL.md](../SKILL.md#step-2-choose-the-product). For a new Pod, the stock `vllm/vllm-openai` image in [pod.md](pod.md) is faster.

The service stays private: it listens on `127.0.0.1` on a port the Pod does not expose, so only a shell on the Pod can call it. Every step runs through a shell on the Pod (SSH or a command executor).

## Plan

Write the full plan before you run a step, and show it to the user. Each step has a deadline.

| Step | What it does | Deadline |
|---|---|---|
| 1. Install | fresh venv, pinned `vllm==<version>`, record `pip freeze` | 20 min |
| 2. Download | each model file from an exact Hugging Face revision, with its SHA-256 | per file: 2 min small, 15 min weights |
| 3. Check | pinned versions import, CUDA is available | 1 min |
| 4. Serve | `vllm serve` on loopback with `VLLM_API_KEY`; health `GET /v1/models` | startup 5 min, runtime bounded |
| 5. Verify | missing/wrong key gives 401, one real request completes, the metrics counter matches | 1 min each |
| 6. Stop | stop the server; delete the Pod only if this conversation created it for a test | — |

## 1. Install into a fresh venv when the torch versions differ

Each vLLM release pins one torch version. Read it before you install (`pip download vllm==<version> --no-deps` and the wheel metadata, or the vLLM release notes) and compare it with the base image's torch (`python3 -c 'import torch; print(torch.__version__, torch.version.cuda)'`).

- **They differ** (the usual case): make a fresh venv. A venv that inherits system packages would replace the base image's torch. `python3 -m venv venv` and install only into it.
- **They match**: `python3 -m venv --system-site-packages venv` reuses the base torch and saves the download. Pin torch with a constraints file so the install cannot replace it. This is the general rule in [on-pod-setup.md](../../runpod-usage/reference/on-pod-setup.md).

```bash
set -eu
python3 -m venv venv
venv/bin/python -m pip install --no-input --no-cache-dir 'vllm==<version>'
venv/bin/python -m pip freeze > installed-packages.txt
venv/bin/python -c 'import torch, vllm; print("vllm", vllm.__version__, "torch", torch.__version__, "cuda", torch.version.cuda)'
```

Put the venv on the container disk, not on a network volume: an install writes many small files. Size the container disk for the venv (about 10 GB) plus the weights.

## 2. Download pinned, hashed files

Download from an exact revision, not `main`: `https://huggingface.co/<repo>/resolve/<commit>/<file>`. Record the expected SHA-256 for each file before the download (the model page's file list shows the LFS SHA-256 for weight files; hash small files yourself from the same revision) and verify every file on the Pod after the download. A hash mismatch stops the plan: report it, do not retry with a different revision.

```bash
curl -fL --max-time 900 -o models/<name>/model.safetensors \
  https://huggingface.co/<repo>/resolve/<commit>/model.safetensors
echo "<sha256>  models/<name>/model.safetensors" | sha256sum -c -
```

Gated weights need `HF_TOKEN` in the environment of the download step only. Never print it.

## 3. Check before you serve

```bash
venv/bin/python -c 'import torch, vllm; assert vllm.__version__ == "<version>"; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))'
```

## 4. Serve on loopback with a key

Generate a random key on the Pod (`python3 -c 'import secrets; print(secrets.token_hex(24))'`) and pass it as the `VLLM_API_KEY` environment variable, never as `--api-key` on the command line, where the process list shows it. Never print it.

```bash
env VLLM_API_KEY=<generated> VLLM_NO_USAGE_STATS=1 HF_HUB_OFFLINE=1 \
  venv/bin/vllm serve models/<name> --served-model-name <served-id> \
  --host 127.0.0.1 --port <port> --max-model-len <len> --gpu-memory-utilization <fraction>
```

- `--host 127.0.0.1` and a port that is not in the Pod's exposed ports keep the server off the proxy. To publish it later, see [pod.md](pod.md); the key then becomes the only protection.
- `HF_HUB_OFFLINE=1` makes vLLM load only the verified files.
- Start the server so it outlives the shell (`setsid ... > serve.log 2>&1 < /dev/null &`) and give it a runtime limit (`timeout <seconds> ...`), unless a service manager on the Pod owns it.
- Ready means `GET /v1/models` with the key returns 200. A running process is not ready. Read `serve.log` with [boot-log-triage.md](boot-log-triage.md) while you wait.

## 5. Verify

Run all three checks from a shell on the Pod.

1. **Auth.** A request with no key and a request with a wrong key both return 401. Build the wrong header at runtime; never read the real key in a check.
2. **Inference.** One `POST /v1/chat/completions` with `max_tokens` small (8 is enough) returns 200, the served model id, and a finish reason. Quote the actual text. A small model often ignores an exact-wording instruction; that is a model result, not a server failure.
3. **No replay.** `GET /metrics` exposes `vllm:request_success_total`. Read it after the request: it equals the number of requests you sent. Read it again after any client retry or page reload: if it rose, a request was sent twice.

```bash
curl -s http://127.0.0.1:<port>/metrics | grep '^vllm:request_success_total{'
```

## 6. Stop

Stop the server process group and confirm that the port has no listener and the GPU memory is free (`nvidia-smi --query-gpu=memory.used --format=csv`). Stopping vLLM does not stop Pod billing. Delete the Pod only when this conversation created it for a test.

## Tested example

Live run on 2026-11-05: an A40 Pod on the PyTorch 2.8 / CUDA 12.8 template, 50 GB container disk, no volume.

| Item | Value |
|---|---|
| vLLM | `0.11.2` in a fresh venv (it needs torch 2.9; the base has 2.8) |
| Model | `Qwen/Qwen2.5-0.5B-Instruct` at revision `7ae557604adf67be50417f59c2c2f167def9a775`, 7 files, 999,586,347 bytes, all SHA-256 verified |
| Serve flags | `--dtype half --max-model-len 1024 --max-num-seqs 1 --gpu-memory-utilization 0.25 --enforce-eager` |
| Results | missing key 401, wrong key 401; streamed request 200 with finish reason `length` at 8 tokens; `vllm:request_success_total` 1.0 before and after a page reload |

These pins prove the procedure. They are not a version recommendation: pick the current vLLM release the model needs.

## Exact rules

- [pod](../../runpod-usage/concepts/pod.yaml) · [exposed-port](../../runpod-usage/concepts/exposed-port.yaml) · [container-disk](../../runpod-usage/concepts/container-disk.yaml)
