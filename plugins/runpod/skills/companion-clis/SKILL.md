---
name: companion-clis
description: Companion CLIs for Runpod workflows — HuggingFace, GitHub, Docker, and AWS.
allowed-tools: Bash(hf:*), Bash(gh:*), Bash(docker:*), Bash(aws:*), Bash(ssh-keygen:*), Bash(ssh-add:*), Bash(ssh-agent:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.2.0" # x-release-please-version
license: Apache-2.0
---

# Companion CLIs

Four CLIs commonly needed alongside Runpod. Each has its own **credentials + command reference** in [`reference/`](reference/) — plus a one-time `<cli>-setup.md` for install (only opened if the CLI isn't installed). Load only the one the task needs, not all four.

| CLI | Use it to | Full reference |
|-----|-----------|----------------|
| `hf` (HuggingFace) | Download models from the Hub to cache/bake into images | [reference/huggingface.md](reference/huggingface.md) |
| `gh` (GitHub) | Manage worker repos + cut releases (Hub indexes releases) | [reference/github.md](reference/github.md) |
| `docker` | Build/validate/push images to Docker Hub for Runpod to pull | [reference/docker.md](reference/docker.md) |
| `aws` (S3) | Read/write network-volume storage over Runpod's S3 API | [reference/aws.md](reference/aws.md) |

Each requires credentials before use. Read the per-tool reference for auth steps and commands; install is a separate one-time `<cli>-setup.md`.

## Windows: Install WSL2 First

If you are on Windows, install WSL2 before proceeding — it gives you the native Linux environment all these CLIs target. In PowerShell as Administrator, then restart:

```powershell
wsl --install
```

Afterward open the Ubuntu app to finish setup, then follow the **Linux** instructions in each reference.

## HuggingFace CLI

Download models locally so they're cached for a Docker build/run. Auth and `hf download` recipes: **[reference/huggingface.md](reference/huggingface.md)** (install: [reference/huggingface-setup.md](reference/huggingface-setup.md)).

- Use the standalone `hf` CLI, **not** `pip install huggingface_hub` (that's the older `huggingface-cli` with different syntax).
- Auth via `hf auth login`, or `export HF_TOKEN=hf_...` (env var wins over saved token).

## GitHub CLI

Manage worker repositories and cut releases. Auth and commands: **[reference/github.md](reference/github.md)** (install + SSH-key setup: [reference/github-setup.md](reference/github-setup.md)).

- **The Hub indexes releases, not commits** — every Hub listing update needs a new `gh release create`.
- One SSH key (`ssh-keygen -t ed25519`) registers with both GitHub (`gh ssh-key add`) and HuggingFace (paste in browser).

## Docker

Build, validate, and push images to Docker Hub. Credentials and commands: **[reference/docker.md](reference/docker.md)** (install: [reference/docker-setup.md](reference/docker-setup.md)).

- **Always build `--platform=linux/amd64`** — Runpod runs on x86 Linux.
- **Always use explicit semantic tags; never `latest`** — `latest` doesn't track the newest push, so workers can silently pull the wrong image.
- Docker Hub auth uses a **personal access token**, not your password. For private images, register the credential once in Console → Container Registry Settings.

## AWS CLI

Access network-volume storage over Runpod's S3-compatible API (bucket name = network volume ID). Credentials, region rules, and commands: **[reference/aws.md](reference/aws.md)** (install: [reference/aws-setup.md](reference/aws-setup.md)).

- Runpod's S3 API, **not AWS**: access key = Runpod **user id** (`user_...`), secret = S3 API key (`rps_...`).
- **S3 API keys are Console-only.** No `runpodctl`/REST/GraphQL creates them — if they're not already in `~/.aws/credentials`/env and S3 access is needed, **stop and ask the user** to generate them (Settings > S3 API Keys).
- Every command needs `--region DATACENTER --endpoint-url https://s3api-DATACENTER.runpod.io/` (datacenter = the volume's DC, not an AWS region).
- For large/many-file transfers with reliable resume, see [reference/aws.md → optional resumable volume transfers](reference/aws.md#optional-resumable-volume-transfers-community-tool).
