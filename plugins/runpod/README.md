# Runpod

One entrypoint for AI agents to manage GPU workloads on Runpod — pods, serverless
endpoints, jobs, templates, and volumes — via the Runpod MCP server, `runpodctl`,
and `flash`, with conceptual guidance and worked golden paths.

This plugin bundles seven skills, the hosted Runpod MCP server config
([`.mcp.json`](.mcp.json)), and reference material.

## Which skill?

Start with **`runpod`** — the router. It reads your task and points to the right
lane below. If you already know the lane, go straight to it.

| Skill | Use it for |
| --- | --- |
| [`runpod`](skills/runpod/SKILL.md) | Router / entrypoint. Start here when the right skill is unclear. |
| [`runpod-mcp`](skills/runpod-mcp/SKILL.md) | Manage infra (pods, endpoints, jobs, templates, volumes, catalog, billing) via the Runpod **MCP server**'s structured tool calls. |
| [`runpodctl`](skills/runpodctl/SKILL.md) | Manage infra from the **CLI**, plus Hub deploys, file transfer (`send`/`receive`), SSH, and `doctor` setup. |
| [`flash`](skills/flash/SKILL.md) | **Write and deploy your own code** on Runpod serverless — `@remote`/`@Endpoint`, `flash dev`, `flash deploy`. |
| [`companion-clis`](skills/companion-clis/SKILL.md) | Prerequisite CLIs: `hf` (models), `docker` (images), `gh` (repos/releases), `aws` (S3 to volumes). |
| [`runpod-usage`](skills/runpod-usage/SKILL.md) | **Concepts** — how pods/serverless work, building containers, storage, GPU selection, gotchas. |
| [`runpod-migrate`](skills/runpod-migrate/SKILL.md) | **Migrate code** from the GraphQL API or REST v1 to REST v2 — inventory, rewrite, flag breaking changes. |

The migration flow also has a slash command: **`/runpod:migrate [scope] [path]`**
runs the `runpod-migrate` workflow directly, e.g. `/runpod:migrate rest src/`.

**runpod-mcp vs runpodctl:** both drive the same Runpod API for the same infra
CRUD. Prefer `runpod-mcp` when its tools are connected in your session; use
`runpodctl` for the terminal, Hub, file transfer, SSH, or `doctor`.

## The development loop

Any "get X running on Runpod" task follows one loop (in `runpod-usage`): **decide
pod vs serverless → prefer a prebuilt template/Hub worker over from-scratch →
provision → verify with a real request ("Running" ≠ "ready") → deliver → cost-guard
+ teardown.** See [`skills/runpod-usage/reference/development-loop.md`](skills/runpod-usage/reference/development-loop.md).

## Golden paths — check these first

**Before improvising a deployment, look for a golden path that already covers it.**
[`skills/runpod/golden-paths/`](skills/runpod/golden-paths/README.md) holds worked,
end-to-end reference tasks — Ollama and ComfyUI on pods, a Whisper endpoint,
fine-tune → serve, network-volume handoffs, autoscaling, streaming, webhooks,
host-cached HF models, and observability, among others. Nearly all are
**live-verified**: someone ran the whole thing on real infrastructure and pasted back
the actual output, including the parts that went wrong. The index marks the status of
each.

They are worth the detour because they encode the failure modes you would otherwise
hit yourself — the "Running ≠ ready" trap, data-center pinning, cold-start costs,
and cleanup. Point your agent at one directly:

> "Follow golden path 20 to deploy this HuggingFace model."

They are acceptance scenarios, not installed skills (no `SKILL.md`, so agents don't
auto-load them), and they live under the `runpod` router skill that indexes them, so
they travel with it on a single-skill install.

## Getting a model onto a worker

If the model is **on HuggingFace, and you are deploying GPU serverless**, prefer
Runpod's host-side model cache over a network volume:

```bash
runpodctl serverless create --template-id <id> --gpu-id "NVIDIA GeForce RTX 4090" \
  --model-reference https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct:main
```

Runpod caches the weights on the host, so workers start on machines that already
hold the model — cold starts drop to seconds and **you are not billed for download
time**. Weights land in the standard HF cache layout
(`/runpod-volume/huggingface-cache/hub/`), so Transformers, vLLM, and anything else
that reads that cache picks them up with no handler changes. A network volume, by
contrast, is **pinned to one data center**, which narrows the GPU availability you
can schedule against.

Reach for the other options deliberately: a **network volume** when you want direct
filesystem control or are sharing large files across workers, the **Model
Repository** (`runpodctl model add`) for your own artifacts that aren't on
HuggingFace, and **baking into the image** when you need a fully reproducible build.
Caching is GPU-only and needs `runpodctl` ≥ v2.4.0.

Full comparison and commands:
[`runpodctl/reference/model-caching.md`](skills/runpodctl/reference/model-caching.md).
Worked example: golden path
[20 — host-cached HF model endpoint](skills/runpod/golden-paths/20-model-caching-endpoint.md).

## Setup

Everything unifies on a single **`RUNPOD_API_KEY`**
(https://runpod.io/console/user/settings):

```bash
runpodctl doctor          # CLI: store the key + SSH
```

The hosted MCP server (bundled in [`.mcp.json`](.mcp.json)) is the exception — it
uses the "Sign in with Runpod" OAuth flow, so no key is stored on disk (see
[`runpod-mcp`](skills/runpod-mcp/SKILL.md)). Companion CLIs (`hf`, `gh`, `docker`,
`aws`) use their own credentials.

## Usage

For one-off actions, just ask — the router picks the lane:

- "Create a pod with an RTX 4090"
- "Deploy a serverless endpoint from this image"
- "Which GPU should I use for a 13B model?"
- "Write an `@remote` function and run it on a GPU"
- "Download a model, containerize it, and deploy it"

For anything you're **designing** rather than executing, add *"and look at the
examples first"*:

- "Use the Runpod plugin skills and look at the examples. I want to build a speech
  translator: audio in, translated text out. Plan it out."
- "Use the runpod-migrate skill to move this repo to REST v2. Show me the inventory
  before you change anything."
- "Use the Runpod skills and check the examples — deploy this handler to serverless."

The golden paths carry no `SKILL.md`, so they are never auto-loaded, and
`reference/*.md` opens only on demand — asking is what pulls them in. Worth adding
either way: *"verify it with a real request"*, per
[`skills/runpod-usage/reference/development-loop.md`](skills/runpod-usage/reference/development-loop.md).

## URLs

- **Pod:** `https://<pod-id>-<port>.proxy.runpod.net` (e.g. `https://abc123xyz-8888.proxy.runpod.net`)
- **Serverless:** `https://api.runpod.ai/v2/<endpoint-id>/{run|runsync|health|status/<job-id>}`

More in [`skills/runpod-usage/reference/networking.md`](skills/runpod-usage/reference/networking.md).

## Structure

```
skills/
  runpod/            router / entrypoint
    golden-paths/    worked end-to-end reference tasks (indexed by the router)
  runpod-mcp/        Runpod MCP server (structured tool calls)
  runpodctl/         Runpod CLI (+ Hub, transfer, SSH, doctor)
  flash/             write & deploy your own code (@remote)
  companion-clis/    hf / gh / docker / aws prerequisites
  runpod-usage/      concepts + reference/*.md
  runpod-migrate/    GraphQL / REST v1 -> REST v2 migration + inventory scanner
.mcp.json            hosted Runpod MCP server config
```

## License

Apache-2.0
