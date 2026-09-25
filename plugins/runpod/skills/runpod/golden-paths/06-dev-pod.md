# Golden path 06 — interactive dev pod (SSH / VS Code + persistent /workspace)

**Goal:** from "give me a Runpod dev box I can SSH into / open in VS Code", an agent
provisions a pod on a PyTorch template with a **network volume at `/workspace`**, returns a
ready-to-use **SSH-over-TCP** connection (and the `~/.ssh/config` block VS Code / Cursor
Remote-SSH reads), and proves an interactive session works with storage that **survives a
stop/restart**.

Unlike a *service* pod (01/02) there's no HTTP proxy URL to poll — **success is a live
interactive shell whose `/workspace` survives a stop/restart, plus a VS Code Remote-SSH
connection string that actually resolves and downloads the server.**
**Status:** COVERED — live-verified 2026-07-10. Created an RTX 4090 pod on `runpod-torch-v280`
in EU-RO-1 with a 10 GB network volume at `/workspace`; SSH-exec returned real GPU/torch output;
a marker file survived a real `pod stop`→`pod start` (ephemeral `/root` was wiped, container
hostname changed); and the VS Code Remote-SSH transport connected via a `~/.ssh/config` alias
and the pod fetched the **exact** `vscode-server-linux-x64.tar.gz` for the local editor's commit
(HTTP 200). The one thing not machine-checkable is the final GUI click (see [VS Code](#verify-it-works--vs-code--cursor-remote-ssh-what-was-verified-headlessly)).
**Lane(s):** runpodctl (pod + volume) + SSH-exec. Builds on the pod-create + readiness-poll
pattern from golden path [07](07-network-volume-handoff.md).

## When to use this
The user wants a **box they log into and work on interactively** — an SSH shell, a VS Code /
Cursor Remote-SSH window, a scratch GPU for experiments — not a served endpoint. Reach for it
whenever the task is "give me a dev machine" rather than "deploy this model". If instead you
need to *serve* something over a URL, that's golden path [01](01-ollama-pod.md)/[02](02-comfyui-pod/README.md);
if you're running a *batch* training job, that's [04](04-finetune-pod.md)/[08](08-finetune-to-serverless.md).

## Prerequisites
- `RUNPOD_API_KEY` resolvable (`export RUNPOD_API_KEY=...`).
- `runpodctl` installed.
- **An SSH key registered on the account BEFORE the pod boots.** Runpod injects registered
  public keys into the pod's `~/.ssh/authorized_keys` **at startup** — a key added after the
  pod is running won't be picked up without a restart (see
  [`../../runpod-usage/reference/getting-started.md`](../../runpod-usage/reference/getting-started.md)).
  Confirm with `runpodctl ssh list-keys`; if empty, register one:
  ```bash
  ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ''          # if you don't have one
  runpodctl ssh add-key --key-file ~/.ssh/id_ed25519.pub
  runpodctl ssh list-keys                                    # confirm it's on the account
  ```
- For VS Code Remote-SSH on your machine: VS Code/Cursor with the **Remote-SSH** extension.

## Walkthrough (verified commands)

### 1. Persistent workspace — a network volume in your target DC
`/workspace` on a dev pod is backed by a network volume so your code/data survives a reset.
The volume is **pinned to one DC**; the pod must run in that same DC.
```bash
runpodctl network-volume create --name devbox-demo --size 10 --data-center-id EU-RO-1
# → id, e.g. gjj71yzmnd, in EU-RO-1
```

### 2. Create the pod — PyTorch template, volume at `/workspace`, TCP 22 exposed
Follow golden path 07's create flags. The two additions for a dev box: `--ports "22/tcp"` (so
SSH is reachable over a **public IP + external TCP port**, which VS Code Remote-SSH requires)
and the volume mounted at `/workspace`.
```bash
runpodctl pod create --name devbox-demo \
  --template-id runpod-torch-v280 --gpu-id "NVIDIA GeForce RTX 4090" \
  --data-center-ids EU-RO-1 \
  --network-volume-id <vol-id> --volume-mount-path /workspace \
  --ports "22/tcp" \
  --ssh
```
> **Stop vs remove.** For a **throwaway test**, `runpodctl pod remove` the pod when done.
> For a **real dev box the user returns to**, `runpodctl pod stop` it between sessions:
> `stop` preserves the pod and its `/workspace`, `remove` **deletes** the pod (the network
> volume survives either way, since it's a separate resource). Don't use `--stop-after` /
> `--terminate-after`: they were never enforced, and runpodctl v2.12.0 removed them.
> Verified image on `runpod-torch-v280`:
> `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, RTX 4090 at **$0.69/hr**.

### 3. Poll until the runtime is up, then read the SSH-over-TCP connection
`ssh info` returns `"error": "pod not ready"` until the runtime is live — poll it (07's
pattern). If it stays "pod not ready" / `runtime: false` past ~5–6 min, it's a **bad machine
draw** — `pod remove` and recreate rather than waiting forever ([07](07-network-volume-handoff.md), `gotchas.md`).
```bash
runpodctl ssh info <pod-id>
# → {"ip":"213.173.108.151","port":17740,
#    "ssh_command":"ssh -i /Users/you/.runpod/ssh/RunPod-Key-Go root@213.173.108.151 -p 17740", ...}
```
`ssh info` hands you the **public-IP + external-port TCP form directly** — this is the form
VS Code Remote-SSH needs (not the proxied `…@ssh.runpod.io` basic-SSH form). It also names the
key path to use (`ssh_key.path`); agents should use that exact path.

### 4. Verify it's actually interactive (not just "Running")
Connect non-interactively (07's flags). Use the IP/port/key from `ssh info`:
```bash
ssh -i /Users/you/.runpod/ssh/RunPod-Key-Go \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -p 17740 root@213.173.108.151 \
    'hostname; nvidia-smi -L; python3 --version; \
     python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"; \
     df -h /workspace | tail -1'
```
Real output (2026-07-10):
```
881177e25f9d
GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-44150745-556c-e3f1-55bc-caae92449acf)
Python 3.12.3
2.8.0+cu128 True
mfs#euro-3.runpod.net:9421  839T  315T  524T  38% /workspace     # volume-backed, network FS
```

### 5. Prove `/workspace` persistence across a stop/restart
Write a marker to `/workspace` and something to ephemeral `/root`, then `stop`→`start`:
```bash
ssh ... -p 17740 root@213.173.108.151 \
  'echo "devbox persistence $(date -u +%FT%TZ)" > /workspace/marker.txt; echo ephemeral > /root/ephemeral.txt'

runpodctl pod stop  <pod-id>          # wait for desiredStatus EXITED
runpodctl pod start <pod-id>          # then re-poll ssh info (PORT CHANGES — see gotcha)

ssh ... -p <NEW-port> root@213.173.108.151 \
  'cat /workspace/marker.txt; test -f /root/ephemeral.txt && echo EXISTS || echo GONE-wiped; hostname'
```
Real result (2026-07-10) — the marker survived, `/root` was wiped, the container is new:
```
devbox persistence 2026-07-10T20:30:06Z     # /workspace marker — SURVIVED
GONE-wiped                                    # /root/ephemeral.txt — wiped on stop
b65f1a073985                                  # hostname changed (was 881177e25f9d) → real restart
```

### 6. Hand off — the VS Code / Cursor Remote-SSH `~/.ssh/config` block
Add this to your local `~/.ssh/config`, then in VS Code/Cursor: **Command Palette →
Remote-SSH: Connect to Host → `runpod-devbox` → Open Folder → `/workspace`**.
```
Host runpod-devbox
    HostName 213.173.108.151          # from `ssh info` .ip
    User root
    Port 17740                        # from `ssh info` .port — RE-READ after every stop/start
    IdentityFile ~/.runpod/ssh/RunPod-Key-Go   # from `ssh info` .ssh_key.path
```

## Verify it works — VS Code / Cursor Remote-SSH (what was verified headlessly)
<a id="4-vs-code--cursor-remote-ssh-what-was-verified-headlessly"></a>
VS Code Remote-SSH is just: (a) run the system `ssh` against a `~/.ssh/config` Host alias, then
(b) download & launch the VS Code **Server** on the remote for your editor's commit. Both
mechanical steps were verified without a GUI:

1. **The Host-alias transport connects** — exactly the `ssh` invocation the extension makes:
   ```bash
   ssh -F /tmp/devbox.cfg runpod-devbox 'echo OK on $(hostname); uname -m'
   # → VS Code Remote-SSH transport OK on host b65f1a073985 / x86_64
   ```
2. **The remote arch matches the server build** — pod is `x86_64` → `server-linux-x64`.
3. **The pod can fetch the exact server tarball for the local editor's commit** (what
   Remote-SSH downloads on first connect):
   ```bash
   COMMIT=$(code --version | sed -n '2p')     # e.g. 4fe60c8b1cdac1c4c174f2fb180d0d758272d713
   ssh -F /tmp/devbox.cfg runpod-devbox \
     "curl -sIL -o /dev/null -w '%{http_code} %{url_effective}\n' \
      https://update.code.visualstudio.com/commit:${COMMIT}/server-linux-x64/stable"
   # → 200  https://vscode.download.prss.microsoft.com/.../vscode-server-linux-x64.tar.gz
   ```

**Verified:** the connection string an agent hands the user is real — the alias resolves, SSH
authenticates with the account key, the remote is the right arch, and the VS Code Server binary
is reachable and downloadable from the pod. **Requires a human (GUI):** the actual *Remote-SSH:
Connect to Host* click in the desktop editor — that Electron action can't be driven headlessly.
Everything up to that click is proven; the click itself just runs steps 1–3 above.

## Gotchas we hit
- **The external TCP port is reassigned on every stop/restart — and `ssh info` can hand you a
  STALE port right after `start`.** Live: the pod came up on port **17740**; after `pod
  stop`→`start` the *first* `ssh info` still reported 17740 (connections were refused), and a
  moment later it returned the real new port **12890**. Always re-read `ssh info` after a
  restart, and if you get connection-refused, poll `ssh info` again for a fresh port before
  updating your `~/.ssh/config` `Port`. (The public IP happened to stay the same here; on
  Community Cloud it can change too.)
- **"Running"/"READY" ≠ sshd is up.** After `start`, `ssh info` reported READY while sshd was
  still initializing — SSH was connection-refused for ~90s. Retry the real `ssh` (or poll a
  fresh `ssh info`) rather than trusting the first READY.
- **Only `/workspace` persists.** Proven live: the network volume at `/workspace` survived
  stop/start; everything else (`/root`, installed apt packages, `/tmp`) is **wiped on stop**
  (the hostname even changed). Keep code, envs, and data under `/workspace`.
- **Key must exist before boot.** Registered account keys are injected at startup; add a key
  after the pod is running and it won't work until a restart. Register first (Prerequisites).
- **Use the key path from `ssh info`.** `ssh info` reports `ssh_key.path` + whether it's
  `in_account`; the live run's working key was runpodctl's own `~/.runpod/ssh/RunPod-Key-Go`.
  Any account-registered key works, but taking the one `ssh info` names avoids guesswork.
- **Volume ↔ GPU same DC.** The volume is DC-locked (EU-RO-1 here); the pod must run in that DC.

## Cost & cleanup
```bash
runpodctl pod remove <pod-id>                 # deletes the pod (do this for bad-draw pods too)
runpodctl network-volume delete <vol-id>      # pod must be removed first
runpodctl pod list && runpodctl network-volume list   # confirm clean
```
Live cost: RTX 4090 pod at **$0.69/hr** + 10 GB volume (negligible). For a real dev box you
keep, `pod stop` between sessions (stopped pods still bill for disk + the volume);
`remove` + volume `delete` when done for good. A CPU pod is cheaper if you
don't need the GPU — drop `--gpu-id` and use `--compute-type cpu` (not exercised in this run).

## Skill gaps folded back
- **`getting-started.md`** already documents key-before-boot + the non-interactive
  `ssh -o StrictHostKeyChecking=no` pattern — confirmed correct in practice.
- **`gotchas.md`** "Pod shows Running but ports aren't reachable yet" was extended with the
  concrete dev-pod finding: after a stop/start, `ssh info` can return a **stale external TCP
  port** and report READY before sshd is up — re-read `ssh info` and retry.
- **Confirmed for this doc:** `runpodctl ssh info` surfaces the public-IP + external-TCP-port
  form directly (no Console needed), including the key path — enough for an agent to build the
  VS Code Remote-SSH `~/.ssh/config` unaided.
