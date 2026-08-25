# Golden path 02 — ComfyUI server on a pod + access URL

**Goal / Status: COVERED — live-verified 2026-07-07 / Kind: pod, server / Lane: runpodctl**

From "run ComfyUI on Runpod and give me the URL", an agent provisions a GPU pod,
gets ComfyUI running, and returns a proxy URL where the web UI loads — with a
checkpoint and the default text-to-image workflow usable. This is the same shape
as `../01-ollama-pod.md`; it follows the pod development loop in
[`../../../runpod-usage/reference/pod-workflows.md`](../../../runpod-usage/reference/pod-workflows.md).

There are two ways to get there, split into their own files below.

If the Pod is already running and an imported workflow names models without
download metadata, route that repair to
[`runpod-comfyui-models`](../../../runpod-comfyui-models/SKILL.md); Pod provisioning
remains in this golden path. This post-launch recovery extension was not part of
the 2026-07-07 live verification, so feature-detect the live image and its routes.

## Which variant should I use?

| | Variant A — from scratch | Variant B — prebuilt official image |
| --- | --- | --- |
| **What you deploy** | Official PyTorch template; you `git clone` + install ComfyUI | Runpod's official prebuilt ComfyUI image (auto-starts) |
| **Steps** | create → SSH install → detached start → poll | create → poll (no SSH/install/run step) |
| **First-boot wait** | ~30–60s of proxy 502s after you start it | ~4 min of proxy 502s (copies ComfyUI to the volume on first boot) |
| **Control** | Full — pick versions, custom nodes, a lighter footprint | What ships (ComfyUI 0.26.2, torch 2.10.0+cu128, ComfyUI-Manager, FileBrowser, JupyterLab) |
| **Gotchas you must handle** | PEP 668 `--break-system-packages`, `setsid` detach, bind `0.0.0.0` | Larger image (150 GB container disk); only the checkpoint needs SSH |
| **Pick when** | You need something custom/lighter, or specific versions/nodes | You just want ComfyUI up reliably with the least effort — **default** |

**Default recommendation: Variant B (prefer prebuilt).** Per the development loop,
[prefer a prebuilt/known option before building from scratch](../../../runpod-usage/reference/development-loop.md#2-prefer-a-prebuilt--known-option-before-building-from-scratch)
— it auto-starts and skips the install gotchas. Reach for Variant A only when no
prebuilt fits (custom nodes, a lighter image, or pinned versions).

## Variants

- [Variant A — from scratch](variant-a-from-scratch.md) — install ComfyUI yourself on a PyTorch template.
- [Variant B — prebuilt official image](variant-b-prebuilt.md) — deploy `runpod/comfyui`, which auto-starts.

## Acceptance criteria (shared)

Both variants must satisfy the same delivery bar:

1. **Auth** resolved (`export RUNPOD_API_KEY=...`).
2. GPU pod, GPU with **≥16 GB VRAM** (RTX 4090 is ideal), **port `8188/http`
   exposed at creation**, SSH enabled, on a **network volume**, with a
   `--terminate-after` cost guard.
3. ComfyUI running, **bound to `0.0.0.0`** on port `8188`.
4. Agent **polls the proxy URL until the UI answers** (expect proxy 502s during
   boot — see per-variant timings); it **escalates on any manual step** rather
   than spinning or faking progress.
5. **Secondary:** an ungated checkpoint is available so the default graph works;
   ideally a generation is confirmed via the API.
6. Returns `https://<pod-id>-8188.proxy.runpod.net`.

## Cross-cutting gotchas (shared)

These bite both variants (details and the fix per variant are in each file):

- **PEP 668 / template torch (Variant A).** Official PyTorch templates are now
  Ubuntu 24.04 / py3.12 (externally-managed) with torch in the **system** Python.
  A bare `pip install` errors without `--break-system-packages`, and a fresh
  `uv venv` won't inherit torch — install into the existing interpreter. See
  [`../../../runpod-usage/reference/on-pod-setup.md`](../../../runpod-usage/reference/on-pod-setup.md).
- **Detach the server / `setsid` (Variant A).** A plain `&` dies on SSH
  disconnect (SIGHUP). Start with `setsid … < /dev/null &`, return immediately,
  and poll in a **separate** SSH call (don't `sleep` in the same invocation).
- **"Running" ≠ ready.** A pod showing "Running" does not mean ComfyUI serves.
  Always verify from **outside** through the proxy and expect a warm-up window of
  502s — that's normal, keep polling. See the loop's
  [verify step](../../../runpod-usage/reference/development-loop.md#6-verify-with-a-real-request--up--ready).
- **Bind `0.0.0.0`.** localhost/`127.0.0.1` → the proxy can't reach it → 502.
  Variant B already passes `--listen 0.0.0.0`; Variant A must set it.
- **Network-volume DC lock.** A network volume is pinned to one data center, so
  the pod must be created in that **same DC** — which narrows GPU availability.
  Confirm your GPU exists in the volume's DC first
  ([`../../../runpod-usage/reference/storage.md`](../../../runpod-usage/reference/storage.md),
  [`gotchas.md`](../../../runpod-usage/reference/gotchas.md)).
- **Ports at creation; URL is public + unauth.** Ports can't be added to a
  running pod without a reset, and the proxy URL is reachable by anyone who has it
  ([`../../../runpod-usage/reference/networking.md`](../../../runpod-usage/reference/networking.md)).

## Cost & cleanup (shared)

- **Cost guard at creation:** `--terminate-after <iso8601 a few hours out>`
  *deletes* the pod at that time. Prefer it over `--stop-after`, which only
  *stops* the pod so you keep paying for disk/volume.
- **Tear down when done:** `runpodctl pod remove <pod-id>`, then delete the
  network volume (`runpodctl network-volume delete <volume-id>`) if it was only
  for this test — the pod must be removed first.
- Data on the network volume persists across stop/restart and survives pod
  removal (only volume deletion clears it).
- Reference RTX 4090 pricing seen during verification: **$0.69/hr** (Variant B
  pod `7ydkt5vs4fst25`). GPU/DC pricing varies — check `runpodctl gpu list`.
