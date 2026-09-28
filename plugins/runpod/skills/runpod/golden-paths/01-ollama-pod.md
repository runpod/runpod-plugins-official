# Golden path 01 — Ollama server on a pod + access URL

**Goal:** from a plain request ("stand up an Ollama server on Runpod and give me
the URL"), an agent provisions a GPU pod, installs and starts Ollama, pulls a
model, and returns a working HTTPS API URL — with model data on persistent
storage.

**Status:** COVERED — live-verified 2026-07-07
**Lane(s):** runpodctl (pod) + SSH

Grounded in the official tutorial `docs/tutorials/pods/run-ollama.mdx` and the
reusable pod loop in [`../../runpod-usage/reference/pod-workflows.md`](../../runpod-usage/reference/pod-workflows.md).

## When to use this (and why a pod, not serverless)

Ollama is a **long-lived HTTP server you keep open and talk to interactively**
(`/api/generate`, `/api/chat`, `/api/tags`). That is the classic pod shape: a
service reached at a proxy URL, not a request/response job that should scale to
zero. See the workload-shape decision in
[`../../runpod-usage/reference/development-loop.md`](../../runpod-usage/reference/development-loop.md).

Use a **pod** here because:

- You want a persistent server behind one stable URL, not per-request cold starts.
- You iterate against it (pull more models, chat repeatedly) over its lifetime.
- Model weights live on a **network volume** so pulls happen once and survive
  restarts.

Reach for **serverless** instead only if you truly want a scale-to-zero
request/response inference API (that is golden path 03, Whisper) — different lane,
`endpoint-workflows.md`.

This path uses the **runpodctl** lane: it exposes every flag this needs
(`--ports`, `--env`, `--network-volume-id`) and gives a
non-interactive SSH channel to run install commands. MCP's `create-pod` can also
set ports/env, but runpodctl is preferred when you need a template lookup + SSH
exec in one lane (see the router).

## Prerequisites

| Need | How |
| --- | --- |
| **Auth** (non-interactive) | `export RUNPOD_API_KEY=your_key` — runpodctl reads it. `runpodctl doctor` is the interactive human first-run (also sets up SSH keys). |
| **runpodctl** installed | `curl -sSL https://cli.runpod.net \| bash` (see [`../../runpodctl/SKILL.md`](../../runpodctl/SKILL.md)). |
| **An SSH key** registered | `runpodctl doctor` or `runpodctl ssh add-key`; needed so the agent can exec on the pod. |
| **A GPU + a co-located DC** | `runpodctl datacenter list` shows per-DC GPU availability — pick a DC that has your GPU *and* will hold the volume. |

Resolve auth **before any API call**. If a step needs a human (OAuth, quota
increase, payment) — stop and say exactly what is blocked; don't fake progress.

## Walkthrough

Each step lists the real command and why it matters. Do them in order; each
depends on the previous.

### 0. Auth

```bash
export RUNPOD_API_KEY=your_key     # non-interactive; runpodctl reads this
# (humans can run `runpodctl doctor` for interactive setup + SSH keys)
```

*Resolves auth once for the whole flow.*

### 1. Create a network volume for the models (default: persistent)

```bash
runpodctl datacenter list          # per-DC GPU availability → pick a DC
runpodctl network-volume create --name ollama-models --size 30 --data-center-id <dc>
#   → note the volume id (it lives in <dc>; the pod MUST go in the same <dc>)
```

*Model weights are large and slow to pull. Put them on a network volume so they
persist across stop/restart and aren't re-downloaded (see
[`../../runpod-usage/reference/storage.md`](../../runpod-usage/reference/storage.md),
"prefer a network volume by default"). The volume is **DC-locked** — the pod has
to be created in the same data center or scheduling fails.*

### 2. Create the pod — ports + env + volume set AT creation

```bash
runpodctl template search pytorch          # find the official PyTorch template id

runpodctl pod create \
  --name ollama \
  --template-id <runpod-pytorch-template-id> \
  --gpu-id "<cheap available gpu>" \
  --ports "11434/http,22/tcp" \
  --env '{"OLLAMA_HOST":"0.0.0.0","OLLAMA_MODELS":"/workspace/ollama"}' \
  --network-volume-id <volume-id> \
  --volume-mount-path /workspace
```

*Everything the service needs is baked in now. **Ports and env cannot be added to
a running pod without a reset**, so `11434/http` (Ollama's API port) and `22/tcp`
(SSH, the agent's control channel) are declared up front. `OLLAMA_MODELS` points
pulls at the volume mount. Live run used an **RTX 4090**.*

### 3. Wait for the pod, then get the SSH connection

```bash
runpodctl pod get <pod-id>                 # poll until it is running
runpodctl ssh info <pod-id>                # prints the ssh command + key (does NOT connect)
```

*`ssh info` returns connection details, not an interactive session — the agent
execs commands remotely via `ssh user@host 'command'`.*

### 4. Install and start Ollama over SSH, then pull a model

```bash
ssh <pod-ssh> 'set -e; DEBIAN_FRONTEND=noninteractive apt-get update && \
  DEBIAN_FRONTEND=noninteractive apt-get install -y lshw zstd curl && \
  curl -fsSL https://ollama.com/install.sh | sh && \
  (env OLLAMA_HOST=0.0.0.0 OLLAMA_MODELS=/workspace/ollama ollama serve \
     > /workspace/ollama.log 2>&1 &) && \
  sleep 3 && ollama pull llama3.2:1b'      # tiny model for a fast readiness check
```

*What each part does:*

- *`apt-get install -y lshw zstd curl` — Ollama's installer and GPU detection
  need these; `-y` + `DEBIAN_FRONTEND=noninteractive` keep apt from prompting (an
  agent can't answer a TTY prompt). System deps go through **apt**; any Python
  tooling would use **uv** — see
  [`../../runpod-usage/reference/on-pod-setup.md`](../../runpod-usage/reference/on-pod-setup.md).*
- *`curl -fsSL https://ollama.com/install.sh | sh` — the vendor's supported
  install path.*
- *`env OLLAMA_HOST=0.0.0.0 OLLAMA_MODELS=/workspace/ollama ollama serve …` — the
  headline fix. The `--env` values from step 2 land in the pod's **PID 1**, **not
  in the SSH login shell**, so `OLLAMA_HOST` is *empty* here and Ollama would bind
  to `127.0.0.1` → the proxy 502s. **Pass the env explicitly on the serve
  command.** Log to the volume so you can diagnose later.*
- *`ollama pull llama3.2:1b` — a deliberately tiny model so readiness verifies
  fast (a bigger model like `llama3` works the same way, just slower to pull).
  Because `OLLAMA_MODELS=/workspace/ollama`, the weights land on the network
  volume and survive restarts.*

> **Detach note (guidance):** the verified run backgrounded `ollama serve` in a
> subshell (`( … & )`) inside a single SSH command that then continued to `pull`.
> For a server that must outlive the SSH session on its own,
> [`../../runpod-usage/reference/on-pod-setup.md`](../../runpod-usage/reference/on-pod-setup.md)
> recommends full detachment — `setsid bash -c "…" > /workspace/ollama.log 2>&1 <
> /dev/null &` — so a channel-close SIGHUP can't kill it. Either way, keep the env
> passed explicitly.

### 5. Return the URL

```bash
echo "Ollama: https://<pod-id>-11434.proxy.runpod.net  (POST /api/generate)"
```

*Proxy URL shape is `https://<pod-id>-<internal-port>.proxy.runpod.net` — HTTPS
only, port `11434` (see
[`../../runpod-usage/reference/networking.md`](../../runpod-usage/reference/networking.md)).*

## Verify it works

"Running" is not "ready." Confirm from **outside**, through the proxy — this
proves the proxy + `0.0.0.0` bind + exposed port all line up.

**1. Readiness poll** (`GET /api/tags` → `200`):

```bash
for i in $(seq 1 120); do curl -sf https://<pod-id>-11434.proxy.runpod.net/api/tags && break; sleep 5; done  # bounded ~10min
```

*Expect the proxy to return `502` for roughly the first 30–60s while the server
finishes coming up — that's normal warm-up, keep polling (with a timeout). When it
returns `200`, the JSON lists the pulled model (`llama3.2:1b`).*

**2. Hello-world generation** (`POST /api/generate`):

```bash
curl -s https://<pod-id>-11434.proxy.runpod.net/api/generate \
  -d '{"model":"llama3.2:1b","prompt":"Say hello in one sentence.","stream":false}'
```

*Live result: `/api/generate` returned a JSON completion containing generated
text — the server is serving end to end. Prefer `stream` or short prompts to
verify: the proxy runs through Cloudflare with a **100s cap**, so a single very
long generation can time out with a `524`.*

Only report success once a real request returns the right result.

## Gotchas we hit (live)

| Symptom | Cause | Fix |
| --- | --- | --- |
| **Proxy 502s even though the server "started"** (the headline) | `--env` values land in **PID 1, not the SSH shell**, so `OLLAMA_HOST` is empty over SSH and Ollama binds to `127.0.0.1` | **Pass env explicitly** on the launch: `env OLLAMA_HOST=0.0.0.0 … ollama serve`. Verified — this is the one step the naive version gets wrong. |
| Can't expose port 11434 after the pod is up | **Ports are set at creation**; adding an HTTP port needs a reset | Declare `11434/http` in `--ports` up front. |
| Proxy 502 with no obvious error | Ollama defaults to `127.0.0.1` | **Bind `0.0.0.0`** via `OLLAMA_HOST=0.0.0.0`. |
| Long single generation dies at ~100s (`524`) | Proxy is **HTTPS + Cloudflare, 100s cap** | Fine for normal API use; for long work stream or keep prompts short. |
| Models vanish after stop | Default model dir is container disk (wiped on stop) | Set `OLLAMA_MODELS=/workspace/ollama` onto the **network volume**. |
| Pod won't schedule after attaching the volume | Network volume is **DC-locked** | Create the pod in the **same DC** as the volume (`datacenter list` to co-locate). |
| Pod still billing past a `--terminate-after` / `--stop-after` deadline | runpodctl before v2.12.0 accepts these flags, but the backend never enforced them | `runpodctl update` (v2.12.0 removed them), and `runpodctl pod remove <pod-id>` when done. |
| Endpoint is wide open | The proxy URL is **public and Ollama has no built-in auth** | Warn the user; don't expose sensitive models unprotected. Add your own auth if needed. |

## Cost & cleanup

- **Cost guard:** the pod bills until you remove it. A stopped pod still bills
  for disk and the volume.
- **Live cost reference:** the verified run used an **RTX 4090** GPU pod.
- **Tear down when done:**
  ```bash
  runpodctl pod remove <pod-id>              # aliases: rm / delete
  runpodctl network-volume delete <volume-id>   # remove the pod first
  ```
  Delete the pod before the volume. Keep the volume only if you want the pulled
  models to persist for a future pod (its models survive termination).

## Reference: skill gaps found / folded back

Capability was mostly present (runpodctl has every flag); the **skill guidance**
to run this agentically was what was thin. Everything below is now closed by
generic, reusable capabilities — not Ollama-specific recipes.

| Requirement | Covered today |
| --- | --- |
| Auth | router + runpodctl `doctor` / `RUNPOD_API_KEY` |
| Pod: pytorch template + GPU | `pod create --template-id --gpu-id` |
| Expose port + env at creation | `--ports` / `--env`; documented in `pod-workflows.md` + runpodctl |
| SSH enabled | `--ssh` defaults on; `ssh info` |
| Agent runs commands on the pod | `pod-workflows.md` — non-interactive `ssh <host> '…'` exec loop |
| Install hygiene / **uv** | `on-pod-setup.md` (apt for system, uv for Python, pin, background + log) |
| Poll readiness + escalate | `pod-workflows.md` steps 6 + 8 |
| Storage: default network volume | `storage.md` "prefer a network volume by default" |
| Return access URL | `networking.md` proxy format |

**Skill changes folded back (done):**

1. [`../../runpod-usage/reference/pod-workflows.md`](../../runpod-usage/reference/pod-workflows.md)
   — the reusable pod development loop (provision → ssh-exec → set up → run → poll
   readiness → escalate → deliver).
2. [`../../runpod-usage/reference/on-pod-setup.md`](../../runpod-usage/reference/on-pod-setup.md)
   — install hygiene (uv/apt, pin, non-interactive, cache on volume, background +
   log, detach long-lived servers).
3. [`../../runpod-usage/reference/storage.md`](../../runpod-usage/reference/storage.md)
   — "prefer a network volume by default" policy.
4. **Router + runpodctl** — service pods declare port + env at creation; both
   point at the pod development loop.

**Live-verification note:** ran end to end on a real account — network volume →
pod (RTX 4090, PyTorch template, port 11434 + env at creation) → SSH install →
`ollama serve` (env passed explicitly) → `ollama pull llama3.2:1b` onto the volume
→ external poll of `/api/tags` (200) → `/api/generate` returned text. The run's
findings (env over SSH, `datacenter list`
for GPU/DC co-location, `uv`, non-interactive auth) are folded into the flow above
and the skill references.
