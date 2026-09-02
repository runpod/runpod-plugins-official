# The Runpod development loop (golden loop)

Every Runpod task an agent runs follows the same spine — proven across the golden
paths (Ollama pod, ComfyUI pod, Whisper endpoint). Learn this loop; it has two
specializations depending on the workload shape.

```
decide shape → prefer prebuilt → plan resources → provision → (set up if scratch)
   → run/deploy → VERIFY with a real request → deliver → cost-guard + teardown
```

## 1. Decide the workload shape

- **A server you open / interactive / long-lived** (Ollama, ComfyUI, Jupyter,
  training) → a **pod**. Reached at a proxy URL. Detailed loop: `pod-workflows.md`.
- **A request/response API that should scale to zero** (transcription, inference
  endpoint) → a **serverless endpoint**. Invoked via `/run`/`/runsync`. Detailed
  loop: `endpoint-workflows.md`.

See `concepts.md` if unsure.

## 2. Prefer a prebuilt / known option before building from scratch

This is the biggest lever for speed and reliability:

- Pod service → look for an **official Runpod template / prebuilt image**
  (`runpodctl template search <app>`) — it auto-starts and skips the install
  gotchas.
- Serverless → look for a **Hub worker** (`runpodctl hub search <app>`).
- Build **from scratch** (install on a pod, or `flash`, or a custom image) only
  when no good prebuilt exists, or you need something **custom or lighter** than
  what's shipped.

## 3. Plan resources

GPU/VRAM and the **CUDA floor** (`gpu-selection.md` — default
`--min-cuda-version 12.8` on any GPU create; a create with no floor accepts any host
CUDA version and a modern image can land on one too old to run it), storage
(**default a network volume** — `storage.md`), and the execution lane (`../../runpod/SKILL.md` router:
runpod-mcp / runpodctl / flash).

## 4. Provision & 5. Set up

Provision through the chosen lane. If from-scratch, do the setup step of the
matching sub-loop (pods: SSH-exec install; serverless: write handler / build image).
Prebuilt options usually skip setup entirely.

## 6. Verify with a real request — "up" ≠ "ready"

The load-bearing step. A pod showing **Running**, or a serverless worker showing
**ready**, does **not** mean it serves. Always confirm from **outside** with a real
call, and expect a warm-up window:

- **Pod:** poll the proxy URL until it answers — expect ~30–60s of **502s** during
  boot.
- **Serverless:** send a real input; the **first call cold-starts** (may exceed
  `runsync`'s 60s → use `/run` + poll `/status/<id>`). A worker that is `ready` but
  leaves jobs `IN_QUEUE` with `inProgress: 0` is a **broken image** — switch, don't
  wait.

Only report success once a real request returns the right result.

## 7. Deliver

Return the access URL (pod) or endpoint id + a **working sample call** (serverless),
and note the security posture (proxy URLs and endpoints are public unless you add
auth).

## 8. Escalate on manual steps

If something needs a human — OAuth, a quota/capacity increase, a gated-model
license, a missing credential, a payment issue — **stop and say exactly what's
blocked**. Don't spin or fake progress.

## 9. Cost-guard + teardown

- Pod → `--terminate-after <ts>` at creation (deletes it), not `--stop-after`.
- Serverless → `--workers-min 0` (scale-to-zero, ~$0 idle).
- Delete test resources when done (`runpodctl pod remove` / `serverless delete` /
  `flash app delete`; then any network volume).

## Which sub-loop?

| Workload | Sub-loop |
| --- | --- |
| A service you open at a URL (Ollama, ComfyUI, dev box, training) | `pod-workflows.md` |
| A request/response API that scales to zero (Whisper, inference) | `endpoint-workflows.md` |
