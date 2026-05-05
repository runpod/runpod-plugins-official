---
name: runpodctl
description: Runpod CLI to manage your GPU workloads.
allowed-tools: Bash(runpodctl:*)
compatibility: Linux, macOS
metadata:
  author: runpod
  version: "2.3"
license: Apache-2.0
---

# Runpodctl

Manage GPU pods, serverless endpoints, templates, volumes, and models.

## Install

```bash
# Any platform (official installer)
curl -sSL https://cli.runpod.net | bash

# macOS (Homebrew)
brew install runpod/runpodctl/runpodctl

# macOS (manual — universal binary)
mkdir -p ~/.local/bin && curl -sL https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-darwin-all.tar.gz | tar xz -C ~/.local/bin

# Linux
mkdir -p ~/.local/bin && curl -sL https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-linux-amd64.tar.gz | tar xz -C ~/.local/bin

# Windows (PowerShell)
Invoke-WebRequest -Uri https://github.com/runpod/runpodctl/releases/latest/download/runpodctl-windows-amd64.zip -OutFile runpodctl.zip; Expand-Archive runpodctl.zip -DestinationPath $env:LOCALAPPDATA\runpodctl; [Environment]::SetEnvironmentVariable('Path', $env:Path + ";$env:LOCALAPPDATA\runpodctl", 'User')
```

Ensure `~/.local/bin` is on your `PATH` (add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` or `~/.zshrc`).

## Quick start

```bash
runpodctl doctor                    # First time setup (API key + SSH)
runpodctl --help                    # See current top-level commands
runpodctl pod create --help         # Inspect exact current flags before creating
runpodctl gpu list                  # See available GPUs
runpodctl hub search vllm           # Find a hub repo
runpodctl serverless create --hub-id <id> --name "my-vllm"  # Deploy from hub
runpodctl template search pytorch   # Find a template
runpodctl pod create --template-id runpod-torch-v21 --gpu-id "NVIDIA GeForce RTX 4090"  # Create from template
runpodctl pod list                  # List your pods
```

API key: https://runpod.io/console/user/settings

## Live Help Is Authoritative

Live `runpodctl --help` output is authoritative for exact flags, aliases, and command syntax. Use this skill for workflows, decision rules, safety notes, and common examples.

```bash
runpodctl --help
runpodctl <resource> --help
runpodctl <resource> <action> --help
```

Before using unfamiliar commands, inspect live help first. Do not rely on this skill as an exhaustive flag reference.

## Decision Rules

- Use Hub when the user wants a known deployable app or worker such as vLLM, ComfyUI, Whisper, or a Runpod-maintained repo.
- Use templates when the user already has a template ID, wants reusable image/config defaults, or needs lower-level control than Hub.
- Use direct pod creation with `--image` when the user has a specific Docker image and does not need a saved template.
- Use serverless for request/response inference APIs and scalable workers; use pods for interactive work, notebooks, training, debugging, or long-lived sessions.
- Use CPU pods for preprocessing, file movement, lightweight scripts, and non-CUDA work. Use GPU pods when CUDA, model inference, training, or GPU memory is required.
- Do not pass GPU flags when creating CPU pods. Check `runpodctl pod create --help` for the current valid flag set.
- For SSH, prefer `runpodctl pod get <pod-id>` or `runpodctl ssh info <pod-id>` to retrieve connection details. Do not use deprecated interactive SSH commands.
- Network volumes are location-sensitive. Check datacenter availability before attaching volumes, and use `send` / `receive` or S3-compatible storage for migrations.
- Clean up paid resources after tests: delete serverless endpoints, pods, and temporary volumes created for validation.

## Commands

### Pods

```bash
runpodctl pod list                                    # List running pods (default, like docker ps)
runpodctl pod list --all                              # List all pods including exited
runpodctl pod list --status exited                    # Filter by status (RUNNING, EXITED, etc.)
runpodctl pod list --since 24h                        # Pods created within last 24 hours
runpodctl pod list --created-after 2025-01-15         # Pods created after date
runpodctl pod get <pod-id>                            # Get pod details (includes SSH info)
runpodctl pod create --template-id runpod-torch-v21 --gpu-id "NVIDIA GeForce RTX 4090"  # Create from template
runpodctl pod create --image "runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404" --gpu-id "NVIDIA GeForce RTX 4090"  # Create with image
runpodctl pod create --compute-type cpu --image ubuntu:22.04  # Create CPU pod
runpodctl pod start <pod-id>                          # Start stopped pod
runpodctl pod stop <pod-id>                           # Stop running pod
runpodctl pod restart <pod-id>                        # Restart pod
runpodctl pod reset <pod-id>                          # Reset pod
runpodctl pod update <pod-id> --name "new"            # Update pod
runpodctl pod delete <pod-id>                         # Delete pod (aliases: rm, remove)
```

For exact pod flags, run `runpodctl pod <action> --help`.

### Hub

Browse and search the Runpod Hub — a curated marketplace of deployable repos.

```bash
runpodctl hub list                                    # Top 10 by stars
runpodctl hub list --type SERVERLESS                  # Only serverless repos
runpodctl hub list --type POD                         # Only pod repos
runpodctl hub list --category ai --limit 20           # Filter by category
runpodctl hub list --order-by deploys                 # Order by deploys
runpodctl hub list --owner runpod-workers             # Filter by repo owner
runpodctl hub search vllm                             # Search for "vllm"
runpodctl hub search whisper --type SERVERLESS        # Search serverless repos
runpodctl hub get <listing-id>                        # Get by listing id
runpodctl hub get runpod-workers/worker-vllm          # Get by owner/name
```

For exact Hub flags, run `runpodctl hub <action> --help`.

### Serverless (alias: sls)

```bash
runpodctl serverless list                             # List all endpoints
runpodctl serverless get <endpoint-id>                # Get endpoint details
runpodctl serverless create --name "x" --template-id "tpl_abc"  # Create from template
runpodctl serverless create --name "x" --hub-id <listing-id>    # Create from hub repo
runpodctl serverless create --hub-id <id> --env MODEL_NAME=my-model  # Override hub env defaults
runpodctl serverless update <endpoint-id> --workers-max 5       # Update endpoint
runpodctl serverless delete <endpoint-id>             # Delete endpoint
```

**Create from hub:** `--hub-id` resolves the hub listing, extracts the build image and config (GPU IDs, container disk, env vars), creates an inline template, and deploys. Accepts both SERVERLESS and POD listing types. GPU IDs and env var defaults from the hub config are included automatically; override with `--gpu-id` and `--env`.

For exact serverless flags, run `runpodctl serverless <action> --help`.

### Templates (alias: tpl)

```bash
runpodctl template list                               # Official + community (first 10)
runpodctl template list --type official               # All official templates
runpodctl template list --type community              # Community templates (first 10)
runpodctl template list --type user                   # Your own templates
runpodctl template list --all                         # Everything including user
runpodctl template list --limit 50                    # Show 50 templates
runpodctl template search pytorch                     # Search for "pytorch" templates
runpodctl template search comfyui --limit 5           # Search, limit to 5 results
runpodctl template search vllm --type official        # Search only official
runpodctl template get <template-id>                  # Get template details (includes README, env, ports)
runpodctl template create --name "x" --image "img"    # Create template
runpodctl template create --name "x" --image "img" --serverless  # Create serverless template
runpodctl template update <template-id> --name "new"  # Update template
runpodctl template delete <template-id>               # Delete template
```

For exact template flags, run `runpodctl template <action> --help`.

### Network Volumes (alias: nv)

```bash
runpodctl network-volume list                         # List all volumes
runpodctl network-volume get <volume-id>              # Get volume details
runpodctl network-volume create --name "x" --size 100 --data-center-id "US-GA-1"  # Create volume
runpodctl network-volume update <volume-id> --name "new"  # Update volume
runpodctl network-volume delete <volume-id>           # Delete volume
```

For exact network volume flags, run `runpodctl network-volume <action> --help`.

### Models

```bash
runpodctl model list                                  # List your models
runpodctl model list --all                            # List all models
runpodctl model list --name "llama"                   # Filter by name
runpodctl model list --provider "meta"                # Filter by provider
runpodctl model add --name "my-model" --model-path ./model  # Add model
runpodctl model remove --name "my-model"              # Remove model
```

For exact model flags, run `runpodctl model <action> --help`.

### Registry (alias: reg)

```bash
runpodctl registry list                               # List registry auths
runpodctl registry get <registry-id>                  # Get registry auth
runpodctl registry create --name "x" --username "u" --password "p"  # Create registry auth
runpodctl registry delete <registry-id>               # Delete registry auth
```

For exact registry flags, run `runpodctl registry <action> --help`.

### Info

```bash
runpodctl user                                        # Account info and balance (alias: me)
runpodctl gpu list                                    # List available GPUs
runpodctl gpu list --include-unavailable              # Include unavailable GPUs
runpodctl datacenter list                             # List datacenters (alias: dc)
runpodctl billing pods                                # Pod billing history
runpodctl billing serverless                          # Serverless billing history
runpodctl billing network-volume                      # Volume billing history
```

For exact info and billing flags, run `runpodctl <command> --help` or `runpodctl billing <resource> --help`.

### SSH

```bash
runpodctl ssh info <pod-id>                           # Get SSH info (command + key, does not connect)
runpodctl ssh list-keys                               # List SSH keys
runpodctl ssh add-key                                 # Add SSH key
runpodctl ssh remove-key --name <name>                # Remove key by name
runpodctl ssh remove-key --fingerprint <fp>           # Remove key by fingerprint
```

**Remove-key:** if multiple keys share a name, use `--fingerprint` to disambiguate.

**Agent note:** `ssh info` returns connection details, not an interactive session. If interactive SSH is not available, execute commands remotely via `ssh user@host "command"`.

### File Transfer

```bash
runpodctl send <path>                                 # Send files (outputs code)
runpodctl receive <code>                              # Receive files using code
```

### Utilities

```bash
runpodctl doctor                                      # Diagnose and fix CLI issues
runpodctl update                                      # Update CLI
runpodctl version                                     # Show version
runpodctl completion                                  # Auto-detect shell and install completion
```

## URLs

### Pod URLs

Access exposed ports on your pod:

```
https://<pod-id>-<port>.proxy.runpod.net
```

Example: `https://abc123xyz-8888.proxy.runpod.net`

### Serverless URLs

```
https://api.runpod.ai/v2/<endpoint-id>/run        # Async request
https://api.runpod.ai/v2/<endpoint-id>/runsync    # Sync request
https://api.runpod.ai/v2/<endpoint-id>/health     # Health check
https://api.runpod.ai/v2/<endpoint-id>/status/<job-id>  # Job status
```
