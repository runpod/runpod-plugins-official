# Official PyTorch templates

The general-purpose GPU base: torch + CUDA + SSH + (optional) JupyterLab. This is the
template to deploy for a dev box, a fine-tune, or as the base under anything you install
yourself — golden path 02 variant A builds ComfyUI on it, path 04 fine-tunes on it.

**Deploy walkthroughs:** [golden path 06 — dev pod](../../runpod/golden-paths/06-dev-pod.md),
[04 — fine-tune](../../runpod/golden-paths/04-finetune-pod.md). Building your own image
`FROM runpod/pytorch:<tag>` →
[`runpod-usage/reference/building-images.md`](../../runpod-usage/reference/building-images.md).

## 1. The seven templates

| Name | Id | Image | Note |
| --- | --- | --- | --- |
| Runpod Pytorch 2.8.0 | `runpod-torch-v280` | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` | **default choice** |
| Runpod Pytorch 2.4.0 | `runpod-torch-v240` | `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04` | older scheme |
| Runpod Pytorch 2.2.0 | `runpod-torch-v220` | `runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04` | older scheme |
| Runpod Pytorch 2.1 | `runpod-torch-v21` | `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04` | CUDA 11.8 |
| Runpod Pytorch 2.8.0 for clusters | `9yo900pjtt` | `runpod/pytorch:1.0.7-cu1281-torch280-ubuntu2404-cluster` | Instant Clusters |
| Runpod Pytorch 2.9.0 for clusters | `a9dk3g7cny` | `runpod/pytorch:1.0.7-cu1300-torch291-ubuntu2404-cluster` | CUDA 13 |
| Runpod Pytorch 2.4.0 ROCm 6.1 | `runpod-torch-v240-rocm61` | `runpod/pytorch:2.4.0-py3.10-rocm6.1.0-ubuntu22.04` | **AMD** category |

All `isRunpod: true`, mount `/workspace`. Note the **two tag schemes**: ≤2.4 encodes
torch first (`2.4.0-py3.11-cuda12.4.1-…`), ≥2.8 is image-versioned
(`1.0.2-cu1281-torch280-…` — the leading `1.0.2` is the image release, not torch).
Single-GPU pods for Blackwell/CUDA-13: only the *cluster* 2.9.0 image carries `cu1300`
today — check `runpodctl template list --type official` for a newer non-cluster one
before assuming.

## 2. Variants — picking

- **Default:** `runpod-torch-v280` (torch 2.8.0, CUDA 12.8.1, Ubuntu 24.04).
- Older torch pins (2.1/2.2/2.4) exist for reproducing environments; they run older
  Python (3.10/3.11) and older CUDA — match to your GPU's requirement.
- `for clusters` variants are for Instant Clusters, not single pods.
- ROCm 6.1 is the only AMD-category official template.

## 3. Ports and credentials

`runpod-torch-v280` (`ports`: `8888/http,22/tcp,22/udp`):

| Port | Service | Credentials |
| --- | --- | --- |
| `22` | SSH | `PUBLIC_KEY` / registered key |
| `8888` | JupyterLab | **only runs if `JUPYTER_PASSWORD` is set** — it becomes the token |

⚠️ **Jupyter does not autostart on a bare create.** `/start.sh` launches JupyterLab only
when the `JUPYTER_PASSWORD` env var is set (verified in the script: `if [[
$JUPYTER_PASSWORD ]]`). Deploying from the **Console** sets it for you; `runpodctl pod
create --template-id runpod-torch-v280` with no `--env` does **not** — port 8888 then
502s forever, which looks exactly like a slow boot. Pass
`--env '{"JUPYTER_PASSWORD":"<token>"}'` if you want Jupyter, or just use SSH.

## 4. Autostart

Nothing user-facing beyond sshd (and Jupyter under the condition above). This template
is a base, not a service: whatever you start, `setsid` it and bind `0.0.0.0`
([pod-workflows](../../runpod-usage/reference/pod-workflows.md)).

## 5. Paths

`/workspace` is the persistent mount (20–50 GB volume by default per template).
Jupyter's preferred dir is `/workspace`. Everything else is stock Ubuntu.

## 6. Readiness

- **SSH** is the readiness signal for a base template — `runpodctl pod create --wait`
  blocks until SSH is actually reachable.
- **8888** answers only if Jupyter was enabled (§3). Do not poll it otherwise.

## 7. What does not ship / on-pod gotchas

The Python environment is the sharp edge — verified on `runpod-torch-v280`:

- **torch lives in the system Python** (3.12.3, torch 2.8.0+cu128, CUDA visible). A
  fresh venv (`uv venv`) does **not** inherit it — install into the existing
  interpreter. `uv` is preinstalled at `/usr/bin/uv`.
- **PEP 668:** Ubuntu 24.04 marks the system Python externally managed, so a bare
  `pip install` fails; use `pip install --break-system-packages` (verified).
- **`pip install runpod` cryptography clash** on this base:
  [`gotchas.md`](../../runpod-usage/reference/gotchas.md).
- Full install hygiene: [`on-pod-setup.md`](../../runpod-usage/reference/on-pod-setup.md).

## 8. Sizing

Container disk: 20–30 GB on the single-pod NVIDIA templates, 50 GB on the cluster
variants, 40 GB on ROCm (vs 150 GB for ComfyUI). VRAM is workload-driven, not
template-driven.

## 9. Version pinning

The template ids are **stable names** (`runpod-torch-v280`) and new torch lines arrive
as **new templates** rather than mutating old ones — the 2.1→2.8 lineup above is the
evidence. To pin harder than the template, deploy the immutable image tag directly
(`--image runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`). Whether a template id's
image tag is ever repointed in place is not yet documented — when it matters, pin the
image tag.

## Verification

Live-verified **2026-08-25** on pod `7f9dzqzjn3iu7u` (RTX 4090, $0.74/hr,
`runpod-torch-v280`, no env vars), torn down after: Python 3.12.3, torch 2.8.0+cu128,
`cuda.is_available()` true, driver 570.195.03; **no Jupyter process** and 8888 502'd
>2 min until the `JUPYTER_PASSWORD` gate was confirmed in `/start.sh:77`; PEP 668
refusal reproduced; `uv` present. Other variants verified from `template get` metadata
only.
