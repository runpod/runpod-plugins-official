---
lanes: [docker]
mcp: none
concepts: [container-image, pod, serverless-endpoint, serverless-handler]
---

# Text-statistics template fixture

A small real CPU operation: count whitespace-separated, case-folded words. HTTP
`POST /analyze` takes `{"text":"A a B"}`; the queue adapter takes
`{"input":{"text":"A a B"}}`. Expected output is
`{"words":3,"counts":{"a":2,"b":1}}`.

File map: `workload.py` is the operation; `app.py` is the HTTP adapter; `handler.py`
is the queue adapter; `requirements.txt` pins the worker SDK; `test_app.py` checks
useful results and failure recovery; `test_input.json` is a local SDK request fixture.
`Dockerfile.http` serves Pods or load balancing;
`Dockerfile.queue` starts the queue worker. `.dockerignore` excludes local/secret data.
The separate `pytorch/` directory is an optional GPU/layer probe with its own context.

Run these commands **from this directory**, in Bash or PowerShell (single-line syntax):

```text
python -B -m unittest -v test_app
docker build --platform linux/amd64 -f Dockerfile.http --target test -t template-http:test .
docker run --rm template-http:test
docker build --platform linux/amd64 -f Dockerfile.http -t template-http:v1 .
docker run --rm -p 127.0.0.1:8080:8080 template-http:v1
```

In another shell, POST JSON to `http://127.0.0.1:8080/analyze`. Bash:

```bash
curl -fsS http://127.0.0.1:8080/analyze -H 'Content-Type: application/json' -d '{"text":"A a B"}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/analyze -ContentType application/json -Body '{"text":"A a B"}'
```

Queue build and selected SDK's local-input mode:

```text
docker build --platform linux/amd64 -f Dockerfile.queue --target test -t template-queue:test .
docker run --rm template-queue:test
docker build --platform linux/amd64 -f Dockerfile.queue -t template-queue:v1 .
docker run --rm template-queue:v1
```

For local execution, the pinned SDK 1.10.1 reads `test_input.json` from its working
directory when no `--test_input` argument is provided. This sample is included in the
queue image, so the command above exercises its actual default command without JSON
shell quoting. Edit that file and rebuild to try another input; on Runpod the SDK runs
as a platform worker. No file-input flag is needed. Do not substitute Bash continuations
in PowerShell. On Linux the Python executable
may be `python3`; the Docker commands run the image's selected interpreter.

Deployment settings: HTTP port `8080`/`PORT=8080`, default image command, no persistent
storage, no GPU or CUDA, no application secrets. The HTTP app has **no authentication**;
the local command binds only loopback. Configure appropriate access for public Pods;
verify current endpoint authentication for Serverless. Queue mode needs no exposed HTTP
port. For load balancing, verify current health-port settings and route `/ping` to the
same listener. Choose CPU sizing/disk from measurements; no live minimum is asserted.

Image release: resolve/record the Ubuntu base digest, source revision and resulting
image digest. `runpod==1.10.1` is this fixture's explicit SDK choice, not a latest-version
claim; revalidate if updated. Transitive package resolution is not a full lock. Use a
registry you control, attach private pull credentials when needed, and supply the
actual supported Runpod settings/commands for the selected target. Do not push or
provision just to run local tests.

The app stores no data, so restart needs no migration. Deploy updates as identified
images/releases and retain the prior image/configuration for rollback. `/ping` is
immediate only because this app has no initialization dependency. A model app must
delay readiness until it can execute work.

Verification: local/container checks can be run above; **Runpod end-to-end behavior,
platform sizing and GPU behavior are unverified here**. If Docker is unavailable,
run the dependency-free Python tests and continue with an eligible hosted build route
or a precise setup handoff. Preserve logs and remove only test-owned artifacts.

On 2026-10-06 both image test stages and actual HTTP/SDK local entrypoints passed on
Docker 29.7.2 / Linux x86_64. The HTTP app passed invalid-input recovery and restart;
the queue SDK returned expected counts and failed invalid input clearly. No live
Runpod, GPU, or managed-GitHub result is claimed.
