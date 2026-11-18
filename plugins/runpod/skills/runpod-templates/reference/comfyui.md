---
concepts: [template, pod, container-image, network-volume, exposed-port]
---

# Official ComfyUI templates

ComfyUI + dependencies + custom nodes baked in, **auto-starting on boot**. No SSH, no
`pip install`, no `python main.py`. This is the default way to get ComfyUI on a pod.
To serve a ComfyUI workflow as a scale-to-zero API instead of a pod, see
[runpod-serverless-deploy/reference/comfyui-serverless.md](../../runpod-serverless-deploy/reference/comfyui-serverless.md).

One template family, versioned: each image release gets a new template id. The
Console Hub page deploys the tag marked CURRENT. Everything below was verified on
2026-11-18 against `0o2l6v3iyp`, unless a section says otherwise (see
[Verification](#verification)).

## 1. The template

| | |
| --- | --- |
| Name | `ComfyUI 0.44.0 - CUDA 13.2 - Template 2.4.1` |
| Template id | `0o2l6v3iyp` (the CURRENT tag on 2026-11-18) |
| Image | `runpod/comfyui:2.4.1-comfyuiv0.44.0-cuda13.2` |
| `allowedCudaVersions` | `13.2`, `13.3`, `13.4` |
| Console | [hub/template/0o2l6v3iyp](https://console.runpod.io/hub/template/0o2l6v3iyp) |

It is official (`isRunpod: true`), public, `serverless: false`, category `NVIDIA`,
container disk **150 GB**, with a **50 GB** persistent mount at `/workspace`, and
`startSsh`/`startJupyter` both on. Source:
[github.com/runpod/containers, `official-templates/comfyui`](https://github.com/runpod/containers/tree/main/official-templates/comfyui).

The same release also ships `-cuda12.8` and `-cuda13.0` image tags. A CUDA 13.x pod
does not start on a host whose driver is older than the tag, so pass
`runpodctl pod create --min-cuda-version 13.2` (or the tag's CUDA) to make host
selection enforce it.

**Upgrading an existing pod from an older image** runs a one-time automatic migration
on the next boot (ComfyUI, bundled nodes and the venv for the new CUDA tag). Expect a
few extra minutes on that boot only.

### Finding the current template

Read the CURRENT tag from the public GraphQL `versionedTemplates` query, which is what
the Console Hub deploy picker reads. No API key is needed:

```bash
curl -s https://api.runpod.io/graphql -H 'content-type: application/json' \
  -d '{"query":"{ versionedTemplates(input: {}) { name versions { version status tags { id imageName releaseType } } } }"}' \
  | jq -r '.data.versionedTemplates[] | select(.name|test("ComfyUI")) | .versions[]
           | select(.status=="CURRENT") | .tags[] | select(.releaseType=="CURRENT") | "\(.id) \(.imageName)"'
```

Then read that template:

```bash
runpodctl template get 0o2l6v3iyp      # image, ports, env, disk + full readme
```

`template get` returns the template's **readme**, which is the authoritative description
maintained alongside the image — read it when this file and the template disagree.
`runpodctl template search comfyui` lists the older `ComfyUI - CUDA 12.8` and
`ComfyUI - CUDA 13.0` templates (image `1.3.3`). Use the CURRENT id above for a new pod.

⚠️ **`runpodctl hub search comfyui` will not find these.** The Hub CLI commands cover Hub
*repos* (serverless workers — it returns `runpod-workers/worker-comfyui`), which are a
different thing from the Console's Hub template pages. Discover pod templates as above,
not with `hub search`.

Console URL form is `https://console.runpod.io/hub/template/<template-id>`.

## 2. Ports and passwords

Ports (`ports`: `8188/http,8080/http,8888/http,22/tcp`):

| Port | Service | Sign-in |
| --- | --- | --- |
| `8188` | ComfyUI, behind an auth proxy | `COMFYUI_PASSWORD` (12+ characters); any username |
| `8080` | FileBrowser, rooted at `/workspace` | user `admin`, password `FILEBROWSER_PASSWORD` (12+ characters, common passwords rejected) |
| `8888` | JupyterLab, rooted at `/workspace` | token `JUPYTER_PASSWORD` (`startJupyter` sets it) |
| `22` | SSH | key only: `PUBLIC_KEY` or an SSH key on your Runpod account |

Ports must be declared **at pod creation**; they cannot be added to a running pod without
a reset.

**ComfyUI and FileBrowser start only with a password.** If `COMFYUI_PASSWORD` is unset or
shorter than 12 characters, ComfyUI does not start. If `FILEBROWSER_PASSWORD` is unset or
rejected, FileBrowser does not start. The pod log says why; it never prints the password.
Both services require a password in every configuration.

**Set both passwords at deploy, with generated values.** The template's `env` holds
placeholder values (`comfyui_password`, `filebrowser_password`) that anyone can guess.
Never hand them to a user as the passwords. Values in the create `env` replace the
template's per key:

```bash
COMFYUI_PASSWORD=$(openssl rand -hex 16)       # 32 characters
FILEBROWSER_PASSWORD=$(openssl rand -hex 16)
runpodctl pod create --template-id 0o2l6v3iyp ... \
  --env "{\"COMFYUI_PASSWORD\":\"$COMFYUI_PASSWORD\",\"FILEBROWSER_PASSWORD\":\"$FILEBROWSER_PASSWORD\"}"
```

Hex values also work unescaped in a URL query and in JSON.

**Read the password back** from the pod's `env`: the `runpodctl pod create` output,
REST v2 `GET /v2/pods/<pod-id>` (`.env.COMFYUI_PASSWORD`), or `echo "$COMFYUI_PASSWORD"`
in a shell on the pod.

**Use the password:**

- **Browser:** open `https://<pod-id>-8188.proxy.runpod.net`, enter any username and
  `COMFYUI_PASSWORD`. Or open `https://<pod-id>-8188.proxy.runpod.net/?token=<COMFYUI_PASSWORD>`
  once to sign in without the prompt.
- **API (every HTTP call and the `/ws` websocket):** send
  `Authorization: Bearer <COMFYUI_PASSWORD>`, or HTTP Basic with any username. A request
  without it gets `401`.
- **Wrong passwords:** after 10 wrong passwords in a row the proxy answers `429` until
  attempts slow to one a second. Browsers that are already signed in keep working.
- **FileBrowser API:** `POST /api/login` with `{"username":"admin","password":"<FILEBROWSER_PASSWORD>"}`
  returns a token.

## 3. Autostart

Already running on boot — do not re-launch it. ComfyUI listens only inside the pod, and
the auth proxy serves port `8188`. The start script sets the listen address and port, so
`--listen` and `--port` in `comfyui_args.txt` are ignored, with a warning in the log.

To add launch args, edit `/workspace/runpod-slim/comfyui_args.txt`, one arg per line
(e.g. `--max-batch-size 8`), and restart. Do not hand-edit the start command.

ComfyUI starts without CORS headers, so pages on other sites cannot call it from a
browser. If your own site needs to, add `--enable-cors-header https://your.site` to
`comfyui_args.txt`. Clients that are not browsers are not affected.

ComfyUI-Manager installs node packs from the registry. The image sets
`allow_git_url_install = False` and `allow_pip_install = False` on every start, so
install from a git URL or a pip name over SSH or JupyterLab instead.

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
only: ~17 s (container disk, cached image) and ~4 min (network volume).

Poll from outside **with the password**. Without it the poll ends at `401` from the auth
proxy, which says nothing about ComfyUI. Expect `404` while the proxy has no port mapping
yet and `502` while ComfyUI is starting; none of it is an error.

```bash
until curl -sf -H "Authorization: Bearer $COMFYUI_PASSWORD" \
  https://<pod-id>-8188.proxy.runpod.net/system_stats; do sleep 10; done
```

In-pod log line for the same moment: `ComfyUI is READY on port 8188`. ComfyUI-Manager
keeps refreshing its node list for a few minutes after that; the UI does not wait for it.

`/system_stats` is also the cheapest way to confirm what you actually got — it returns the
ComfyUI version, the torch build, the live `argv`, and VRAM.

## 6. Pre-installed custom nodes

The image ships four, confirmed present at `/extensions/<name>/`:

| Node | Why it matters |
| --- | --- |
| **ComfyUI-Manager** | missing-model download button in the UI; owns the readiness log line |
| **ComfyUI-RunpodDirect** | downloads models **straight to the pod** from workflow metadata |
| **ComfyUI-KJNodes** | extra utility nodes |
| **Civicomfy** | Civitai model downloader |

**RunpodDirect ships here.** So for a workflow repaired with the sibling
[model-repair guide](./comfyui-model-repair.md), the official templates are the case
where automatic downloads are available by default — the guide's "RunpodDirect was not
detected" branch does not apply to a stock pod from these templates.

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
fetch `/view?filename=<out>&type=output`. Send `Authorization: Bearer $COMFYUI_PASSWORD`
on each call, and on the `/ws` websocket if you listen for progress.

If the user arrives with an **imported workflow whose model metadata is missing or
broken** (models won't download, filenames with no source), that is a repair task — hand
off to the [model-repair guide](./comfyui-model-repair.md). On a stock pod from these
templates its automatic-download path applies, since RunpodDirect is pre-installed (§6).

## 8. Sizing

- **Container disk 150 GB** — considerably larger than a PyTorch base.
- **VRAM ≥16 GB.** RTX 4090 (24 GB) is the reference GPU; seen at **$0.74/hr** with
  12 vCPU / 31 GB RAM.

## 9. Version pinning

Each image release gets a new template id with a full image tag
(`runpod/comfyui:<release>-comfyuiv<comfyui>-cuda<cuda>`), and the CURRENT marker moves to
the new id. To hold a build, keep its template id or deploy its image tag directly with
`--image` (then set `ports`, disk and both passwords yourself).

`/system_stats` tells you what a running pod actually has, and `template get` tells you
what a new pod would get.

## 10. When these templates are the wrong answer

Custom nodes beyond the four above, pinned ComfyUI/torch versions, or a lighter image →
build on a PyTorch base instead:
[golden path 02, variant A](../../runpod/golden-paths/02-comfyui-pod/variant-a-from-scratch.md).

## Verification

Live-verified **2026-11-18** on pod `lyhyfvbhbn2w05` (RTX 4090, $0.89/hr, template
`0o2l6v3iyp`, `--min-cuda-version 13.2`, **no** network volume), torn down right after.
Created with generated 32-character `COMFYUI_PASSWORD` and `FILEBROWSER_PASSWORD` in
`--env`; the pod's `env` held those values, not the template placeholders. Results:

| Request | Status |
| --- | --- |
| `GET /system_stats`, no auth | `401` (after `404` for ~10 s) |
| `GET /system_stats`, `Bearer comfyui_password` (placeholder) | `401` |
| `GET /system_stats`, `Bearer <COMFYUI_PASSWORD>` | `200` ~17 s after create |
| `GET /system_stats`, Basic `anyone:<COMFYUI_PASSWORD>` | `200` |
| `GET /?token=<COMFYUI_PASSWORD>` | `200` |
| `/ws` upgrade, no auth / with Bearer | `401` / `101` |
| FileBrowser `POST /api/login`, `admin` + `FILEBROWSER_PASSWORD` / + placeholder | `200` / `403` |

`/system_stats`: ComfyUI **0.44.0**, torch **2.13.0+cu132**, Python 3.12.3, `argv`
`main.py --listen 127.0.0.1 --port 18188` (the auth proxy owns `8188`). Generation, the
custom nodes (§6) and the empty checkpoints folder (§7) were last checked on the
2026-08-25 run of the older `cw3nka7d08` template. The ~4 min network-volume boot figure
comes from the earlier live run in
[golden path 02, variant B](../../runpod/golden-paths/02-comfyui-pod/variant-b-prebuilt.md)
(pod `7ydkt5vs4fst25`, 2026-07-07).
