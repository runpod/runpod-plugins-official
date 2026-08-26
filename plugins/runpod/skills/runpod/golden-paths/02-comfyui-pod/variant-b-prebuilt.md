# Golden path 02 — ComfyUI — Variant B: prebuilt official image

**Status:** COVERED — live-verified 2026-07-07 on pod `7ydkt5vs4fst25` (RTX 4090,
$0.69/hr). **Lane:** runpodctl.
**When to use this variant:** the default. You want ComfyUI up reliably with the
least effort — creation + poll, no SSH install, no `python main.py`. Reach for
[Variant A — from scratch](variant-a-from-scratch.md) only when you need custom
nodes, pinned versions, or a lighter image (see the
[README comparison](README.md#which-variant-should-i-use)).

> Instead of installing ComfyUI onto a PyTorch template, deploy Runpod's
> **official prebuilt ComfyUI image** — ComfyUI + deps + custom nodes are baked in
> and it **auto-starts** on boot. No SSH, no `pip install`, no `python main.py`.
> Per the development loop, this is the "prefer a prebuilt" path
> (`../../../runpod-usage/reference/development-loop.md`).

## Prerequisites

- `runpodctl` installed and `export RUNPOD_API_KEY=your_key`
  ([`../../../runpodctl/SKILL.md`](../../../runpodctl/SKILL.md)).
- A GPU with ≥16 GB VRAM (RTX 4090 ideal) in the **same DC** as your network
  volume.
- Enough container disk for the image (**~150 GB** — larger than a PyTorch base).

## Walkthrough

```bash
export RUNPOD_API_KEY=your_key

runpodctl template search comfyui                  # discover the official ComfyUI templates
# Official (isRunpod:true): "ComfyUI - CUDA 12.8"  id cw3nka7d08  image runpod/comfyui:cuda12.8
#   (CUDA 13 / Blackwell / RTX 5090 → use "ComfyUI - CUDA 13" id 2lv7ev3wfp)
```

```bash
runpodctl pod create --name comfyui-prebuilt \
  --template-id cw3nka7d08 \                        # official prebuilt ComfyUI (CUDA 12.8); auto-starts
  --gpu-id "NVIDIA GeForce RTX 4090" --data-center-ids <dc-with-4090-and-volume> \
  --ports "8188/http,8080/http,8888/http,22/tcp" \  # 8188 ComfyUI, 8080 FileBrowser, 8888 JupyterLab, 22 SSH
  --network-volume-id <volume-id> --volume-mount-path /workspace \  # persist install + models
  --ssh --terminate-after <iso8601 a few hours out>                 # SSH (only for adding a model) + cost guard
```

There is **no install/run step** — ComfyUI is already launched by the image
(`main.py --listen 0.0.0.0 --port 8188 --enable-cors-header`, so bind and CORS are
handled for you).

> For the RTX 5090 / Blackwell / CUDA 13 case, swap the template id to
> `2lv7ev3wfp` ("ComfyUI - CUDA 13") and set `--gpu-id` to the matching GPU.

## Verify it works

Just poll the proxy — no service to start:

```bash
# ~4 min of proxy 502s on FIRST boot (it copies ComfyUI to /workspace on the volume) — keep polling
until curl -sf https://<pod-id>-8188.proxy.runpod.net/system_stats; do sleep 10; done
echo "ComfyUI: https://<pod-id>-8188.proxy.runpod.net"
```

The readiness log line inside the pod is
`[ComfyUI-Manager] All startup tasks have been completed.` Install path is
`/workspace/runpod-slim/ComfyUI`; the launch args file is
`/workspace/runpod-slim/comfyui_args.txt`.

**The checkpoint detail:** the image ships **no model** — `/models/checkpoints`
is empty on boot, so the default graph can't run until you add one. The default
graph references `v1-5-pruned-emaonly-fp16.safetensors`; add exactly that filename
so the graph is usable with no node edits. Three ways to add it:

- **From the UI (easiest for a human):** the prebuilt image bundles
  **ComfyUI-Manager**, so when a loaded workflow references a missing model the UI
  shows a **blue "download" / missing-models button** that fetches the model
  **straight into the correct Runpod folder** — no need to find the URL or the
  right `models/` subdirectory yourself.
- **Programmatically (for an agent):** drop the file into
  `/workspace/runpod-slim/ComfyUI/models/checkpoints/` over SSH (same filename the
  default graph references); ComfyUI rescans on the next `/object_info` request —
  no restart needed. Agents use this path since they don't click UI buttons:

  ```bash
  ssh <pod-ssh> 'set -e; cd /workspace/runpod-slim/ComfyUI/models/checkpoints && \
    curl -L -o v1-5-pruned-emaonly-fp16.safetensors \
      https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors'
  ```
- **From workflow metadata:** the current official image also bundles
  **ComfyUI-RunpodDirect**. When a loaded workflow contains trustworthy model
  metadata, it can download the approved file straight into the correct Pod model
  folder. Feature-detect `/server_download/folder_paths` instead of assuming a
  particular image version. If a community workflow has only a filename and no
  model URL/hash, use the
  [ComfyUI model-repair guide](../../../runpod-templates/reference/comfyui-model-repair.md)
  to resolve and annotate a reviewed workflow copy first. This metadata-recovery path was added
  after the 2026-07-07 live run; probe the route and verify a real download before
  treating it as live-confirmed.

Then confirm generation the same way as Variant A: POST the default graph to
`/prompt`, poll `/history/<id>`, fetch `/view?filename=<out>&type=output`.

## Variant-specific facts & gotchas

Verified on pod `7ydkt5vs4fst25` (RTX 4090, $0.69/hr): template `ComfyUI - CUDA 12.8`
(id `cw3nka7d08`), first boot ~4 min of proxy 502s while it copied ComfyUI onto the
network volume, then served; generation confirmed via the API.

**Static image facts** (ids, variants, ports/credentials, autostart command, paths,
custom nodes, sizing, the no-model gap) live in
[`runpod-templates/reference/comfyui.md`](../../../runpod-templates/reference/comfyui.md)
— maintained there once, don't trust a stale copy here.

Run-specific notes that stay with this walkthrough:

- **Boot time depends on the volume:** the ~4 min above is the network-volume case (the
  first-boot copy crosses the volume). On container disk with a cached image it can be
  well under a minute — poll, don't budget a fixed wait.
- **Only the checkpoint needs SSH** — everything else is create + poll.
- **Shared gotchas still apply:** "Running" ≠ ready (poll the proxy), network
  volume ↔ GPU must be the same DC, and the proxy URL is public + unauth. See the
  [README's shared gotchas](README.md#cross-cutting-gotchas-shared).

## Cost & cleanup

Shared with Variant A — see [Cost & cleanup in the README](README.md#cost--cleanup-shared).
In short: `--terminate-after` at creation, then `runpodctl pod remove <pod-id>`
and delete the network volume when done.
