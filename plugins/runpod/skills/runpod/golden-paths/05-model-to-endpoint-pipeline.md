---
lanes: [docker, runpodctl, rest, hf]
mcp: partial
concepts: [container-image, template, serverless-endpoint, serverless-handler, job, worker]
---

# Golden path 05 — custom model → serverless endpoint (hf → docker → runpodctl)

**Goal:** from "serve this custom model as an endpoint", take a model, bake it into a
serverless **handler image**, push it, deploy an endpoint from that image, and verify it
with a real request. This is the **cross-lane** path — the only one that chains the
**companion CLIs** (`hf`/`docker`) into the **infra lane** (runpodctl), exercising the
ordering rule (**artifacts before infra**) and credential boundaries a single lane never
hits.
**Status:** COVERED — live-verified 2026-07-10 end to end. Baked
`distilbert-base-uncased-finetuned-sst-2-english` into a CPU image
(`<your-registry>/rp-gp05:v2`), pushed it public, created a **CPU** serverless endpoint from a
runpodctl template, and got a `COMPLETED` job with real output. Cold call: ~73 s queue
(image pull + worker init) + 0.86 s exec; warm `/runsync`: ~0.16 s exec.
**Lane(s):** docker (build/push) + runpodctl (template + serverless create) + Runpod REST (`/run`, `/status`, `/runsync`, `/health`)

## When to use this
Only when **no Hub worker and no `flash` handler fits** — those are cheaper (no Docker,
no registry). Reach for this custom-image path when you must ship a specific container:
pinned system deps, a private model baked in, a bespoke runtime. It's the last resort
(golden path [03](03-whisper-endpoint/README.md);
[`../../runpod-usage/reference/endpoint-workflows.md`](../../runpod-usage/reference/endpoint-workflows.md)).

**Bake vs mount:** bake the model **into the image** (this path) for small/private models —
no runtime download, self-contained. For a huge or public/gated model, prefer a **network
volume** (golden path [07](07-network-volume-handoff.md)) or a cached model, so you don't
bloat the image and every cold start (see `reference/gotchas.md` "Model not baked or mounted").

## Prerequisites
- `RUNPOD_API_KEY` resolvable (runpodctl + REST). Verify: `curl -s -o /dev/null -w '%{http_code}'
  https://api.runpod.io/v2/pods -H "Authorization: Bearer $RUNPOD_API_KEY"` → `200`.
- `docker` running and `docker login` to a registry you can push to (`<your-registry>`,
  e.g. your Docker Hub user). A **public** image needs no Runpod registry auth; a
  **private** one does (see gotchas).
- `runpodctl` installed + authenticated.
- `HF_TOKEN` only if the model is **gated/private** (the SST-2 model is ungated — not needed).

## The lane handoff (who does what, in order)
```
docker (build --platform=linux/amd64 + push)  →  runpodctl (template → endpoint)  →  REST (/run → poll → /runsync)
     produces  <your-registry>/rp-gp05:v2               consumes that exact tag           invoke + verify
     └──────────── artifact exists ────────────┘  └──────── infra points at it ───────┘
```
The handoff point is the **image tag**. Everything left of it produces the tag; everything
right consumes it. **Push before you create the endpoint** — an endpoint only references a
tag, so creating it first just gives workers that can't pull.

## Walkthrough (verified commands)

### 1. Artifact: handler (Runpod contract) + model bake + Dockerfile
The handler loads the model **once at import** (cold-start rule) and reads `job["input"]`:
```python
# handler.py
import runpod
from transformers import pipeline

MODEL = "distilbert-base-uncased-finetuned-sst-2-english"
classifier = pipeline("sentiment-analysis", model=MODEL, device=-1)  # device=-1 => CPU

def handler(job):
    job_input = job["input"]                       # {"input": {...}} contract
    text = job_input.get("text") or job_input.get("prompt")
    if not text:
        return {"error": "provide 'text' (or 'prompt') in input"}
    top = classifier(text)[0]                      # {'label': 'POSITIVE'|'NEGATIVE', 'score': ...}
    return {"text": text, "label": top["label"], "score": round(float(top["score"]), 4)}

runpod.serverless.start({"handler": handler})      # required — blocks and serves jobs
```
Bake the model at **build** time (a separate script the Dockerfile runs), so the worker
never downloads at runtime:
```python
# download_model.py — runs during docker build
from transformers import pipeline
pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english", device=-1)
print("MODEL_BAKED")
```
```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /
# CPU-only torch keeps the image small (no CUDA) — this is a CPU model.
RUN pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY download_model.py .
RUN python download_model.py                       # <-- model baked into this layer
COPY handler.py .
CMD ["python", "-u", "/handler.py"]
```
```
# requirements.txt
runpod~=1.7.6
transformers==4.44.2
numpy<2            # <-- REQUIRED with torch 2.2.2 (see gotcha #1); pip pulls numpy 2.x by default
```

### 2. Test the container locally BEFORE pushing (this caught a real bug)
The Runpod SDK runs one job from a `test_input.json` in the working dir, prints the output,
and exits — a full offline dry run:
```bash
echo '{ "input": { "text": "This movie was fantastic" } }' > test_input.json
docker build --platform=linux/amd64 -t <your-registry>/rp-gp05:v2 .
docker run --rm --platform=linux/amd64 -v "$PWD/test_input.json:/test_input.json" <your-registry>/rp-gp05:v2
```
Observed (after the numpy<2 fix — the first build without it failed here, see gotcha #1):
```
DEBUG  | local_test | run_job return: {'output': {'text': 'This movie was fantastic', 'label': 'POSITIVE', 'score': 0.9999}}
INFO   | Job local_test completed successfully.
```

### 3. Push the image (public → no registry auth needed)
```bash
docker push <your-registry>/rp-gp05:v2
# v2: digest: sha256:a429...  — 2.31 GB, public on Docker Hub
```

### 4. Infra: template from the image, then a CPU endpoint (scale-to-zero)
`runpodctl serverless create` takes **`--template-id` or `--hub-id`, not `--image`** — so
it's a **two-step**: create a serverless template pointing at the tag, then the endpoint from
the template. `--compute-type CPU` dodges GPU scarcity for a CPU model:
```bash
runpodctl template create --name rp-gp05-tpl --serverless \
  --image <your-registry>/rp-gp05:v2 --container-disk-in-gb 10
# → template id, e.g. <template-id>

runpodctl serverless create --template-id <template-id> \
  --name rp-gp05-ep --compute-type CPU \
  --workers-min 0 --workers-max 1                    # scale-to-zero, ~$0 idle
# → endpoint id, e.g. <endpoint-id>
```

## Verify it works (the actual test + observed output)
Cold start pulls the 2.3 GB image + inits the worker, which exceeds `/runsync`'s ~60 s
window — so the **first** call uses `/run` + poll `/status`:
```bash
EP=<endpoint-id>
curl -s "https://api.runpod.ai/v2/$EP/health" -H "Authorization: Bearer $RUNPOD_API_KEY"
# {"workers":{"initializing":1,"ready":0,...}}  — worker is pulling the image

JOB=$(curl -s "https://api.runpod.ai/v2/$EP/run" -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"text":"I absolutely love how fast Runpod serverless is!"}}' | jq -r .id)
# then poll /status/$JOB until COMPLETED (took ~10 polls / ~73 s on the cold call)
```
Observed cold result (real, 2026-07-10):
```json
{ "delayTime": 72949, "executionTime": 857, "status": "COMPLETED",
  "output": { "text": "I absolutely love how fast Runpod serverless is!",
              "label": "NEGATIVE", "score": 0.9646 } }
```
Once warm, `/runsync` is fine (real outputs — both labels correct):
```bash
curl -s "https://api.runpod.ai/v2/$EP/runsync" -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"text":"This movie was absolutely fantastic, I loved every minute."}}'
# → {"delayTime":1673,"executionTime":158,"status":"COMPLETED",
#    "output":{"label":"POSITIVE","score":0.9999, ...}}
# and a clearly-negative text → {"label":"NEGATIVE","score":0.9994, ...}
```
Green: a `COMPLETED` job returning the model's real prediction. Warm exec ~158 ms.

## Gotchas we hit
1. **`numpy<2` with torch 2.2.2 (the build-passes-then-inference-crashes trap).** The image
   **built and the worker started fine**, but the first job crashed at inference with
   `RuntimeError: Numpy is not available` — pip had pulled numpy 2.x, which the torch-2.2.2
   wheel (built against numpy 1.x) can't use. Pinning `numpy<2` fixed it. **The local
   `test_input.json` run (step 2) caught this before deploy** — the import warning
   `Failed to initialize NumPy: _ARRAY_API not found` is the early tell. Always run the
   container locally first (`reference/docker.md` "Test the container locally").
2. **`serverless create` has no `--image` — it's a two-step.** It requires `--template-id`
   or `--hub-id`. So `template create --serverless --image <tag>` first, then
   `serverless create --template-id <id>`. (This resolves the old SPEC's open question.)
3. **`--compute-type CPU` to dodge GPU scarcity.** A CPU model doesn't need a GPU pool;
   the CPU endpoint scheduled immediately. Default compute-type is `GPU`.
4. **Public image ⇒ no registry auth.** Nothing extra to configure. A **private** image
   needs a Runpod registry credential (`runpodctl registry create`, or Console → Container
   Registry) attached to the template, or workers can't pull (`reference/gotchas.md`).
5. **`--platform=linux/amd64` always.** Built on Apple Silicon; without the flag the image
   is arm64 and fails on Runpod's x86 hosts with "exec format error".
6. **Cold start is real (~73 s here).** Image pull + worker init blew past `/runsync`'s
   window, so the first call must be `/run` + poll `/status`. Warm calls are ~0.16 s.
7. **Model quirk, not a bug:** SST-2 is trained on **movie reviews**, so out-of-domain text
   like "love how fast Runpod is" can misclassify (it returned NEGATIVE). The model
   discriminates correctly on in-domain text (verified: clear positive → POSITIVE 0.9999,
   clear negative → NEGATIVE 0.9994). Use in-domain phrasing when sanity-checking a demo model.

## Cost & cleanup
```bash
runpodctl serverless delete <endpoint-id>          # the endpoint
runpodctl template delete <template-id>                # the template
runpodctl serverless list && runpodctl pod list && runpodctl network-volume list  # confirm clean
```
Endpoint is scale-to-zero (`--workers-min 0`), ~$0 idle — but delete it anyway. The pushed
Docker Hub image (`<your-registry>/rp-gp05:v2`, public) was **left in place** so this doc
references a real, pullable tag; it costs nothing and is harmless. No pod or volume is
created by this path.

## Skill gaps folded back
- **`reference/docker.md`** — added that `runpodctl serverless create` takes
  `--template-id`/`--hub-id` (not `--image`): it's a two-step (template → endpoint); and a
  note that CPU workers use `--compute-type CPU`.
- **`reference/gotchas.md`** — added the **numpy 2.x vs torch** gotcha (build succeeds, then
  inference throws `Numpy is not available`; pin `numpy<2`), reinforcing "test the container
  locally before pushing."
- Confirmed correct in practice: `--platform=linux/amd64` requirement, explicit tag over
  `latest`, public-image-needs-no-auth, cold-start → `/run`+poll then `/runsync`.
