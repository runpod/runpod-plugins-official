# ComfyUI pinned, private and driven by the API

## Prompt

On my running GPU Pod (PyTorch template, I have a shell), install ComfyUI at an exact
version, keep it off the public URL, and generate one test image through its API. Tell me
the file you got.

## Expected behavior

Per golden path 02 Variant C (`golden-paths/02-comfyui-pod/variant-c-pinned-api.md`):

1. Routes to Variant C, not Variant A or B: the user wants a private, API-driven install on an
   existing Pod, not a URL.
2. Downloads the ComfyUI source archive for an exact commit and the checkpoint from an exact
   revision, and checks both SHA-256 values on the Pod.
3. Installs into `python3 -m venv --system-site-packages` with a torch constraints file, so
   the requirements cannot replace the template's torch.
4. Starts ComfyUI with `--listen 127.0.0.1`, `--disable-all-custom-nodes` and
   `--disable-api-nodes`, and waits for `GET /system_stats` 200.
5. Sends `POST /prompt` once with an API-format workflow, keeps the `prompt_id`, reads
   `GET /history/<prompt_id>` until `success`, and takes the filename, subfolder and type from
   its `outputs`.
6. Fetches the PNG with `GET /view` using those values and reports its size and SHA-256.

## Assertions

- No new Pod, no new exposed port, no `--listen 0.0.0.0`.
- `/prompt` is sent once; a 200 from it is not reported as an image.
- The reported filename comes from `/history` outputs, not from the `filename_prefix`.
- A 4-step 256 px smoke image is described as a pipeline check, not a quality result.
