---
lanes: [runpodctl]
mcp: partial
concepts: [pod, template, container-image, network-volume, exposed-port, container-disk]
status: live-verified
verified: "2026-11-18"
evals: [runpod/evals/route-templates, runpod/evals/prefer-prebuilt]
---

# Golden path 02 — ComfyUI — Variant B: prebuilt official image

> **Status:** live-verified 2026-11-18 — create with generated passwords, auth and readiness poll on template `0o2l6v3iyp`; generation through the API last run 2026-07-07 on the older `cw3nka7d08` template. **Evals:** [route-templates](../../evals/route-templates.eval.md) · [prefer-prebuilt](../../evals/prefer-prebuilt.eval.md). Status key: [golden-paths README](../README.md#status-legend).

**Status:** COVERED — live-verified 2026-11-18 on pod `lyhyfvbhbn2w05` (RTX 4090,
$0.89/hr). **Lane:** runpodctl.
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

Find the template marked CURRENT (the command is in
[`runpod-templates/reference/comfyui.md` §1](../../../runpod-templates/reference/comfyui.md#finding-the-current-template)),
then read it:

```bash
export RUNPOD_API_KEY=your_key
runpodctl template get 0o2l6v3iyp
# "ComfyUI 0.44.0 - CUDA 13.2 - Template 2.4.1", image runpod/comfyui:2.4.1-comfyuiv0.44.0-cuda13.2
# env: COMFYUI_PASSWORD / FILEBROWSER_PASSWORD = placeholders; replace both at create
```

ComfyUI (`8188`) and FileBrowser (`8080`) start only with a password of 12+ characters.
The template's values are guessable placeholders, so generate your own and pass them in
`--env`; they replace the template's values per key:

```bash
COMFYUI_PASSWORD=$(openssl rand -hex 16)
FILEBROWSER_PASSWORD=$(openssl rand -hex 16)

runpodctl pod create --name comfyui-prebuilt \
  --template-id 0o2l6v3iyp \                        # official prebuilt ComfyUI (CURRENT tag); auto-starts
  --gpu-id "NVIDIA GeForce RTX 4090" --min-cuda-version 13.2 \   # match the image's CUDA tag
  --data-center-ids <dc-with-4090-and-volume> \
  --ports "8188/http,8080/http,8888/http,22/tcp" \  # 8188 ComfyUI, 8080 FileBrowser, 8888 JupyterLab, 22 SSH
  --env "{\"COMFYUI_PASSWORD\":\"$COMFYUI_PASSWORD\",\"FILEBROWSER_PASSWORD\":\"$FILEBROWSER_PASSWORD\"}" \
  --network-volume-id <volume-id> --volume-mount-path /workspace \  # persist install + models
  --ssh                                                             # SSH (only for adding a model)
```

There is **no install/run step** — the image starts ComfyUI behind an auth proxy on
`8188`. To read the password back later, take `env.COMFYUI_PASSWORD` from REST v2
`GET /v2/pods/<pod-id>`, or run `echo "$COMFYUI_PASSWORD"` in a shell on the pod.

## Verify it works

Poll the proxy **with the password**; without it the poll stops at `401`:

```bash
# 404/502 while it starts; ~4 min on FIRST boot onto a network volume — keep polling
until curl -sf -H "Authorization: Bearer $COMFYUI_PASSWORD" \
  https://<pod-id>-8188.proxy.runpod.net/system_stats; do sleep 10; done
echo "ComfyUI: https://<pod-id>-8188.proxy.runpod.net (any username, password = COMFYUI_PASSWORD)"
```

Hand the user the URL and the password. A browser asks for a username (any) and the
password, or signs in once through `https://<pod-id>-8188.proxy.runpod.net/?token=<COMFYUI_PASSWORD>`.
FileBrowser is user `admin` with `FILEBROWSER_PASSWORD`.

The readiness log line inside the pod is
`ComfyUI is READY on port 8188`. Install path is
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
`/prompt`, poll `/history/<id>`, fetch `/view?filename=<out>&type=output`. Send
`Authorization: Bearer $COMFYUI_PASSWORD` on every call, and on the `/ws` websocket:

```bash
curl -sf -H "Authorization: Bearer $COMFYUI_PASSWORD" -H 'Content-Type: application/json' \
  -d @workflow_api.json https://<pod-id>-8188.proxy.runpod.net/prompt   # body: {"prompt": {...}}
```

## Variant-specific facts & gotchas

Verified on pod `lyhyfvbhbn2w05` (RTX 4090, $0.89/hr, 2026-11-18): template
`0o2l6v3iyp` with generated passwords in `--env`, container disk only. `/system_stats`
answered `401` without auth and with the placeholder, `200` with the Bearer password ~17 s
after create; the `/ws` upgrade answered `401` without auth and `101` with it. The full
request table is in the
[reference's Verification](../../../runpod-templates/reference/comfyui.md#verification).

Earlier run on pod `7ydkt5vs4fst25` (RTX 4090, $0.69/hr, 2026-07-07): template
`ComfyUI - CUDA 12.8` (id `cw3nka7d08`, image without the password proxy), first boot
~4 min of proxy 502s while it copied ComfyUI onto the network volume, then served;
generation confirmed via the API.

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
  volume ↔ GPU must be the same DC, and the proxy URL is public (the image's own
password is the only access control). See the
  [README's shared gotchas](README.md#cross-cutting-gotchas-shared).

## Cost & cleanup

Shared with Variant A — see [Cost & cleanup in the README](README.md#cost--cleanup-shared).
In short: `runpodctl pod remove <pod-id>`, then delete the network volume when done.
