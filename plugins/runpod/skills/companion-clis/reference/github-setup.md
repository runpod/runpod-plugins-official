---
concepts: [hub-repo]
---

# GitHub CLI — one-time setup

Install `gh` and set up an SSH key (only needed once, if `gh --version` fails or your key
isn't registered yet). Auth verification and commands are in [`github.md`](github.md).

## Install

```bash
# macOS
brew install gh

# Linux (Debian/Ubuntu)
(type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)) \
  && sudo mkdir -p -m 755 /etc/apt/keyrings \
  && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  && cat $out | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
  && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
     | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
  && sudo apt update && sudo apt install gh -y

# Linux (Alpine)
apk add github-cli

# Windows (WSL2): use the Linux (Debian/Ubuntu) installer above
```

## SSH Keys

An SSH key identifies your machine as authentic to remote services. Generate one key and
register the public key with each service that requires it — GitHub (via `gh`) and
HuggingFace (via browser).

**Generate a key**

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
# Saves to ~/.ssh/id_ed25519 (private) and ~/.ssh/id_ed25519.pub (public)
# Press Enter to accept the default path; set a passphrase or leave blank
```

**Add the key to the SSH agent**

```bash
# macOS
eval "$(ssh-agent -s)"
ssh-add --apple-use-keychain ~/.ssh/id_ed25519

# macOS — also add to ~/.ssh/config so the key loads automatically on login.
# Create the file if it doesn't exist, and add these lines:
#
#   Host *
#     AddKeysToAgent yes
#     UseKeychain yes
#     IdentityFile ~/.ssh/id_ed25519

# Linux
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Windows (WSL2): use the Linux instructions above
```

**Register the public key with each service** (do this after `gh auth login`, see [`github.md`](github.md)):

```bash
# GitHub — upload via gh CLI (requires auth to be completed first)
gh ssh-key add ~/.ssh/id_ed25519.pub --title "my-machine"

# HuggingFace — paste contents of public key manually in browser
cat ~/.ssh/id_ed25519.pub   # copy this output
# Then add at https://huggingface.co/settings/keys
```
