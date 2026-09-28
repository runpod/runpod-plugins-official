---
lanes: [rest]
mcp: full
concepts: [public-endpoint, job]
---

# Golden path 11 — call a Runpod Public Endpoint (ready hosted model, no deploy)

**Goal:** from "I just need a model's output, not my own infrastructure", call a
**Runpod Public Endpoint** — a hosted, pre-deployed model you invoke with only your API
key. No Docker image, no template, no network volume, no workers to scale, nothing to
clean up. You pay per call for the output you actually get. This is the **zero-infra**
path: the answer to "do I even need to deploy anything?" before you reach for 05/09.
**Status:** ✅ COVERED — live-verified 2026-07-13. Called the `qwen3-32b-awq` text model
live with `RUNPOD_API_KEY` on both the native `/runsync` and the OpenAI-compatible
`/openai/v1/chat/completions` routes. Got `COMPLETED` jobs with real output. Cold call:
~44 s queue + ~3.5 s exec; warm: ~16 ms queue + ~3.2 s exec. Total spend for all test
calls: **~$0.0025**.
**Lane(s):** Runpod REST invoke only (`POST https://api.runpod.ai/v2/<model-slug>/runsync`
| `/run` + `/status`), plus the OpenAI-compatible route for LLMs. No infra lane at all.

## When to use this
Reach for a Public Endpoint **first** whenever a Runpod-hosted model already does what
you need. It's the cheapest possible path to a result because you skip the entire deploy
loop:

| You want… | Use |
| --- | --- |
| Output from a **model Runpod already hosts** (Flux, WAN, Qwen3, TTS, …) | **Public Endpoint (this path)** — zero infra, pay-per-output |
| Your **own model / custom code / pinned deps** served as an endpoint | Self-deploy: golden path [05](05-model-to-endpoint-pipeline.md) (custom image) or [09](09-custom-serverless-dev-loop/README.md) (dev loop) |
| A **standard OSS model** but you want to control the worker/scaling | Hub worker / flash — golden path [03](03-whisper-endpoint/README.md) |
| A long-running interactive session (Jupyter, SSH, training) | A **pod** — golden paths [01](01-ollama-pod.md), [04](04-finetune-pod.md), [06](06-dev-pod.md) |

Rule of thumb: **if the model is on the Public Endpoints list and the schema fits, do
not deploy.** You only move to 05/09 when there's no hosted model for your use case, or
you need a private model, custom pre/post-processing, or a specific runtime. Public
Endpoints have **no cold-start image pull to own, no idle cost, and nothing to delete** —
the trade is you don't control the worker, the model set is fixed, and you can't bake in
custom code.

## Prerequisites
- A Runpod account **with credits** (Public Endpoints are pay-per-call; a call fails if
  you have no balance).
- `RUNPOD_API_KEY` resolvable. Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://rest.runpod.io/v1/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`.
- **Nothing else.** No Docker, no runpodctl, no template, no volume. The same account API
  key that talks to REST invokes every Public Endpoint.

## The available models (as of 2026-07-13)
Browse/test in the [Hub playground](https://console.runpod.io/hub?tabSelected=public_endpoints).
Each model is a fixed slug you invoke at `https://api.runpod.ai/v2/<slug>/runsync`.

| Type | Examples (slug) | Price (output-based) |
| --- | --- | --- |
| **Image** | `black-forest-labs-flux-1-schnell`, `black-forest-labs-flux-1-dev`, `qwen-image`, `z-image-turbo` | $0.0024–$0.24 / MP or / image |
| **Video** | `wan-2-5`, `kling-v2-1`, `seedance-1-5-pro`, `sora-2` | $0.10–$2.25 per clip / second |
| **Text (LLM)** | `qwen3-32b-awq`, `granite-4` | $10.00 / 1M tokens |
| **Audio (TTS)** | `chatterbox-turbo`, `minimax-speech` | $0.001 / s, $0.05 / 1K chars |

The cheapest thing to prove live is a **tiny text request** (a handful of tokens costs a
fraction of a cent) or a small **Flux Schnell** image (512×512 ≈ $0.0006). This path was
verified on `qwen3-32b-awq` because text output is trivial to eyeball.

## Walkthrough (verified commands)

### 1. Call a model synchronously — that's the whole thing
No setup. Point `/runsync` at the model slug, pass `input`, send your key:
```bash
export RUNPOD_API_KEY=...            # your account key
curl -s -X POST "https://api.runpod.ai/v2/qwen3-32b-awq/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"prompt":"Reply with exactly: Runpod public endpoints work.",
                "max_tokens":16,"temperature":0}}'
```
Observed (real, cold, 2026-07-13):
```json
{ "delayTime": 44073, "executionTime": 3469, "status": "COMPLETED",
  "id": "sync-4c4c4f9c-...-u1", "workerId": "kial9wg5uyd12h",
  "output": [ { "choices": [ { "tokens": [ " We offer fast, scalable compute ... How are your public endpoints working for your users? ..." ] } ],
               "cost": 0.0011, "usage": { "input": 10, "output": 100 } } ] }
```
`COMPLETED`, a real completion, and `output.cost` = **$0.0011** for this call. The 44 s
`delayTime` is a cold worker on Runpod's shared pool warming up; the next call was warm.

### 2. For an LLM, prefer the OpenAI-compatible route
Text models expose an OpenAI-compatible API at
`https://api.runpod.ai/v2/<slug>/openai/v1/...`. Use it for chat models — it applies the
**chat template** and **honors `max_tokens`** (the native `/runsync` prompt does neither;
see gotchas):
```bash
curl -s -X POST "https://api.runpod.ai/v2/qwen3-32b-awq/openai/v1/chat/completions" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-32B-AWQ",
       "messages":[{"role":"user","content":"Say hello in one word."}],
       "max_tokens":10,"temperature":0}'
```
Observed (real, 2026-07-13) — note `finish_reason:"length"` and `completion_tokens:10`,
i.e. `max_tokens` was respected:
```json
{ "object": "chat.completion", "model": "Qwen/Qwen3-32B-AWQ",
  "choices": [ { "index": 0, "finish_reason": "length",
    "message": { "role": "assistant", "content": "<think>\nOkay, the user wants me to say" } } ],
  "usage": { "prompt_tokens": 14, "completion_tokens": 10, "total_tokens": 24 },
  "cost": 0.00024 }
```
This also means you can drop a Public Endpoint into any OpenAI SDK by setting
`base_url="https://api.runpod.ai/v2/qwen3-32b-awq/openai/v1"` and `api_key=$RUNPOD_API_KEY`.

### 3. For slow generations (video, big images), go async
Same slug, `/run` returns a job id immediately; poll `/status/<id>` until `COMPLETED` —
identical to the serverless invoke contract in
[`reference/endpoint-workflows.md`](../../runpod-usage/reference/endpoint-workflows.md):
```bash
JOB=$(curl -s -X POST "https://api.runpod.ai/v2/wan-2-5/run" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"prompt":"..."}}' | jq -r .id)
curl -s "https://api.runpod.ai/v2/wan-2-5/status/$JOB" -H "Authorization: Bearer $RUNPOD_API_KEY"
```

## Verify it works (the actual test + observed output)
Green = a `COMPLETED` job carrying real model output and a non-zero `output.cost`. Two
live checks confirmed the path end to end:

1. **Cold native call** → `COMPLETED`, 100 output tokens, `cost 0.0011`, `delayTime 44073`.
2. **Warm native call** (2nd request, seconds later) → `COMPLETED`, `delayTime` dropped to
   **16 ms**, exec ~3.2 s, `cost 0.00113`. Same `workerId` — the warmed worker was reused.
3. **OpenAI-compatible call** → `COMPLETED`, `max_tokens:10` honored
   (`finish_reason:"length"`, `completion_tokens:10`), `cost 0.00024`.

The response envelope (`delayTime`, `executionTime`, `status`, `id`, `workerId`,
`output`) is the **same shape as a self-deployed serverless endpoint** — so tooling that
polls your own endpoints works unchanged against Public Endpoints.

## Gotchas we hit
1. **Native `input.prompt` is a raw completion, not a chat turn.** On `/runsync`, the
   text model continued our prompt as free text and ignored the instruction ("Reply with
   exactly…") — it rambled. Qwen3 is a chat/reasoning model, so a bare prompt with no chat
   template drifts. **For instruction-following, use the OpenAI-compatible
   `/openai/v1/chat/completions` route** (step 2), which applies the chat template.
2. **Native `/runsync` ignored `max_tokens`.** We sent `max_tokens:16` and later `8`; both
   returned exactly **100 output tokens** (`usage.output:100`). The OpenAI route honored
   `max_tokens` precisely. Budget/latency-control on text models → use the OpenAI route.
3. **Reasoning models emit `<think>…` and burn tokens before the answer.** With a tiny
   `max_tokens` the OpenAI call was cut off *inside* its `<think>` block and never reached
   the answer. Give reasoning models enough `max_tokens` (or a model without a think phase)
   when you cap output.
4. **Cost is per *output*, and you're billed on the real output, not your request.** A
   "tiny" text request still returned 100 tokens on the native route (see #2), so cost is
   set by what the model produces. Failed generations are not charged, per the docs.
5. **Cold start is on a shared pool you don't control (~44 s here).** You can't pre-warm or
   set min-workers like your own endpoint — the first call after idle just waits. Use `/run`
   + `/status` for anything that might exceed `/runsync`'s ~60 s window (video, large images).
6. **Output URLs expire after 7 days.** Image/video/audio models return `image_url` /
   `video_url` / `audio_url` that expire — **download immediately** if you need to keep them.
7. **Model set is fixed and slugs are exact.** You can only call models Runpod hosts, at
   their exact slug (e.g. `qwen3-32b-awq`, `black-forest-labs-flux-1-schnell`). No hosted
   model for your case ⇒ self-deploy ([05](05-model-to-endpoint-pipeline.md) /
   [09](09-custom-serverless-dev-loop/README.md)).

## Cost & cleanup
- **Total spend for this live verification: ~$0.0025** (three text calls: $0.0011 +
  $0.00113 + $0.00024).
- **Nothing to clean up.** This path creates **no endpoint, template, volume, or pod** —
  there is no resource to delete and nothing accrues idle cost. That absence of cleanup is
  the whole point of the path.

## Skill gaps folded back
- This path documents the **decision gate that precedes 03/05/09**: check the Public
  Endpoint catalog *before* deciding to deploy. Consider linking it from
  [`reference/development-loop.md`](../../runpod-usage/reference/development-loop.md)'s
  "pod vs serverless" triage as an earlier "do you need to deploy at all?" branch.
- Confirmed the Public Endpoint invoke contract is **identical** to a self-deployed
  endpoint (`/run`, `/runsync`, `/status`, same response envelope, `Authorization: Bearer
  $RUNPOD_API_KEY`) — existing invoke tooling in
  [`reference/endpoint-workflows.md`](../../runpod-usage/reference/endpoint-workflows.md)
  works against `api.runpod.ai/v2/<model-slug>/…` unchanged.
- Documented two LLM-specific gotchas worth carrying into any text-model guidance: native
  `/runsync` **ignores `max_tokens` and applies no chat template**, whereas the
  `/openai/v1/chat/completions` route honors both — use the OpenAI route for chat models.
