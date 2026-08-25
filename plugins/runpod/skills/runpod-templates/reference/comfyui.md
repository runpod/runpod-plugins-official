# Official ComfyUI templates

ComfyUI + dependencies + custom nodes baked in, **auto-starting on boot**. No SSH, no
`pip install`, no `python main.py`. This is the default way to get ComfyUI on a pod.

Two variants, one per CUDA line. Everything below was verified on 2026-08-25 (see
[Verification](#verification)).

## 1. The two templates

| | CUDA 12.8 | CUDA 13 |
| --- | --- | --- |
| Name | `ComfyUI - CUDA 12.8` | `ComfyUI - CUDA 13` |
| Template id | `cw3nka7d08` | `2lv7ev3wfp` |
| Image | `runpod/comfyui:cuda12.8` | `runpod/comfyui:cuda13.0` |
| GPUs | pre-Blackwell (RTX 4090, L40, A100) | **Blackwell / RTX 5090** |
| Console | [hub/template/cw3nka7d08](https://console.runpod.io/hub/template/cw3nka7d08) | [hub/template/2lv7ev3wfp](https://console.runpod.io/hub/template/2lv7ev3wfp) |

Both are official (`isRunpod: true` in runpodctl; the `official` catalog slice in REST v2),
public, `serverless: false`, category `NVIDIA`, container disk **150 GB**, with a **50 GB**
persistent mount at `/workspace`, and `startSsh`/`startJupyter` both on. Source for both:
[github.com/runpod-workers/comfyui-base](https://github.com/runpod-workers/comfyui-base).

**Picking the wrong CUDA line for the GPU is the most common first-run failure.** The
12.8 template explicitly does not support CUDA 13 / Blackwell. Don't infer from the GPU
name — each catalog entry states it:

| Template | `allowedCudaVersions` |
| --- | --- |
| `cw3nka7d08` | `12.8`, `12.9` |
| `2lv7ev3wfp` | `13.0`, `13.1`, `13.2`, `13.3` |

Pass the matching `runpodctl pod create --min-cuda-version` to make host selection
enforce it.

**Upgrading an existing CUDA 12.4 pod to the CUDA 13 template** triggers a one-time
automatic venv migration on the next boot — expect a few extra minutes on that boot only.

### Finding them

```bash
runpodctl template list --type official        # all official templates
runpodctl template search comfyui              # ComfyUI ones; check isRunpod: true
runpodctl template get cw3nka7d08              # image, ports, portsConfig, disk + full readme
```

`template get` returns the template's **readme**, which is the authoritative description
maintained alongside the image — read it when this file and the template disagree.

⚠️ **`runpodctl hub search comfyui` will not find these.** The Hub CLI commands cover Hub
*repos* (serverless workers — it returns `runpod-workers/worker-comfyui`), which are a
different thing from the Console's Hub template pages. Discover pod templates with
`template list` / `template search`, not `hub search`.

Console URL form is `https://console.runpod.io/hub/template/<template-id>`. Slug URLs like
`/hub/template/comfyui-cuda-13?id=2lv7ev3wfp` `308`-redirect to the id form; group URLs
(`/hub/group/<group-id>?selectedTemplate=<id>`) also resolve but carry an opaque group id —
prefer the id form when handing a link to a user.

## 2. Ports and credentials

Baked into both templates (`ports`: `8188/http,8080/http,8888/http,22/tcp,22/udp`):

| Port | Service | Credentials |
| --- | --- | --- |
| `8188` | ComfyUI | none — **the proxy URL is public and unauthenticated** |
| `8080` | FileBrowser | `admin` / `adminadmin12` (default — change it) |
| `8888` | JupyterLab | token via `JUPYTER_PASSWORD`, root at `/workspace` |
| `22` | SSH | `PUBLIC_KEY`, or a generated root password in the pod logs |

Ports must be declared **at pod creation**; they cannot be added to a running pod without
a reset.

## 3. Autostart

Already running on boot — do not re-launch it:

```
main.py --listen 0.0.0.0 --port 8188 --enable-cors-header
```

Both the `0.0.0.0` bind and the CORS header are handled for you.

To add launch args, edit `/workspace/runpod-slim/comfyui_args.txt`, one arg per line
(e.g. `--max-batch-size 8`), and restart. Do not hand-edit the start command.

## 4. Paths

| | |
| --- | --- |
| Install | `/workspace/runpod-slim/ComfyUI` |
| Launch args | `/workspace/runpod-slim/comfyui_args.txt` |
| FileBrowser DB | `/workspace/runpod-slim/filebrowser.db` |
| Checkpoints | `/workspace/runpod-slim/ComfyUI/models/checkpoints/` |

Everything is under `/workspace`, so mounting a network volume there persists the install
and models across pods — and is what makes first boot slow. Volume and GPU must be in the
same data center.

## 5. Readiness

`Running` is not ready. On first boot the image copies ComfyUI into `/workspace`, so the
wait varies a lot — with the image cached on the host and `/workspace` on container disk
it can be well under a minute; onto a network volume, or on a cold image pull, expect
several minutes. **Do not budget a fixed number: poll.** Observed points, for calibration
only: ~22 s (container disk, cached image) and ~4 min (network volume).

Poll from outside and expect this progression — none of it is an error:

```
404  →  502  →  200
```

`404` while the proxy has no port mapping yet, `502` while ComfyUI is starting.

```bash
until curl -sf https://<pod-id>-8188.proxy.runpod.net/system_stats; do sleep 10; done
```

In-pod log line for the same moment:
`[ComfyUI-Manager] All startup tasks have been completed.`

`/system_stats` is also the cheapest way to confirm what you actually got — it returns the
ComfyUI version, the torch build, the live `argv`, and VRAM.

## 6. Pre-installed custom nodes

Both templates ship four, confirmed present at `/extensions/<name>/`:

| Node | Why it matters |
| --- | --- |
| **ComfyUI-Manager** | missing-model download button in the UI; owns the readiness log line |
| **ComfyUI-RunpodDirect** | downloads models **straight to the pod** from workflow metadata |
| **ComfyUI-KJNodes** | extra utility nodes |
| **Civicomfy** | Civitai model downloader |

**RunpodDirect ships here.** So for a workflow repaired by the `runpod-comfyui-models`
skill, the official templates are the case where automatic downloads are available by
default — that skill's "RunpodDirect was not detected" branch does not apply to a stock
pod from these templates.

## 7. What does not ship — no model

`models/checkpoints` is **empty on boot** (verified: `CheckpointLoaderSimple` offers `[]`),
so the default graph cannot run until you add a checkpoint. The default graph references
`v1-5-pruned-emaonly-fp16.safetensors`; use exactly that filename and the graph works with
no node edits.

- **Human:** ComfyUI-Manager shows a blue download button for missing models and fetches
  them into the right folder. Civicomfy covers Civitai.
- **Agent:** drop the file in over SSH. ComfyUI rescans on the next `/object_info` request
  — **no restart needed.** This is the only SSH step these templates need.

```bash
ssh <pod-ssh> 'set -e; cd /workspace/runpod-slim/ComfyUI/models/checkpoints && \
  curl -L -o v1-5-pruned-emaonly-fp16.safetensors \
    https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors'
```

Verify generation end to end: POST the default graph to `/prompt`, poll `/history/<id>`,
fetch `/view?filename=<out>&type=output`.

If the user arrives with an **imported workflow whose model metadata is missing or
broken** (models won't download, filenames with no source), that is a repair task — hand
off to the **`runpod-comfyui-models`** skill. On a stock pod from these templates its
automatic-download path applies, since RunpodDirect is pre-installed (§6).

## 8. Sizing

- **Container disk 150 GB** — considerably larger than a PyTorch base.
- **VRAM ≥16 GB.** RTX 4090 (24 GB) is the reference GPU; seen at **$0.74/hr** with
  12 vCPU / 31 GB RAM.

## 9. Version pinning

Not yet documented: whether `cw3nka7d08` is repointed at new
`runpod/comfyui:cuda12.8` builds or a new id is minted per release, and whether a user can
hold an older build through the template or must deploy the raw image tag instead.

Meanwhile: `/system_stats` tells you what a running pod actually has, and `template get`
tells you what a new pod would get.

## 10. When these templates are the wrong answer

Custom nodes beyond the four above, pinned ComfyUI/torch versions, or a lighter image →
build on a PyTorch base instead:
[golden path 02, variant A](../../runpod/golden-paths/02-comfyui-pod/variant-a-from-scratch.md).

## Verification

Live-verified **2026-08-25** on pod `31wn26y2boogll` (RTX 4090, $0.74/hr, CUDA 12.8
template, **no** network volume), torn down after: ready in 22 s on that run (cached image, no volume) via `404 → 502 → 200`;
ComfyUI **0.26.2**, torch **2.10.0+cu128**, Python 3.12.3; `argv` exactly as in §3; all
four custom nodes present; checkpoints empty.

The **CUDA 13** template is verified from `runpodctl template get 2lv7ev3wfp` + its readme
only — **not** live-run (needs a Blackwell GPU). The ~4 min network-volume boot figure
comes from the earlier live run in
[golden path 02, variant B](../../runpod/golden-paths/02-comfyui-pod/variant-b-prebuilt.md)
(pod `7ydkt5vs4fst25`, 2026-07-07).
