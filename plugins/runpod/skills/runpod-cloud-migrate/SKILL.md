---
name: runpod-cloud-migrate
description: >-
  Move a workload from another cloud or GPU platform to Runpod: Vast.ai, Lambda, CoreWeave,
  Paperspace, Modal, Replicate, Baseten, Together AI, Fireworks AI, fal, Hugging Face
  Inference Endpoints, AWS, Google Cloud or Azure. Inventories what the project uses, maps
  it to Runpod, plans, then migrates one workload at a time with verification. To move
  Runpod code between Runpod API versions, use runpod-migrate instead.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/runpod-cloud-migrate/scripts/scan_cloud_usage.py:*) Bash(rg:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "2.1.0" # x-release-please-version
  concepts: [runpod-platform, pod, serverless-endpoint, worker, template, network-volume, global-volume, container-image, gpu-type]
license: Apache-2.0
---

# Migrate to Runpod from another platform

Moves a project that runs on another cloud or GPU platform onto Runpod. This skill owns the
**migration procedure and the per-platform maps**. It does not own how Runpod works or how
to operate it: for those it hands off to the lanes ([router](../runpod/SKILL.md)).

| Need | Owner |
| --- | --- |
| What the other platform's thing becomes on Runpod | the platform playbook in `reference/` (table below) |
| Pods vs Serverless, storage, GPU choice, networking | [runpod-usage](../runpod-usage/SKILL.md) |
| Creating and managing Runpod resources | [runpod-mcp](../runpod-mcp/SKILL.md) or [runpodctl](../runpodctl/SKILL.md), per the router's matrix |
| Python apps without a Dockerfile (`runpod.App`) | [runpod-flash](../runpod-flash/SKILL.md) |
| A Dockerfile and handler for a custom image | [runpod-build-template](../runpod-build-template/SKILL.md) |
| Serving an LLM with an OpenAI-compatible route | [runpod-vllm](../runpod-vllm/SKILL.md) |
| Ordering, flags and traps for a deploy | the [golden paths](../runpod/golden-paths/README.md) |

## Rules that hold for the whole migration

1. **Inventory before anything else.** Never plan from the user's description alone: the
   repo usually depends on more than they remember.
2. **The source platform is read-only until the user says otherwise.** List and describe
   freely. Never stop, scale down, delete or modify a resource on the source platform
   without an explicit instruction naming that resource. A migration that breaks
   production on the old platform before the new one is verified is a failed migration.
3. **Nothing billable on Runpod without an approved plan.** Show the plan and an hourly
   cost bound first (step 3), then create only what the plan lists.
4. **One workload at a time, smallest first.** Verify it with a real request before
   starting the next.
5. **Credentials move as secrets, never as text.** Carry credential *names* across. Ask the
   user to set values as Runpod secrets or environment variables; do not read a value out
   of the source platform, print one, or commit one.
6. **Keep the old path callable.** Put the new endpoint behind a config switch (an env var
   for the base URL or provider) so cutover and rollback are one setting.
7. **State gaps, do not paper over them.** Each playbook ends with a "Gaps: stop and ask
   the user" section. Those are decisions only the user can make.
8. **The playbooks are a snapshot.** Each names the date its platform docs were checked.
   Before relying on a detail of the other platform that the migration hinges on, confirm
   it in that platform's docs or CLI help. For Runpod, the tool in front of you wins
   ([why](../runpod/SKILL.md#these-skills-are-a-snapshot-the-tools-are-the-source-of-truth)).

## The workflow

### 1. Inventory

The scanner ships beside this file, in the installed skill directory, not in the user's
repo. Resolve it first:

```bash
SCAN="$CLAUDE_PLUGIN_ROOT/skills/runpod-cloud-migrate/scripts/scan_cloud_usage.py"
[ -f "$SCAN" ] || SCAN="<directory containing this SKILL.md>/scripts/scan_cloud_usage.py"
[ -f "$SCAN" ] || SCAN=$(find ~/.claude ~/.agents ~/.codex ~/.config -name scan_cloud_usage.py 2>/dev/null | head -1)
python3 "$SCAN" --help >/dev/null || echo "scanner not found: resolve it before continuing"
```

Then, from the root of the user's repo:

```bash
python3 "$SCAN" .            # Markdown summary per platform and kind
python3 "$SCAN" . --json     # every hit, for a large repo
```

It reads files only: no network, no credentials, no edits. Hits are grouped by kind (`sdk`,
`cli`, `api`, `config`, `iac`, `runtime`, `credential`). A hit is evidence, so open the file
before deciding what it means. Show the user the summary table.

The repo is half the picture. Ask the user to run the playbook's "list what's running"
commands on the source platform (or run them yourself when its CLI is authenticated and
the commands are read-only), because consoles hold resources no file mentions.

**No hits** means the project deploys by hand or keeps infrastructure code elsewhere. Ask
what runs where. Do not guess a platform.

### 2. Open the playbook for each platform found

| Platform | Playbook |
| --- | --- |
| Vast.ai | [reference/vast-ai.md](reference/vast-ai.md) |
| Lambda | [reference/lambda.md](reference/lambda.md) |
| CoreWeave, and Kubernetes GPU workloads on any cloud | [reference/coreweave.md](reference/coreweave.md) |
| Paperspace and DigitalOcean GPU | [reference/paperspace.md](reference/paperspace.md) |
| Modal | [reference/modal.md](reference/modal.md) |
| Replicate and Cog | [reference/replicate.md](reference/replicate.md) |
| Baseten and Truss | [reference/baseten.md](reference/baseten.md) |
| Together AI | [reference/together-ai.md](reference/together-ai.md) |
| Fireworks AI | [reference/fireworks-ai.md](reference/fireworks-ai.md) |
| fal | [reference/fal.md](reference/fal.md) |
| Hugging Face Inference Endpoints, Spaces | [reference/hugging-face.md](reference/hugging-face.md) |
| AWS (EC2, SageMaker, Bedrock, Batch) | [reference/aws.md](reference/aws.md) |
| Google Cloud (Compute Engine, Vertex AI, Cloud Run) | [reference/google-cloud.md](reference/google-cloud.md) |
| Azure (GPU VMs, Azure Machine Learning, Azure OpenAI) | [reference/azure.md](reference/azure.md) |

Read only the playbooks the inventory calls for. A platform with no playbook still
migrates: classify each workload by shape with the table in step 3 and translate from
that platform's own docs.

The scanner's `openai-compatible` rows mark clients that already take a base URL, which
makes them a configuration change rather than a rewrite. Its `runpod` rows mean part of the
project is on Runpod already: read those files first and reuse their conventions.

### 3. Plan, and get the plan approved

Classify every workload by its shape, not by the product name it had:

| Workload shape | Runpod target |
| --- | --- |
| Calls a hosted model someone else runs | A Public Endpoint when Runpod hosts that model, else your own endpoint |
| Request in, response out, idle between requests | Serverless queue-based endpoint |
| Your own HTTP server, low latency, custom routes | Serverless load-balancing endpoint |
| An LLM behind an OpenAI-compatible API | Serverless endpoint running the vLLM worker |
| A job that runs to completion (training, batch) | A Pod, or one ephemeral Pod per call from the Runpod SDK |
| Interactive machine (notebook, SSH, IDE) | Pod |
| Always-on service with a stable address | Pod |
| Multi-node training or HPC with Slurm | Instant Cluster |

The reasoning behind each row is in
[runpod-usage concepts](../runpod-usage/reference/concepts.md).

Write the plan as one table and show it before acting:

| Column | Content |
| --- | --- |
| Workload | Name on the source platform, and the files that define it |
| Target | Row from the table above, and the lane that will create it |
| Compute | GPU type or pool sized to the model's memory needs, worker bounds |
| Image and code | Reused as is, rebuilt for `linux/amd64`, or ported (which contract changes) |
| Data | What moves, how large, from where to which storage layer |
| Callers | Files that call the workload and what changes in each |
| Gaps | Rows from the playbook's gaps section that apply, with the options |
| Cost bound | Hourly rate of what will run and for how long during the test |

Read live GPU stock before naming a GPU or data center
([gpu-selection](../runpod-usage/reference/gpu-selection.md)); stock varies, so the plan
names a fallback. Ask the questions the gaps raise in one batch, with the plan in front of
the user. Proceed when they approve.

### 4. Translate (no cloud calls)

Do everything that costs nothing first, on a branch, one commit per workload:

- Port the container contract or app code using the playbook's code translation section.
- Rewrite the infrastructure definitions (Terraform, CI deploy steps).
- Add the config switch for callers (rule 6) and the new credential names.
- Leave the source platform's files in place. Removing them is the last step.

### 5. Provision one workload and move its data

Hand off to the lane the plan names, and follow the matching golden path for ordering.
Move data before the compute that needs it. Storage placement follows
[storage](../runpod-usage/reference/storage.md): a network volume lives in one data
center, so choose the data center from GPU stock and create the volume there.

### 6. Verify with a real request

A resource that reports ready is not a workload that serves. Send the same input to the
old and the new deployment from outside both platforms, then compare: output, latency
of a cold and a warm request, and error handling. Use the playbook's "Verify" section for
platform-specific checks. Fix and repeat until the outputs agree, then report the numbers.

### 7. Cut over, then repeat

Switch callers with the config switch. Keep the old deployment running until the user
confirms the new one under real traffic. Then return to step 4 for the next workload.

### 8. Report, and shut the source down only on request

Finish with: what moved, where each thing lives on Runpod (IDs and URLs), what still runs
on the source platform, the open gaps, what is billing on Runpod now, and how to roll
back. The playbook's "Shut down" section lists the commands that stop billing on the
source platform, including the resources people forget. Offer them. Run one only after the
user approves that specific resource.

## When the user wants only part of this

| The user says | Do |
| --- | --- |
| "What would it take to move off X?" | Steps 1 to 3, then stop at the plan |
| "Compare X and Runpod for this project" | Steps 1 and 2, then the playbook's product map and gaps. No prices for the other platform: point at both pricing pages |
| "Port this file" | Step 4 for that file, and say which other files the inventory found |
| "Move our Terraform" | Step 1 with attention to `iac` hits, then the playbook's Terraform rows |
| "We already moved the compute, fix the callers" | Step 1, then the playbook's client and API call map |
