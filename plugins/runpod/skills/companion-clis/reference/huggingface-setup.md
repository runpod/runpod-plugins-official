---
concepts: [container-image]
---

# HuggingFace CLI — one-time setup

Install the `hf` CLI (only needed once, if `hf version` fails). Auth and `hf download`
recipes are in [`huggingface.md`](huggingface.md).

```bash
# macOS / Linux (standalone installer — recommended)
curl -LsSf https://hf.co/cli/install.sh | bash

# macOS (Homebrew)
brew install hf

# Windows (WSL2): use the Linux standalone installer above
```

> **Note:** `pip install huggingface_hub` installs the older Python CLI (`huggingface-cli`),
> which uses different command syntax. Use the standalone `hf` CLI installed above.
