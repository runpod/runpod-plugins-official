# Set a CUDA floor when creating a GPU pod

## Prompt

Create a Runpod GPU pod running the latest official PyTorch image on an RTX 4090 so
I can iterate on a training script over SSH.

## Expected behavior

Per `runpod-usage/reference/gpu-selection.md` ("Step 3: pin the CUDA floor") and the
`runpodctl` skill's decision rules:

1. **Pins the host CUDA floor to the image's CUDA line** — the current official
   PyTorch image is a `cu128` build, so the create carries `--min-cuda-version 12.8`
   (or `gpu.minCudaVersion: "12.8"` on REST v2). A create with no floor accepts any
   host, and the container then dies at startup or silently drops to CPU.
2. **Does not jump to `13.0`** just because it's the newest — 13.0 is for a CUDA-13
   image (`runpod/comfyui:cuda13.0`, the `cu1300` cluster PyTorch image), not for a
   newer GPU.
3. **Does not reach for the old default** — `runpod-torch-v21` is torch 2.1 on CUDA
   11.8; the current default is `runpod-torch-v280`.
4. **Uses a lane that can express the constraint** — `runpodctl pod create` or a v2
   `POST /v2/pods`. If the agent is in the MCP lane it notes that the MCP create
   tools carry no CUDA parameter and switches lanes (or verifies the live schema
   before claiming otherwise).
5. **Cost guard + SSH** as usual — `--terminate-after`, and the SSH key registered
   before creation.

## Assertions

- The pod create includes a CUDA floor (`--min-cuda-version` / `gpu.minCudaVersion`), not just a GPU id.
- The floor matches the image's CUDA line rather than defaulting to the highest number available.
- Does not use `runpod-torch-v21` / a CUDA 11.8 image as the "latest PyTorch" default.
- If MCP is the chosen lane, it either verifies the live tool schema or hands the create to runpodctl.
