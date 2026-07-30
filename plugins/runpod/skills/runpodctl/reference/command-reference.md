# runpodctl — full command reference

Live `runpodctl <resource> <action> --help` is always authoritative for exact flags. This
is the fuller menu (the SKILL keeps the 80% essentials); use it for the long-tail flags.

Output shapes, error codes and env vars are in
[output-and-errors.md](output-and-errors.md).

## Pods

```bash
runpodctl pod list                                    # List running pods (default, like docker ps)
runpodctl pod list --all                              # List all pods including exited
runpodctl pod list --status exited                    # Filter by status (RUNNING, EXITED, etc.)
runpodctl pod list --since 24h                        # Pods created within last 24 hours
runpodctl pod list --created-after 2025-01-15         # Pods created after date
runpodctl pod get <pod-id>                            # Get pod details (includes SSH info)
runpodctl pod create --template-id runpod-torch-v21 --gpu-id "NVIDIA GeForce RTX 4090"  # From template
runpodctl pod create --image "runpod/pytorch:..." --gpu-id "NVIDIA GeForce RTX 4090"    # From image
runpodctl pod create --compute-type cpu --image ubuntu:22.04  # CPU pod (lowercase `cpu`)
runpodctl pod start <pod-id>                          # Start stopped pod
runpodctl pod stop <pod-id>                           # Stop running pod
runpodctl pod restart <pod-id>                        # Restart pod
runpodctl pod reset <pod-id>                          # Reset pod
runpodctl pod update <pod-id> --name "new"            # Update pod
runpodctl pod delete <pod-id>                         # Delete pod (aliases: rm, remove)
```

## Hub

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

## Serverless (alias: sls)

```bash
runpodctl serverless list                             # List all endpoints
runpodctl serverless get <endpoint-id>                # Get endpoint details
runpodctl serverless create --name "x" --template-id "tpl_abc"  # Create from template
runpodctl serverless create --name "x" --hub-id <listing-id>    # Create from hub repo
runpodctl serverless create --hub-id <id> --env MODEL_NAME=my-model  # Override hub env defaults
runpodctl serverless create --template-id <id> --gpu-id "NVIDIA GeForce RTX 4090" --model-reference https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct:main  # Attach & cache a HF model (GPU only)
runpodctl serverless create --hub-id <id> --gpu-id "NVIDIA GeForce RTX 4090" --model-reference https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct:main       # Same, on a hub deploy
runpodctl serverless create --compute-type CPU --template-id <id> --instance-id cpu3g-4-16  # CPU endpoint (uppercase `CPU`)
runpodctl serverless create --template-id <t> --network-volume-ids <v1>,<v2> --data-center-ids <dc1>,<dc2>  # Multi-DC (v2.4.0+)
runpodctl serverless update <endpoint-id> --workers-max 5       # Update endpoint
runpodctl serverless delete <endpoint-id>             # Delete endpoint
```

## Templates (alias: tpl)

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
runpodctl template get <template-id>                  # Get template details (README, env, ports)
runpodctl template create --name "x" --image "img"    # Create template
runpodctl template create --name "x" --image "img" --serverless  # Create serverless template
runpodctl template update <template-id> --name "new"  # Update template
runpodctl template delete <template-id>               # Delete template
```

## Network Volumes (alias: nv)

```bash
runpodctl network-volume list                         # List all volumes
runpodctl network-volume get <volume-id>              # Get volume details
runpodctl network-volume create --name "x" --size 100 --data-center-id "US-GA-1"  # Create volume
runpodctl network-volume update <volume-id> --name "new"  # Update volume
runpodctl network-volume delete <volume-id>           # Delete volume
```

## Models (Model Repository)

```bash
runpodctl model list                                  # List your models
runpodctl model list --all                            # List all models (not just yours)
runpodctl model list --name "llama"                   # Filter by name
runpodctl model list --provider "meta"                # Filter by provider
runpodctl model add --name "my-model" --model-path ./model   # Upload a local model dir (multipart)
runpodctl model remove --name "my-model" --owner <owner>     # Remove a model
```

`model add` supports upload sessions, versioning, metadata, and private-source credentials —
see live `runpodctl model add --help`. Concepts: [model-caching.md](model-caching.md).

## Registry (alias: reg)

```bash
runpodctl registry list                               # List registry auths
runpodctl registry get <registry-id>                  # Get registry auth
runpodctl registry create --name "x" --username "u" --password "p"  # Create registry auth
runpodctl registry delete <registry-id>               # Delete registry auth
```

## Info

```bash
runpodctl user                                        # Account info and balance (alias: me)
runpodctl gpu list                                    # List available GPUs (+ $/hr per cloud + dataCenterAvailability[])
runpodctl gpu list --include-unavailable              # Include unavailable GPUs
runpodctl datacenter list                             # List datacenters (alias: dc)
runpodctl billing pods                                # Pod billing history
runpodctl billing serverless                          # Serverless billing history
runpodctl billing network-volume                      # Volume billing history
```

## SSH

```bash
runpodctl ssh info <pod-id>                           # Get SSH info (command + key, does not connect)
runpodctl ssh list-keys                               # List SSH keys
runpodctl ssh add-key                                 # Add SSH key
runpodctl ssh remove-key --name <name>                # Remove key by name
runpodctl ssh remove-key --fingerprint <fp>           # Remove key by fingerprint (disambiguate shared names)
```

`ssh info` returns connection details, not an interactive session. If interactive SSH isn't
available, execute remotely via `ssh user@host "command"`.

## File Transfer

```bash
runpodctl send <path>                                 # Send file/dir — prints a one-time code
runpodctl receive <code>                              # Receive using that code (positional, no --code flag)
```

`send`/`receive` do encrypted, incremental, compressed transfer — don't pre-tar or
pre-compress the source. **Agent flow (one side sends, the other receives):**

1. Run `send <path>` **without** a code. The **first line of stdout is the one-time code**;
   `send` then blocks until the receiver connects — so capture that first line as it streams
   (background the process, tee to a log) rather than waiting for exit.
2. On the other machine (use `runpodctl ssh` into the pod/host if needed) run `receive <code>`
   with that exact code. Each `send` mints a **fresh** code — never reuse or invent one.
3. Both processes must exit `0`. On failure, re-run `send` and use its **new** first-line code.

To push local files to a pod: get `ssh info <pod-id>`, start `send` locally (capture the
code), then `ssh` to the pod and run `receive <code>` there. For large/library-style data, a
network volume or the S3 API is often simpler than `send`/`receive`.

## Utilities

```bash
runpodctl doctor                                      # Diagnose and fix CLI issues (interactive)
runpodctl update                                      # Update CLI to latest
runpodctl version                                     # Show version
runpodctl completion                                  # Auto-detect shell and install completion
```
