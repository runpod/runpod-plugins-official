# Building a Docker image Runpod can run

Runpod pulls a container image and runs it on x86_64 Linux GPU/CPU hosts. For
serverless, the image runs a **handler**; for pods, the image runs whatever your
`CMD`/start script does. This file covers the serverless handler contract and the
build/push mechanics that apply to both.

## The serverless handler contract

A queue-based serverless worker is a Python script that starts the Runpod SDK
with a handler function:

```python
# handler.py
import runpod

def handler(job):
    job_input = job["input"]        # your request payload lives under "input"
    prompt = job_input.get("prompt")
    # ... do the work ...
    return {"result": prompt}       # returned value becomes the job output

runpod.serverless.start({"handler": handler})   # required — blocks and serves jobs
```

Request/result shape:

- The platform hands your handler a job dict: `{"id": "<uuid>", "input": { ... }}`.
  `id` is Runpod's job id; `input` is exactly what the client sent.
- Whatever the handler **returns** is the job result (must be JSON-serializable).
- Raising an exception marks the job `FAILED` and returns the error details.

Handler variants: return a value (standard), `yield` values (streaming — add
`return_aggregate_stream: True` to expose them via `/run`), or `async def` +
`yield` (async). Concurrent handlers serve multiple requests per worker.

**Load-balanced endpoints do not use a handler.** You expose your own HTTP server
(FastAPI, Flask, vLLM, etc.) and Runpod routes to it. The `runpod.serverless.start`
contract is only for queue-based endpoints.

Best practice: load models and other heavy state **at module level, outside the
handler**, so it initializes once per worker instead of once per request.

## A minimal Dockerfile

```dockerfile
FROM python:3.11.1-slim
WORKDIR /

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .

CMD ["python", "-u", "/handler.py"]
```

`requirements.txt` must include the `runpod` SDK plus your libraries:

```
runpod~=1.7.6
torch==2.0.1
transformers==4.30.2
```

> **Version pin gotcha (numpy 2.x):** if you `pip install torch==2.2.x`, also pin
> `numpy<2`. That torch wheel is built against NumPy 1.x; pip otherwise pulls NumPy
> 2.x and the image **builds and starts fine but crashes at inference** with
> `RuntimeError: Numpy is not available`. Testing the container locally (below) catches
> it before deploy (`gotchas.md`).

> **`cryptography` uninstall gotcha (on a `runpod/pytorch` base):** installing the
> `runpod` SDK on an official `runpod/pytorch` image (e.g. behind `runpod-torch-v280`)
> fails with `Cannot uninstall cryptography 41.0.7 … no RECORD file` — the base's copy is
> **Debian-managed**, so pip can't replace it with the newer one `runpod` wants. Fix:
> `pip install --ignore-installed cryptography runpod` (add `--break-system-packages` for
> the base's PEP-668 "externally managed" pip). Install conflict-free deps like
> `faster-whisper` first, on their own. Verified live 2026-07-10 (golden path 09).

For GPU/CUDA workloads, start from a CUDA base and install Python yourself, or
build on a framework image:

```dockerfile
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y python3.11 python3-pip
# or: FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
```

Keep images small (slim bases, multi-stage builds, `.dockerignore`, clean up apt
caches) — smaller images pull and cold-start faster.

## Build for x86_64 — always `--platform=linux/amd64`

Runpod hosts are x86_64. If you build on an ARM machine (Apple Silicon Mac) the
default build produces an arm64 image that Runpod cannot run. **Always pass the
platform flag:**

```bash
docker build --platform=linux/amd64 -t DOCKER_USER/worker-name:v1.0.0 .
```

This is the single most common deployment failure. It applies to serverless
workers, pod images, and template images alike.

## Pin tags — never rely on `latest`

`latest` is mutable: it points to whatever was last pushed without an explicit
tag, and Runpod caches images per host, so a worker can silently keep running a
stale `latest`. Use explicit semantic versions (`v1.0.0`, `v1.0.1`), and for
critical deploys pin the immutable digest (`name:tag@sha256:...`).

```bash
docker build --platform=linux/amd64 -t DOCKER_USER/worker-name:v1.0.0 .   # good
docker build -t DOCKER_USER/worker-name:latest .                          # avoid
```

## Test the container locally before pushing

Provide a `test_input.json` next to the handler and run the image — the SDK
detects it, runs one job, prints the output, and exits:

```json
{ "input": { "prompt": "Hey there!" } }
```

```bash
python handler.py                                          # bare, on host
python handler.py --test_input '{"input":{"prompt":"hi"}}' # inline input
docker run -it DOCKER_USER/worker-name:v1.0.0              # inside the image
docker run --rm --gpus all DOCKER_USER/worker-name:v1.0.0  # with GPU
```

Fix any import/dependency/handler errors here — it is far faster than debugging
after deploy.

## Push, and handle private images

```bash
docker login
docker push DOCKER_USER/worker-name:v1.0.0
```

Runpod pulls public images with no extra config. For **private** registry images
you must register container-registry credentials with Runpod once (Console →
Settings → Container Registry, then select the credential on the template/endpoint).
Runpod supports `docker login`-style credentials. Without this, workers fail to
pull the image.

## Deploy the pushed image as a serverless endpoint

`runpodctl serverless create` takes **`--template-id` or `--hub-id`, not `--image`** —
so deploying your own image is a **two-step**: register a serverless *template* pointing
at the tag, then create the endpoint from that template. Use `--compute-type CPU` for a
CPU-only image to sidestep GPU scarcity, and `--workers-min 0` for scale-to-zero:

```bash
runpodctl template create --name my-tpl --serverless \
  --image DOCKER_USER/worker-name:v1.0.0 --container-disk-in-gb 10   # → template id
runpodctl serverless create --template-id <template-id> --name my-ep \
  --compute-type CPU --workers-min 0 --workers-max 1                 # → endpoint id
```

For a **private** image, attach the registry credential to the template (Console →
Container Registry, or `runpodctl registry create`) so workers can pull it. Full worked
example: golden path 05 (`golden-paths/05-model-to-endpoint-pipeline/README.md`).

## Payload limits

Handler input/output flows through the job API: `/run` caps at ~10 MB, `/runsync`
at ~20 MB. For anything larger, pass URLs or use a network volume / S3 and return
references instead of inlining bytes.
