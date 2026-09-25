# Golden path 02 — ComfyUI — Variant A: from scratch on a PyTorch template

**Status:** COVERED — live-verified 2026-07-07 (ran end to end, 512×512 PNG
produced). **Lane:** runpodctl (SSH-exec).
**When to use this variant:** you need full control — specific ComfyUI/torch
versions, custom nodes, or a lighter footprint than the prebuilt image ships. If
you just want ComfyUI up fast and reliably, use
[Variant B — prebuilt official image](variant-b-prebuilt.md) instead (the
[README](README.md#which-variant-should-i-use) recommends B by default).

> Full control, slower first setup: you install ComfyUI onto an official PyTorch
> template yourself. This is the from-scratch branch of the pod development loop
> (`../../../runpod-usage/reference/pod-workflows.md`).

## Prerequisites

- `runpodctl` installed and `export RUNPOD_API_KEY=your_key` (non-interactive
  auth — see [`../../../runpodctl/SKILL.md`](../../../runpodctl/SKILL.md)).
- A GPU with ≥16 GB VRAM available (RTX 4090 ideal) in a data center that also has
  your network volume.
- SSH usable by the agent (`runpodctl ssh info` returns the connection details).

## Walkthrough

Real commands; one line each on *why*. Fill in the `<...>` from the discovery
steps.

```bash
export RUNPOD_API_KEY=your_key                    # non-interactive auth runpodctl reads

runpodctl datacenter list                         # pick a DC that has the GPU (co-locate with the volume)
runpodctl network-volume create --name comfy --size 50 --data-center-id <dc>   # persistent /workspace, survives teardown
runpodctl template search pytorch                 # find the official PyTorch template id
```

```bash
runpodctl pod create --name comfyui \
  --template-id <runpod-pytorch-template-id> \    # official PyTorch base (ships system torch/CUDA)
  --gpu-id "NVIDIA GeForce RTX 4090" --data-center-ids <dc> \
  --ports "8188/http,22/tcp" \                    # 8188 = ComfyUI proxy port, 22 = SSH; MUST be set at creation
  --network-volume-id <volume-id> --volume-mount-path /workspace \  # persist models/install
  --ssh                                                             # SSH control channel
```

```bash
runpodctl pod get <pod-id>                         # poll until it is running
runpodctl ssh info <pod-id>                        # prints ssh command + key (does not connect)
```

```bash
# install into the template's EXISTING torch (see PEP 668 gotcha) + fetch an ungated checkpoint
ssh <pod-ssh> 'set -e; cd /workspace && \
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI && \
  cd ComfyUI && pip install --break-system-packages -r requirements.txt && \
  curl -L -o models/checkpoints/v1-5-pruned-emaonly-fp16.safetensors \
    https://huggingface.co/Comfy-Org/stable-diffusion-v1-5-archive/resolve/main/v1-5-pruned-emaonly-fp16.safetensors'
```

```bash
# start FULLY DETACHED so it survives ssh disconnect (SIGHUP); return immediately
ssh <pod-ssh> 'setsid bash -c "cd /workspace/ComfyUI && python main.py --listen 0.0.0.0 --port 8188" \
  > /workspace/comfyui.log 2>&1 < /dev/null &'
```

`--listen 0.0.0.0` is required — bound to localhost the proxy can't reach it and
502s forever. Logging to `/workspace/comfyui.log` (on the volume) lets you
diagnose in a later SSH call.

## Verify it works

Poll from **outside**, in a separate call from the start command (don't `sleep`
in the same SSH invocation — it can drop the channel):

```bash
# expect ~30–60s of proxy 502s first while ComfyUI imports / inits CUDA — keep polling
until curl -sf https://<pod-id>-8188.proxy.runpod.net/system_stats; do sleep 5; done
echo "ComfyUI: https://<pod-id>-8188.proxy.runpod.net"
```

Once `/system_stats` returns 200, open the URL: the UI loads with the default
text-to-image graph, tweak the prompt → **Queue Prompt**.

**The checkpoint detail:** the file `v1-5-pruned-emaonly-fp16.safetensors` is
exactly what ComfyUI's default graph references, so the UI is usable on first
open with no node edits. To verify programmatically instead: POST the default
graph to `/prompt`, poll `/history/<id>`, then fetch the image at
`/view?filename=<out>&type=output`. (In the verified run this produced a
512×512 PNG.)

## Variant-specific gotchas

- **PEP 668 / install into the template's torch.** The current PyTorch template
  is Ubuntu 24.04 / py3.12 (externally-managed), torch in the **system** Python.
  Plain `pip install` errors — use `--break-system-packages` (as above). A bare
  `uv venv` won't inherit torch and would reinstall multi-GB torch or lose CUDA;
  install into the existing interpreter (or `uv venv --system-site-packages`). See
  [`../../../runpod-usage/reference/on-pod-setup.md`](../../../runpod-usage/reference/on-pod-setup.md).
- **Detach or it dies.** A plain `&` is killed by SIGHUP when the SSH channel
  closes. `setsid … < /dev/null &` (new session + detached stdin) is what keeps
  ComfyUI alive after you disconnect. Do the readiness wait in a **separate** SSH
  call.
- **Proxy warm-up 502s.** ~30–60s of 502s during boot is normal — poll with a
  timeout, don't treat early 502s as failure. If it never comes up, read
  `/workspace/comfyui.log`.
- **Bind `0.0.0.0`, ports at creation, URL is public.** localhost → 502; ports
  can't be added to a running pod without a reset; anyone with the proxy URL can
  reach it (no auth).
- **Escalate on manual steps.** If a step needs a human (gated model license,
  quota increase, credential), stop and say exactly what's blocked.

## Cost & cleanup

Shared with Variant B — see [Cost & cleanup in the README](README.md#cost--cleanup-shared).
In short: `runpodctl pod remove <pod-id>`, then delete the network volume when done.
