---
concepts: [container-image]
---

# HuggingFace CLI

The HuggingFace CLI (`hf`) is used to download models from the Hub to your local machine so they are cached and available when you build and run the Docker container. For example, to deploy `openai/gpt-oss-20b` to a Runpod serverless endpoint: download the model locally first, build a Docker image that includes or mounts it, validate the container locally, then push the image to Docker Hub for Runpod to pull.

> **Not installed?** One-time install lives in [`huggingface-setup.md`](huggingface-setup.md) — skip if `hf version` already works.
>
> Use the standalone `hf` CLI, **not** `pip install huggingface_hub` (that's the older `huggingface-cli`, different syntax).

## Credentials

Get a token at https://huggingface.co/settings/tokens. Use **write** access for uploading; **read** access is sufficient for downloading public or gated models.

```bash
# Option 1: interactive login (saves token to ~/.cache/huggingface/token, optionally to git credential store)
hf auth login

# Option 2: non-interactive (pass token directly, useful in scripts and pod start commands)
hf auth login --token $HF_TOKEN --add-to-git-credential

# Option 3: environment variable (takes precedence over saved token; to revert, unset the variable)
export HF_TOKEN=hf_...
```

```bash
hf auth whoami      # confirm auth and org memberships
hf auth logout      # delete all locally stored tokens
```

## Key Commands

```bash
# Download a model to a local directory (use --local-dir to control where it lands)
hf download openai/gpt-oss-20b --local-dir ./models/gpt-oss-20b
hf download meta-llama/Llama-3.1-8B --local-dir ./models/llama-3.1-8b

# Download a single file from a model repo
hf download openai/gpt-oss-20b config.json --local-dir ./models/gpt-oss-20b

# Download with glob filters (e.g. only safetensors weights, skip fp16 variants)
hf download stabilityai/stable-diffusion-xl-base-1.0 \
  --include "*.safetensors" --exclude "*.fp16.*" \
  --local-dir ./models/sdxl

# Download a specific revision (commit hash, branch, or tag — append --revision REF)
hf download openai/gpt-oss-20b --revision v1.0 --local-dir ./models/gpt-oss-20b
```

## Troubleshooting

```bash
# Increase download timeout on slow connections (default: 10s)
export HF_HUB_DOWNLOAD_TIMEOUT=30
```
