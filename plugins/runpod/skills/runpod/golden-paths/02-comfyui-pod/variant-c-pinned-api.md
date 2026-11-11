---
lanes: [ssh]
mcp: none
concepts: [pod, exposed-port, container-disk, pod-command-exec]
status: live-verified
verified: "2026-11-09"
evals: [runpod/evals/comfyui-pinned-api]
---

# Golden path 02 — ComfyUI — Variant C: pinned, private, driven by the API

> **Status:** live-verified 2026-11-09 — step 2b on the official ComfyUI image through `/prompt`, `/history` and `/view` (see Tested example for the reused venv); step 2a on the PyTorch template on 2026-11-05 through `/history`. **Evals:** [comfyui-pinned-api](../../evals/comfyui-pinned-api.eval.md). Status key: [golden-paths README](../README.md#status-legend).

**Goal / Lane:** install an exact ComfyUI version on a GPU Pod the user already runs, keep it private, and generate one image through its HTTP API. **Lane:** a shell on the Pod (SSH or a command executor).

**When to use this variant:** an agent, not a person, drives ComfyUI; the install must be reproducible; and nothing may be published on the proxy. For a UI the user opens in a browser, use [Variant B](variant-b-prebuilt.md) (the default) or [Variant A](variant-a-from-scratch.md).

## Prerequisites

- A running GPU Pod with ≥ 16 GB VRAM and a shell on it. The default install (step 2a) needs an official PyTorch template (`runpod/pytorch`), whose system Python has CUDA torch with cuDNN. Any other image uses step 2b. A Pod on the official ComfyUI image already has ComfyUI: use [Variant B](variant-b-prebuilt.md) instead of a second install.
- About 15 GB free on the container disk (dependencies plus a 2.1 GB checkpoint).
- The [shared prerequisites](../README.md#before-you-run-any-path-shared-prerequisites).

## Walkthrough

Write the whole plan first, with a deadline on each step, and show it to the user.

**1. Pin and hash the inputs.** Pick a ComfyUI commit and a checkpoint revision. Record the SHA-256 of the source archive (`https://codeload.github.com/Comfy-Org/ComfyUI/tar.gz/<commit>`) and of the checkpoint (the LFS SHA-256 on the model's file page at that revision). Verify both on the Pod after the download; a mismatch stops the run.

```bash
curl -fL -o comfy-source.tar.gz https://codeload.github.com/Comfy-Org/ComfyUI/tar.gz/<commit>
echo "<sha256>  comfy-source.tar.gz" | sha256sum -c -
```

**2. Check the base image, then install.** Run this check before the install. It passes only when the system Python has CUDA torch and cuDNN loads (a small convolution on the GPU):

```bash
python3 -c 'import torch, torch.nn.functional as F; assert torch.cuda.is_available(); F.conv2d(torch.zeros(1,1,8,8,device="cuda"), torch.zeros(1,1,3,3,device="cuda")); print(torch.__version__, torch.version.cuda, torch.backends.cudnn.version())'
```

**2a. The check passes (official PyTorch template): reuse the base torch.** Inherit it and pin it with a constraints file. Without the constraints, `pip install -r requirements.txt` can upgrade torch to a build that does not match the host.

```bash
set -eu
mkdir comfy && tar -xzf comfy-source.tar.gz --strip-components=1 -C comfy
python3 -m venv --system-site-packages comfy-venv
python3 -m pip freeze | grep -E '^(torch|torchvision|torchaudio)==' > torch-constraints.txt
comfy-venv/bin/python -m pip install --no-input --no-cache-dir -c torch-constraints.txt -r comfy/requirements.txt
comfy-venv/bin/python -m pip freeze > installed-packages.txt
```

**2b. The check fails (any other image): use a fully isolated venv.** `--system-site-packages` on such an image lets pip treat torch as installed while its CUDA libraries are missing, and ComfyUI then fails with `ImportError: libcudnn.so.9`. Install torch into a plain venv instead. Pin torch, torchvision and torchaudio together in a constraints file; from the default index, the Linux torch wheels bring their CUDA and cuDNN libraries as separate packages. Their CUDA version must be at or below the host driver's (`nvidia-smi` prints `CUDA Version`). Add `requests`: ComfyUI imports it, and its `requirements.txt` does not list it. Allow 25 minutes: the wheels are several GB.

```bash
set -eu
mkdir comfy && tar -xzf comfy-source.tar.gz --strip-components=1 -C comfy
python3 -m venv comfy-venv
printf 'torch==<version>\ntorchvision==<version>\ntorchaudio==<version>\n' > torch-constraints.txt
comfy-venv/bin/python -m pip install --no-input --no-cache-dir -c torch-constraints.txt -r comfy/requirements.txt
comfy-venv/bin/python -m pip install --no-input --no-cache-dir 'requests==2.32.3'
comfy-venv/bin/python -m pip freeze > installed-packages.txt
```

For a torch build with a different CUDA version, add `--index-url https://download.pytorch.org/whl/cu<cuda>` to a separate torch install before the requirements. The live runs did not use that option.

After either install, run the same check with `comfy-venv/bin/python` before you continue.

**3. Download and check the checkpoint.**

```bash
curl -fL -o comfy/models/checkpoints/<file>.safetensors \
  https://huggingface.co/<repo>/resolve/<revision>/<file>.safetensors
echo "<sha256>  comfy/models/checkpoints/<file>.safetensors" | sha256sum -c -
```

**4. Start it on loopback with only core nodes.**

```bash
setsid timeout 900 comfy-venv/bin/python -s comfy/main.py --listen 127.0.0.1 --port <port> \
  --disable-all-custom-nodes --disable-api-nodes --disable-auto-launch \
  > comfy.log 2>&1 < /dev/null &
```

- `--listen 127.0.0.1` and a port that the Pod does not expose keep ComfyUI off the public proxy. ComfyUI has no authentication, so this is the only protection.
- `--disable-all-custom-nodes` and `--disable-api-nodes` run only the nodes in the pinned source.
- Ready means `GET /system_stats` returns 200. Poll it in short reads.

**5. Run one workflow through the API.** Send an API-format workflow (node ids mapped to `class_type` and `inputs`, as the UI's "Export (API)" writes it), not the UI's graph format.

1. `POST /prompt` with `{"prompt": <workflow>}`. Save the returned `prompt_id`, and check `node_errors` is empty. Send it once. A 200 means the job was queued, not that an image exists.
2. `GET /history/<prompt_id>` until the entry shows `status.completed: true` and `status_str: "success"`.
3. Read `outputs.<save-node-id>.images[]` from that entry: `filename`, `subfolder`, `type`. Do not build the filename from the prefix.
4. `GET /view?filename=<filename>&subfolder=<subfolder>&type=output` returns the PNG. Save it and record its SHA-256 and pixel size.

## Verify it works

- `/system_stats` 200 before the workflow.
- `/history/<prompt_id>` reports `success` with one output file.
- The PNG has the requested size and a recorded SHA-256. Look at it before calling it a good result.

## Variant-specific gotchas

- **Smoke settings give poor images.** Four sampler steps at 256 × 256 prove the pipeline, not the quality. Use the model's normal steps and resolution for a result the user will judge.
- **Do not resubmit `/prompt` after an unclear result.** Read `/history` (and `/queue`) first; a second POST makes a second image.
- **Torch drift.** If the install log shows torch being replaced, stop: the constraints file is missing or wrong.
- **The base image decides the install.** `--system-site-packages` is safe only when the base check passes. On another image it gives a venv whose torch cannot load cuDNN (`ImportError: libcudnn.so.9`). Use step 2b.
- **A plain venv lacks `requests`.** ComfyUI imports it at startup, and the pinned `requirements.txt` does not list it, so without it ComfyUI exits about 15 s after start with `ModuleNotFoundError: No module named 'requests'`. Step 2b installs it. On step 2a the base image supplies it.

## Cost & cleanup

The Pod bills while it exists; stopping ComfyUI does not stop billing. Stop the process group, confirm no listener on the port, and delete the Pod only if this conversation created it for the test. Shared cost notes: [README](README.md#cost--cleanup-shared).

## Tested example

Live run on 2026-11-05: an A40 Pod on the PyTorch 2.8 / CUDA 12.8 template, no volume.

| Item | Value |
|---|---|
| ComfyUI | v0.3.67, commit `f2bb3230b796f6a486894fc3b597db2c0b9538c9`, archive SHA-256 `c2a65dc160a398ee8b2fea0a09a68ab4132a0619da62fa81e78eee7fef38539b` |
| Torch constraints | `torch==2.8.0`, `torchvision==0.23.0`, `torchaudio==2.8.0` |
| Checkpoint | `Comfy-Org/stable-diffusion-v1-5-archive` at `9cfd069101959ca3828bf9c04a4419870832b74f`, `v1-5-pruned-emaonly-fp16.safetensors`, 2,132,696,762 bytes, SHA-256 `e9476a13728cd75d8279f6ec8bad753a66a1957ca375a1464dc63b37db6e3916` |
| Workflow | `CheckpointLoaderSimple` → two `CLIPTextEncode` → `EmptyLatentImage` 256 × 256 → `KSampler` (seed 41235, 4 steps, cfg 5, euler) → `VAEDecode` → `SaveImage` (prefix `workspace_qa`) |
| Result | `/history` `success`, output `workspace_qa_00001_.png`, 5.2 s generation; PNG 256 × 256, 112,808 bytes |

Step 2b was live-verified on 2026-11-09 on an A40 Pod with the official ComfyUI image (`runpod/comfyui`), on the same pinned source, checkpoint and workflow:

- With the step 2a install, step 1 passed, and the install failed with `ImportError: libcudnn.so.9`.
- The full step 2b install from scratch (constraints `torch==2.8.0`, `torchvision==0.23.0`, `torchaudio==2.8.0`) passed all setup steps on the third attempt. The service then exited with the missing `requests` error.
- A fourth attempt with `requests==2.32.3` passed the install. Its checkpoint download then hit the step deadline on a slow network. The passing run reused the venv from the third attempt, with `requests==2.32.3` added. `/system_stats` was ready in about 25 s, and `/prompt`, `/history` and `/view` each returned 200 with a 256 × 256 PNG.

The `/view` call was not part of that run: the PNG was read from `comfy/output/` and hash-checked. These pins prove the procedure. They are not a version recommendation.
