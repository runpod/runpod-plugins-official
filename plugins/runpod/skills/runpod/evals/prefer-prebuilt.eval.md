# Prefer a prebuilt/known option before building from scratch

## Prompt

Get ComfyUI running on Runpod for me and give me the URL.

## Expected behavior

Per the development loop's "prefer prebuilt" step (`runpod/SKILL.md`,
`runpod-usage/reference/development-loop.md`):

1. The agent should look for an **official prebuilt ComfyUI template/image** first
   (the Runpod-official ComfyUI template tag marked CURRENT, per
   `runpod-templates/reference/comfyui.md`),
   NOT immediately git-clone + `pip install` ComfyUI onto a bare PyTorch template.
2. It should deploy the pod from that template with the ComfyUI port exposed, set
   `COMFYUI_PASSWORD` and `FILEBROWSER_PASSWORD` in the create `env` to generated
   values of 12+ characters, and **verify by polling the proxy URL with
   `Authorization: Bearer <COMFYUI_PASSWORD>`** (expecting warm-up 404/502s), not
   report success on "pod Running" or on a `401`.
3. From-scratch install is acceptable only as a fallback if no good prebuilt exists.

## Assertions

- Searches for / uses a prebuilt ComfyUI template or Hub entry before any from-scratch install.
- Exposes the ComfyUI port at creation and returns a `…proxy.runpod.net` URL.
- Sets both passwords at create with generated values; never keeps the template's
  placeholder values or presents them to the user as the passwords.
- Verifies readiness with a real authenticated request (polls the URL with the
  password), not a status field.
- Hands back the URL with the ComfyUI password and how to sign in (any username).
- Only falls back to git-clone + pip install if it argues no prebuilt fits.
