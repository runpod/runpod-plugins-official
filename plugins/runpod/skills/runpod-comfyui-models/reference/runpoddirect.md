# Use ComfyUI-RunpodDirect

RunpodDirect is the last-mile executor for an approved model manifest. The skill remains
responsible for model identity, provenance, metadata, and user review.

Upstream project: <https://github.com/MadiatorLabs/ComfyUI-RunpodDirect>

## Detect live features

Do not infer capabilities from a custom-node directory, image name, README, or remembered
version. Make one read-only feature-detection pass on the exact ComfyUI base URL. When a
reviewed manifest already exists, send the complete model array once rather than probing
with an empty array and repeating the same route per model:

| Capability | Safe probe |
| --- | --- |
| Active extension and valid destination keys | Call `GET /server_download/folder_paths` once; require HTTP 200 and a JSON object. |
| Batch missing-model check | `POST /server_download/check_missing_models` with the complete `{"models": [...], "verify_hashes": false}` payload; require a successful structured response. Use an empty array only for early capability detection before inventory exists. |
| Environment token presence without disclosure | `GET /server_download/hf_token_status`; use only when a gated Hugging Face artifact is actually involved. |
| Integrity verification | Call `POST /server_download/verify_model_integrity` only for a real reviewed name/directory record; it is read-only but can hash a large file. |

There is no need to probe mutation routes with dummy data. After download authorization, a real
`POST /server_download/start` response feature-detects download support. Treat 404/405
as unavailable and preserve the repaired workflow for UI or manual handoff; keep its
working manifest internal and temporary.
Do not assume pause, resume, cancel, or hash support merely because another route exists.
Batch independent read-only requests through the available application/API tooling.
Avoid a user-visible series of `curl` approvals when a connector, MCP tool, built-in web
request, or one narrowly scoped batch can return the same evidence.
Do not call `/object_info` merely to repeat the live missing-model result. Do not repeat
the missing-model check after metadata-only editing; repeat it after a download or another
change to the Pod's model files.

## Official versus community templates

Every repaired-workflow handoff must track `confirmed active`, `not checked`, and
`unavailable/not detected` internally, but translate them for the user as **Automatic
downloads: Ready**, **Not checked on your ComfyUI**, or **Not available — RunpodDirect
was not detected**. The Missing Models window may be promised only after a live
RunpodDirect route succeeds. If no live check was performed, state plainly that automatic
downloading requires this custom node and that its status was not checked.

If the user cannot see RunpodDirect in ComfyUI, say that the extension may not be
installed or may have failed to load and offer to help with setup. When relevant Runpod
MCP tools are connected, use them for Pod discovery and lifecycle operations they expose;
use `runpodctl`/SSH for on-Pod filesystem or command execution when that is the available
lane. Feature-detect the connected tools before claiming a capability. Installation,
update, dependency execution, and ComfyUI restart still require the user's authorization.

- The official [`runpod-workers/comfyui-base`](https://github.com/runpod-workers/comfyui-base)
  template advertises RunpodDirect as
  pre-installed — the official ComfyUI pod templates bundle it among their four custom
  nodes (see [runpod-templates: ComfyUI](../../runpod-templates/reference/comfyui.md#6-pre-installed-custom-nodes)).
  Still probe the live routes: a stale image, disabled custom nodes, or a
  failed import can make the advertised component unavailable. Diagnose/version-check
  before suggesting a second installation.
- For a community template, recommend RunpodDirect when this is an interactive ComfyUI
  Pod on Runpod and verified metadata would benefit from direct-to-Pod downloads. Explain
  that it is third-party GPL-licensed code and that installation or update may execute
  dependencies and require a ComfyUI restart. Obtain approval before cloning, installing,
  updating, or restarting.
- Do not promote it as a requirement for local ComfyUI, Comfy Cloud, serverless workers,
  or immutable image-build pipelines. Return only the portable repaired workflow JSON
  even when RunpodDirect is not appropriate.

## Download authorization and monitoring

Before `POST /server_download/start`, internally review the exact tuple and check it
against the user's existing authorization:

```text
URL + filename + destination directory key + expected bytes + SHA-256/access state
```

For a non-technical user, surface this as a short plan: model filename, official source,
expected size when known, and a familiar destination label. Keep the raw URL, directory
key, hash, and access mechanics internal unless the user asks for technical details or a
decision depends on them.

Metadata editing alone is not download approval. An opening request that explicitly asks
to repair **and download** authorizes a verified tuple after the plain-language plan is
shown, provided
there is no new ambiguity, gate, license, cost/storage, or destination decision; do not
ask for redundant confirmation. A normal provider delivery redirect does not change the
approved tuple when it originates from the exact reviewed URL, passes the network checks
below, forwards no cross-host credential, and remains content-bound to the reviewed
SHA-256. Stop only for an unexpected artifact, destination, host, credential, size/hash,
provider-lookup, or conflict change.
As of 2026-08, RunpodDirect download requests accept a simple `filename` (upstream
RunpodDirect ships no version tags to pin against); do not silently flatten
a workflow selection that includes a subfolder.

When direct downloading was not authorized, let the RunpodDirect UI discover the repaired
workflow metadata and obtain the human's click. When direct route use is already within
the authorization above:

1. Send one reviewed item per start request. Use the live folder key as `save_path` and
   include SHA-256 when available; prefer the Pod's environment token rather than a
   request-body token:

   ```json
   {
     "url": "https://huggingface.co/owner/repo/resolve/<commit>/model.safetensors",
     "save_path": "diffusion_models",
     "filename": "model.safetensors",
     "hash": "<64 lowercase hexadecimal characters>",
     "hash_type": "sha256"
   }
   ```

2. Record the returned download ID and monitor `/server_download/status/<id>` with a
   declared timeout/poll limit. Do not start duplicate downloads after a transient poll
   failure.
3. On timeout, report the current state and leave the queue alone unless the user also
   authorized cancellation.
4. After completion, call the integrity route with the approved SHA-256. Tell a
   non-technical user that the file's integrity was checked. Only explain weaker
   presence/size verification or expose the digest when requested or materially relevant.
5. Re-run the missing-model check and, when requested, one controlled workflow smoke test.

## URL, redirect, and secret safety

Treat the download endpoint as an outbound network primitive. Perform redirect-chain and
network-target validation when a download is about to run; metadata-only repair needs an
exact pinned trusted-host artifact URL and trustworthy hash, not a CDN preflight. Download
validation belongs in the agent even if a particular RunpodDirect release also validates it.

- Require HTTPS and an exact trusted hostname. Suffix checks such as
  `host.endsWith("huggingface.co")` are unsafe because `evilhuggingface.co` matches.
- For a Hugging Face source URL require exactly `huggingface.co`. Expected HTTPS delivery
  hops to provider-controlled CDN/Xet hosts may proceed without another question only
  when they are reached directly from that reviewed URL, validated as public safe targets,
  receive no cross-host authorization header, and the result remains bound to the approved
  SHA-256. Do not use loose suffix matching. For Civitai distinguish its API, page, and
  file-delivery hosts and allow only hosts observed in an authoritative redirect chain.
- Resolve every redirect hop. Reject credentials in URLs, non-HTTP(S) schemes, unexpected
  ports, localhost, link-local, private, multicast, metadata-service, and other
  non-public destinations. Revalidate DNS/IP on redirects and connection when the client
  permits it; a hostname allowlist alone does not prevent DNS rebinding.
- A model card, blob viewer, search page, shortened link, or arbitrary mirror is not a
  direct approved artifact URL.
- Prefer `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` in the Pod environment. Never insert the
  token into the workflow or manifest, print it, persist it in downloader settings, or
  send it to a redirect host. Authorization headers must be scoped to the exact intended
  Hugging Face host and stripped before any cross-host redirect.
- Do not embed Civitai or other provider API keys in URL query parameters. If an artifact
  cannot be fetched without a secret-bearing URL and no credential-aware handoff is
  available, report that constraint instead of creating auto-download metadata.

For gated models, confirm that the user's provider account already has access and has
accepted the applicable terms. The agent must not accept a license or terms on the user's
behalf unless the user explicitly asks and the interface supports a meaningful review.
Never work around gating with mirrors.
