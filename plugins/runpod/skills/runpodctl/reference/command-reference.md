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
runpodctl pod create --image <img> --gpu-id <id> --wait                  # wait until ssh answers (v2.9.0+)
runpodctl pod create --image <img> --gpu-id <id> --wait --wait-timeout 3m # give up sooner than the 10m default
```

### Waiting for readiness (`--wait`, v2.9.0+)

| | detail |
| --- | --- |
| ready means | the pod's **public port 22** accepts a tcp connection *and* answers with an ssh protocol banner. No key, no handshake — it proves sshd is up, not that your key is installed. Port 22 merely appearing in `runtime.ports` is not enough: prod allocates that port even for images that run no sshd |
| timeout | `--wait-timeout` accepts `90s`, `10m`, `1h`, `2d`; default `10m` |
| output | progress on **stderr** every ~15s; stdout stays exactly one json object, in the `pod get` shape (so it includes the live `ssh` block, unlike a plain create) |
| on failure | the pod is **not** deleted — exit is non-zero, code `wait_timeout` (or `wait_interrupted` on ctrl-c), and the error object carries the pod id in `id` plus the delete command. A second ctrl-c always exits |
| refuses | `--ssh=false` (there would be nothing to wait for) |
| warns, still waits | `--compute-type CPU` (cpu pods are created over rest, which cannot request Runpod-managed ssh, so only an image that starts its own sshd becomes reachable) and `--cloud-type COMMUNITY` without `--public-ip` (community cloud only maps a public ssh port on a machine that has a public ip) |

### Pod status fields

`pod get` and `pod list` report both (v2.9.0+):

| field | meaning |
| --- | --- |
| `desiredStatus` | what the platform intends: `RUNNING`, `EXITED`. Says `RUNNING` while the image is still pulling |
| `runtimeStatus` | what is actually happening: `running`, `initializing` (no container reported yet — pull/create/boot), `stopped`, `terminated`, `unknown` (the runtime lookup failed or was not made — **not** "the pod is down") |
| `runtimeStatusReason` | stable token when there is more to say, e.g. `awaiting_container`, `stopped_by_user`, `stopped_by_runpod`, `terminated_outbid`, `runtime_unavailable` |
| `uptimeSeconds` | present only while the container is up; omitted otherwise (it used to be a constant `0`) |
| `lastStatusChange` | the backend's raw free-text note, carried so a phrasing the cli does not tokenise still reaches you |

`--status` filters **`desiredStatus` only** — `--status initializing` silently matches nothing.

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
runpodctl serverless create --template-id <id> --workers-min 1 --wait  # wait for a ready worker (v2.9.0+)
```

### Invoking an endpoint (v2.9.0+)

```bash
runpodctl serverless run <endpoint-id> --input '{"prompt":"hi"}'   # submit + wait for the result
runpodctl serverless run <endpoint-id> --input-file payload.json   # payload from a file ("-" = stdin)
runpodctl serverless run <endpoint-id> --input '{}' --wait 15m     # wait budget (default 5m; 0 = do not wait)
runpodctl serverless run <endpoint-id> --input '{}' --no-wait      # submit only (same as --wait 0)
runpodctl serverless status <endpoint-id> <job-id>                 # poll a job submitted earlier
runpodctl serverless health <endpoint-id>                          # worker + job counts
```

| | detail |
| --- | --- |
| payload | the **handler** payload, sent as `{"input": <your json>}`. Must be a json object; parsed and size-checked locally (the api's `/run` body limit is 10 MiB), so quoting mistakes and oversized bodies fail as `usage_error` before the upload |
| `--input` vs `--input-file` | mutually exclusive; one is required. `-` reads stdin either way. A payload with its own top-level `input` key gets a warning — that is usually a whole curl envelope pasted in, which arrives double-wrapped |
| stdout | always the job payload, including a `FAILED` job's `error`, and the last payload seen when the wait ran out. Printed byte-faithfully (handler keys are not renamed or re-typed) |
| stderr | progress notes and the error object — never job data |
| exit codes | `0` when `COMPLETED`, and when `--no-wait`/`--wait 0` submitted successfully. `1` on request failure, on wait-budget exhaustion (`timeout`), or on `FAILED`/`CANCELLED`/`TIMED_OUT` (`job_failed`) |
| two budgets | `--wait` bounds the whole job; the shared `timeout` config key (30s) bounds one api call. A call inside a wait is clamped to what is left, never below 1s |
| `/run`, never `/runsync` | `/runsync` is not synchronous: the connection is released after ~90s with the job still running, no job id exists until it answers (so a slow response strands a billed, unpollable job), and a `sync-` job's result expires after 1 minute vs 30 for `/run` |

### Error codes worth branching on

`timeout`, `job_failed`, `wait_timeout` and `wait_interrupted` are the codes these commands
add, and `not_found` gains a nuance during a wait. They live with every other code in
[output-and-errors.md](output-and-errors.md#codes) — including which are safe to retry, which
mean work outlived the cli, and the `id` field that names a resource a failed wait left
behind.

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
