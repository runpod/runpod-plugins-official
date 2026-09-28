# The pod development loop

A repeatable loop for standing up, iterating on, and delivering **any** workload
on a Runpod pod — an Ollama server, ComfyUI, a Jupyter/dev box, a training run.
An agent has no Console and no web terminal, so it drives every step through the
CLI/API and a non-interactive SSH channel. Do the steps in order; each depends on
the previous.

## 1. Plan

Resolve the choices before creating anything (see `concepts.md`, `gpu-selection.md`,
`storage.md`):

- **Pod or serverless?** Long-lived / interactive / a persistent server → pod.
  Request/response that scales to zero → serverless (different lane).
- **GPU / VRAM** for the workload.
- **CUDA floor** — set `--min-cuda-version 12.8` on the create unless the image needs
  otherwise, so a modern image can't land on a host too old to run it
  ([`gpu-selection.md`](gpu-selection.md#step-3-pin-the-cuda-floor)).
- **Storage** — default to a **network volume** for anything worth keeping
  (models, datasets, checkpoints, envs). See `storage.md`.
- **Which ports** the service listens on. These must be declared **at creation**.

## 2. Provision

Create the pod with everything the service needs baked in — **ports and env
cannot be added to a running pod** without a reset, so set them now. Enable SSH
(the agent's control channel) and a **terminate** guard for cost safety.

> **Pre-flight — register your SSH key BEFORE creating the pod.** Runpod injects
> your account's registered SSH keys into the pod **at boot**, so a key added
> *after* the pod is running won't work until a restart. If you'll exec into the
> pod (you will — it's the control channel), confirm a key is registered first:
>
> ```bash
> runpodctl ssh list-keys                                   # already have one? then proceed
> # if not — human (interactive): registers a key + stores the API key
> runpodctl doctor
> # or agent/scripted: make a key, then register its PUBLIC half
> ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''
> runpodctl ssh add-key --key-file ~/.ssh/id_ed25519.pub
> ```

```bash
runpodctl pod create \
  --name <name> --template-id <official-template> --gpu-id "<gpu>" \
  --ports "<port>/http,22/tcp" \          # every port the service exposes (+22 for ssh)
  --env '{"KEY":"VALUE"}' \               # goes to PID 1 — NOT the ssh shell (see step 5)
  --network-volume-id <id> --volume-mount-path /workspace \
  --terminate-after <iso8601>             # cost guard: TERMINATES the pod
```

`--terminate-after` deletes the pod at that time; `--stop-after` only *stops* it
(you keep paying for disk/volume), so use `--terminate-after` as the real guard.
Find a data center that has both your GPU and (for co-location) your volume with
`runpodctl datacenter list` — its output includes per-DC GPU availability.

(MCP's `create-pod` also sets `ports`/`env`; use runpodctl when you need a
template, CPU pod, or multi-GPU list — see the router.)

## 3. Connect (the control channel)

```bash
runpodctl pod get <pod-id>     # poll until it is running
runpodctl ssh info <pod-id>    # prints the ssh command + key (does not connect)
```

Then run commands **non-interactively** — this is how an agent works a pod:

```bash
ssh <user>@<host> -p <port> -i <key> 'set -e; <commands>'
```

Keep it one command (or a heredoc script) per step so you can check the exit code
and output before moving on.

## 4. Set up

Install dependencies idempotently, using package managers and persisting heavy
artifacts to the volume. See `on-pod-setup.md` for the hygiene rules (apt for
system, `uv` for Python, pin versions, background long installs, cache on the
volume).

## 5. Run the service

Start it **bound to `0.0.0.0`** (not localhost, or the proxy can't reach it) on
the exposed port, in the background, logging to the volume.

> **Gotcha — creation env vars are NOT in your SSH shell.** The `--env` vars from
> step 2 are injected into the pod's **main process (PID 1)**, not into SSH login
> shells. A service you launch over SSH will see them **empty** — so a service
> that reads `OLLAMA_HOST`/`HOST`/`PORT` from the environment silently binds to
> localhost and the proxy 502s. **Pass the env explicitly** when you launch:

A long-lived server must be **fully detached**, or SSH sends SIGHUP on channel
close and kills it. Use `setsid` + `< /dev/null`, return immediately, and poll in
a *separate* call.

**Do not `sleep` in the same invocation** — it can drop the channel:

```bash
ssh <host> 'setsid bash -c "env HOST_VAR=0.0.0.0 OTHER=val <service-command>" \
  > /workspace/<svc>.log 2>&1 < /dev/null &'
```

(Two things at once: pass env explicitly because `--env` isn't in this shell, and
detach with `setsid`/`</dev/null` so it survives disconnect.)

## 6. Verify readiness — not "Running"

A pod showing "Running" does **not** mean the service answers. Poll a real health
check from **outside**, through the proxy URL, until it succeeds:

```bash
for i in $(seq 1 120); do curl -sf https://<pod-id>-<port>.proxy.runpod.net/<health-path> && break; sleep 5; done  # bounded ~10min; if it never answers, the service didn't come up — check logs
```

Expect the **proxy itself to return 502 for the first ~30–60s** while the service
finishes importing / CUDA-initializing — that's normal warm-up, not failure, so
keep polling (with a timeout). Only report success once it passes. If it never
does, read the service log on the volume to diagnose.

## 7. Iterate

Re-run setup/service commands over the same SSH channel. Logs and artifacts on the
volume survive restarts. Use a framework's hot-reload/dev mode when it has one
(e.g. `flash dev` in the flash lane).

## 8. Escalate on manual steps

If a step genuinely needs a human — OAuth sign-in, a quota/capacity increase, a
license/EULA click, a missing credential, a payment issue — **stop and tell the
user exactly what is blocked and what you need**. Do not silently retry or fake
progress.

## 9. Deliver & tear down

- Return the **access URL** (`https://<pod-id>-<port>.proxy.runpod.net`) and a
  sample request.
- Note any security caveat (proxy URLs are public; most dev servers have no auth).
- Tell the user how to stop/terminate; data on the network volume persists. The
  `--stop-after`/`--terminate-after` guard from step 2 is the backstop.

## The loop in one line

**plan → provision (ports+env+volume+ssh) → connect (ssh-exec) → set up → run
(bind 0.0.0.0) → poll readiness → iterate → escalate if blocked → deliver + tear
down.**
