---
lanes: [docker, runpodctl, ssh]
mcp: partial
concepts: [container-image, pod, pod-ssh-access, ssh-key, template, cpu-pod]
---

# Golden path 22 — minimal **pod** image (and don't kill SSH)

✅ **Live-verified** (built → pushed → CPU pod launched → **SSH'd in** → HTTP proxy `200` → torn down).

A minimal **SSH-enabled Pod** image: if the template promises SSH, its image must
start that service. Application-only Pods can use another access contract. Compatible
`runpod/pytorch` bases provide startup hooks; this historical path
builds from a plain base to show the **from-scratch** SSH pattern explicitly (and to prove it
works). Pods have **no handler** — the container just runs a long-lived process (your `CMD`).

See [building-images.md → Match startup to the target](../../../runpod-usage/reference/building-images.md)
for the current concept; this is historical runnable evidence for an SSH-enabled Pod.

## Prerequisites

See the shared [Before you run any path](../README.md#before-you-run-any-path-shared-prerequisites)
block first. For this path specifically:

- **Runpod auth** — `export RUNPOD_API_KEY=<key>` (from the
  [console](https://runpod.io/console/user/settings); see
  [getting-started](../../../runpod-usage/reference/getting-started.md)).
- **Docker** running **and `docker login`** to a registry you can push to — substitute your
  namespace for `<namespace>`. See [companion-clis docker](../../../companion-clis/reference/docker.md).
- **An SSH key** to register on your account (below). No key yet?
  `ssh-keygen -t ed25519` first (see [getting-started](../../../runpod-usage/reference/getting-started.md)).

## The image

[`template/`](template/):

- **`Dockerfile`** — `FROM python:3.11-slim`, installs `openssh-server` (a plain base has none),
  copies `start.sh`, `CMD ["/start.sh"]`.
- **`start.sh`** — reproduces what `runpod/pytorch`'s `/start.sh` does, then runs the workload:
  1. `$PUBLIC_KEY` → `~/.ssh/authorized_keys` (Runpod injects **all your account SSH keys** here)
  2. `ssh-keygen -A` (host keys) → `service ssh start`
  3. `exec python3 -m http.server $PORT` — a stand-in long-running service

> **On a compatible `runpod/pytorch` base that already provides SSH, skip steps 1–2** — add your layers and
> preserve that exact base version's supported startup hooks (see building-images.md).
> Verify hook ordering and process supervision rather than relying on a background
> script and fixed sleep. This example specifically implements an SSH-enabled contract.

## Build + push (x86_64 Linux — emulated on Apple Silicon)

```bash
cd template
docker buildx build --platform linux/amd64 -t <namespace>/rp-gp22-pod:v1 --push .
```

## Make sure your SSH key is on the account (so it lands in `PUBLIC_KEY`)

```bash
# no key yet? generate one first:  ssh-keygen -t ed25519
runpodctl ssh add-key --key-file ~/.ssh/id_ed25519.pub   # once (use your key's path)
runpodctl ssh list-keys                                   # confirm it's there
```

## Launch (CPU pod — cheapest; this workload needs no GPU)

```bash
runpodctl pod create --compute-type cpu \
  --image <namespace>/rp-gp22-pod:v1 --name gp22-pod \
  --ports "22/tcp,8000/http" --container-disk-in-gb 10 --env '{"PORT":"8000"}'
# → pod id, e.g. m9e1ow8y6pwm2x ; costPerHr ~0.06
```

`--ports "22/tcp,8000/http"` exposes SSH **and** the HTTP service (the latter gets a public
`https://<pod-id>-8000.proxy.runpod.net` proxy URL).

## Verify SSH works (the whole point)

```bash
runpodctl ssh info <pod-id>        # prints ip, port, and a ready-to-paste `ssh_command`
# paste the `ssh_command` field verbatim — it includes the right `-i <key>` path
# (the exact key filename varies per account; don't hardcode it), e.g.:
#   ssh -i <key-from-ssh-info> root@<ip> -p <port>
```

**Observed this run** (`m9e1ow8y6pwm2x`, US-CA-2, CPU pod):

```text
$ ssh … 'whoami; wc -l < ~/.ssh/authorized_keys; pgrep -x sshd'
root
21                      # PUBLIC_KEY (all account keys) landed in authorized_keys
20                      # sshd running

$ ps aux | grep -E 'http.server|sshd'
root  1  … python3 -u -m http.server 8000    # workload is PID 1 (the exec'd CMD)
root 20  … sshd: /usr/sbin/sshd [listener]    # SSH came up alongside it

http_local: 200                                # service answering inside the pod
proxy_http: 200   # https://m9e1ow8y6pwm2x-8000.proxy.runpod.net  → public proxy works
```

Both the workload **and** sshd are running — because `start.sh` started SSH before `exec`ing
the workload. Drop the SSH block (or override `CMD` without it) and you'd get the HTTP service
but **no way to SSH in**.

## Tear down

```bash
runpodctl pod delete <pod-id>
runpodctl pod list        # confirm it's gone (pods bill while running — delete when done)
```

## What this proves

- The **pod image contract**: no handler — the container runs your long-lived `CMD`.
- **Promised SSH access must be set up by the image.** From a Runpod base it's inherited; from a plain base you
  reproduce it (`PUBLIC_KEY` → authorized_keys, `ssh-keygen -A`, start sshd) **before** your
  workload, or you're locked out.
- `--platform=linux/amd64` build from Apple Silicon; CPU pod for a CPU workload; port exposure
  → public proxy URL.
