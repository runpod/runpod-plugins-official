# Pods vs Serverless

Two ways to run compute on Runpod. Pick based on the shape of the work.

## Pods — interactive / long-lived

A Pod is a GPU or CPU container you rent by the minute and keep running. You get
full control: SSH, a web terminal, JupyterLab, VS Code/Cursor, exposed ports. It
stays up until you stop or delete it, and you pay for every minute it exists
(running or stopped-with-disk).

Use a Pod when:

- You are developing, experimenting, or debugging interactively.
- Work is long-running or stateful (training, fine-tuning, rendering, a notebook).
- You want a persistent environment you shell into and iterate in.
- You need a service up continuously with a stable address.

Not a good fit when traffic is bursty or idle much of the day — you pay for idle time.

Two clouds — **default to Secure Cloud**:

- **Secure Cloud** — T3/T4 data centers run by data-center-grade host providers, high
  redundancy. Production and sensitive data. Use this unless the user explicitly asks
  for Community.
- **Community Cloud** — approved vendors, cheaper. Secure Cloud's data-center-grade
  providers tend toward more stable behavior, which is why Secure is the default.
  (Runpod is no longer onboarding new Community Cloud hosts; existing capacity remains.)

Limits: no Docker Compose (Runpod runs Docker for you), no UDP (TCP/HTTP only), no Windows.

## Serverless — request/response + autoscale

Serverless runs your container only while it is processing requests. You deploy a
worker image behind an **endpoint** (a URL). Workers spin up on demand, process
jobs, and spin down when idle. You pay for compute time used, with no idle cost
when nothing is running.

Use Serverless when:

- Work is request-shaped: inference, image generation, transcription, batch jobs.
- Traffic is bursty or unpredictable and you want it to scale to zero.
- You want a managed URL, not a machine to babysit.

## Serverless building blocks

- **Endpoint** — the access point (URL) clients send requests to. Holds the scaling
  and GPU config.
- **Worker** — a container instance running your image + code. Runpod starts and
  stops workers automatically based on load.
- **Handler function** (queue-based) — `def handler(event)` reads `event["input"]`,
  processes it, returns a result. Started with `runpod.serverless.start({"handler": handler})`.
- **Job** — one unit of work: the input payload, queued until a worker is free.

## Cold starts and FlashBoot

A **cold start** is the gap between a request arriving at an endpoint with no ready
worker and that worker being warmed up — container start + model load into VRAM +
runtime init. Bigger models = longer cold starts.

Reduce cold starts by:

- **FlashBoot** (on by default) — retains worker state after spin-down so a worker
  "revives" faster than a fresh boot. Most effective with steady traffic where
  workers cycle between active and idle.
- **Cached models** — schedule workers onto machines with your model files
  pre-loaded, cutting model-load time.
- **Active workers** ≥ 1 — keep workers always warm (see below).

## Active vs flex workers, scale-to-zero

- **Active (min) workers** — always-on, kept warm at all times. Setting this to 1+
  eliminates cold starts for those slots but bills continuously, even when idle.
  Default is **0**.
- **Flex workers** — the elastic pool between active count and **max workers**.
  Spun up under load, spun down when idle. **Scale-to-zero** = active workers 0, so
  the endpoint drops to zero running workers (and zero cost) when idle, at the price
  of a cold start on the next request.
- **Idle timeout** — how long a flex worker stays warm after finishing before it
  shuts down (default 5s). Longer = fewer cold starts, more cost.
- **Max workers** — concurrency cap and cost safety limit (default 3). Set ~20%
  above expected peak concurrency to absorb spikes.

> **These are the platform defaults** (Console / `runpodctl` / API). The **flash SDK**
> applies its *own* defaults for the same settings — `idle_timeout` **60s** (not 5s),
> `workers` **(0, 1)** i.e. max 1 (not 3), `execution_timeout` unlimited (not 600s). So a
> default value depends on which layer you configured through; don't assume the flash
> number holds for a platform-created endpoint or vice-versa. See
> [`../../flash/reference/api.md`](../../flash/reference/api.md).

Auto-scaling type decides *when* to add workers:

- **Queue delay** — add workers when requests wait longer than a threshold
  (default 4s). Good when small delays are acceptable.
- **Request count** — scale on pending + in-progress work
  (`ceil((inQueue + inProgress) / scalerValue)`). More aggressive; good for LLMs
  and frequent short requests.

## Queue-based vs load-balanced endpoints

Two endpoint types, chosen at creation:

**Queue-based** (traditional)

- Requests go into a queue and are processed in order; execution is guaranteed with
  automatic retries.
- Uses a handler function; fixed operations: `/run`, `/runsync`, `/status`, `/stream`,
  `/cancel`, `/health`, etc.
- Best for async tasks, batch, long-running jobs. Higher latency (queue + worker).

**Load-balanced**

- Requests route directly to a worker's HTTP server — no queue, no backlog buffering
  (overloaded workers drop requests).
- You run any HTTP server (FastAPI, Flask) and define your own URL paths; workers
  expose a `/ping` health check.
- Lower latency (single hop). Best for real-time inference, streaming, custom REST APIs.
- No built-in retry.

Analogy from the docs: queue-based is like TCP (guaranteed delivery), load-balanced
is like UDP (fast, no guarantees).

## Templates

A **template** is a saved, pre-configured setup: a Docker image plus its default
config (exposed ports, environment variables, container/volume disk, start command).
Runpod ships official templates (e.g. PyTorch) so you can launch a working
environment without wiring dependencies yourself, and you can save your own custom
templates for repeatable deployments of both Pods and endpoints.

## Where to act

This file is a mental model. To actually create or manage resources use
**runpodctl** / **runpod-mcp** (infra), **flash** (deploy your own code), or the
Runpod console.
