# Golden path 03 — Whisper endpoint (audio → text)

**Goal / Status: COVERED — live-verified 2026-07-07 / Kind: serverless / Lane: runpodctl+Hub or flash**

Deploy a serverless endpoint that, given an audio URL (or base64 audio), returns
the transcription. This is a **serverless** path — request/response, scale-to-zero
— not a pod. Two variants were both live-verified; this folder splits them so you
can jump straight to the one you want.

## Lane choice (why serverless, and why Hub is the default)

Whisper is a request/response inference API → **serverless** (invoked via
`/run`/`/runsync`, scales to zero between requests). See the shape decision in
[../../../runpod-usage/reference/development-loop.md](../../../runpod-usage/reference/development-loop.md)
and the serverless specialization in
[../../../runpod-usage/reference/endpoint-workflows.md](../../../runpod-usage/reference/endpoint-workflows.md).

The least-fragile way to stand up a *known* worker is the **Runpod Hub**. This walkthrough
uses **runpodctl** (`serverless create --hub-id …`); with the MCP server connected,
`deploy-hub-repo` does the same thing in one tool call. A ready Hub worker means no handler code, no
`docker build --platform=linux/amd64`, no registry auth, no cloudpickle/import
gotchas — just `serverless create --hub-id …`. That's why **Variant A (Hub) is the
default**.

Rejected:
- **flash** — great for *custom/small* code-first handlers you iterate on, but for a
  heavy, prebuilt model you'd be re-implementing a faster-whisper handler that the
  Hub already ships and maintains. More moving parts, no upside here. (Still fully
  covered as [Variant B](variant-b-flash.md) for when you *do* want to own the code.)
- **Custom image + endpoint** — most fragile (write handler → build amd64 → push →
  maybe registry auth → create endpoint). Only worth it if no good Hub worker exists.

## Which variant should I use?

| | [Variant A — Hub](variant-a-hub.md) | [Variant B — flash](variant-b-flash.md) |
| --- | --- | --- |
| Approach | Deploy a maintained Hub worker | Write your own faster-whisper handler |
| Effort | ~2 min, zero code | ~15 min, you own the handler |
| Customization | Take the worker's model + I/O schema | Own the model size, I/O schema, pre/post-processing |
| Image | Heavy prebuilt WhisperX image | Lighter/cheaper image you control |
| Iteration | None needed (prebuilt) | `flash dev` on a real remote GPU (hot-reload) |
| Pick when | A **heavy, prebuilt, known** model has a good Hub worker | **Custom/small** workload, or no good Hub worker fits |

Rule of thumb: for a big prebuilt model with a solid Hub worker, flash is just
re-implementing it — stay on the Hub. Reach for flash when you need your own model
size / I/O / a lighter image, or nothing on the Hub fits.

## Variants

- [Variant A — Runpod Hub worker](variant-a-hub.md) (recommended)
- [Variant B — from scratch with flash](variant-b-flash.md)

## Input & output schema (shared)

Both variants speak the Runpod job API. Body is always `{"input": { ... }}`.

> **Variant B caveat:** a flash handler nests the value under its **parameter
> name** — see the raw-HTTP gotcha in [variant-b-flash.md](variant-b-flash.md).
> The schema below is the plain Hub contract (Variant A).

Key input fields (WhisperX Hub worker, Variant A):

| Field | Type | Req | Notes |
| --- | --- | --- | --- |
| `audio_file` | string | yes | **HTTP(S) URL** to the audio, **or base64-encoded audio** (optionally a `data:audio/wav;base64,…` data-URI prefix). Both verified. |
| `language` | string | no | ISO code (`en`, `fr`, …); auto-detected if omitted |
| `align_output` | bool | no | word-level timestamps (default false) |
| `diarization` | bool | no | speaker labels; needs `HF_TOKEN` env / `huggingface_access_token` |
| `batch_size` | int | no | default 64 |
| `initial_prompt`, `temperature`, `vad_onset`, `vad_offset`, `min_speakers`, `max_speakers` | — | no | see worker README |

**Output:** `{"output": {"detected_language": "en", "segments": [{"start","end","text", ...}]}}`.
The transcript is the concatenation of `segments[].text`.

**"Uploading" audio:** there is no file-upload step. Either (a) host the file at a
public URL and pass it as `audio_file`, or (b) base64-encode the bytes and pass the
string as `audio_file`. Base64 rides the job payload, so respect the limits:
`/run` ~10 MB, `/runsync` ~20 MB. For larger files, use a URL (presigned S3/GCS
works).

## Cross-cutting gotchas (shared)

- **Cold-start vs the `runsync` 60 s window.** The first request after idle
  cold-starts (image pull + model load) — ~20–90 s on the Hub, ~55–75 s on flash —
  which can exceed `runsync`'s 60 s sync window. Use `/run` + poll `/status/<id>`
  for the first call, then `runsync` once warm. **Bound any poll loop.** More in
  [../../../runpod-usage/reference/gotchas.md](../../../runpod-usage/reference/gotchas.md)
  ("Cold starts and timeouts").
- **Broken Hub worker: `ready` but jobs never run.** A worker showing `ready` while
  jobs sit `IN_QUEUE` with `inProgress: 0` is a broken/mis-dispatching image (or
  workers `throttled` on a scarce GPU pool). **Switch workers, don't wait it out.**
  There's no first-class serverless worker-log command in runpodctl/REST v1 —
  diagnose via the endpoint `/health` worker counts. (Details in Variant A.)
- **Delete returns 204, not JSON.** A DELETE / MCP `delete-*` may report an error
  like "Unexpected end of JSON input" because the REST API returns **204 No
  Content** (no body to parse). Treat it as success; confirm with a follow-up
  `get`/`list` (the resource should 404 / be absent).

## Cost & cleanup (shared)

`--workers-min 0` ⇒ **scale-to-zero**: no GPU billing while idle (you pay only per
request-second, plus the free scale-to-zero). This is the right cost posture for a
request/response API, so it's safe to leave an endpoint deployed. Delete test
resources when done:

```bash
runpodctl serverless delete <endpoint-id>
# flash apps can also be removed with: flash app delete <app-name>
```

See each variant file for the exact teardown command it used.
