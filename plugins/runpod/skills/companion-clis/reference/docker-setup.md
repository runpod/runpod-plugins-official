---
concepts: [container-image]
---

# Docker — one-time setup

Install Docker (only needed once, if `docker --version` fails). Credentials, tagging,
and build/push commands are in [`docker.md`](docker.md).

**macOS:** Download Docker Desktop from https://docs.docker.com/desktop/setup/install/mac-install/
- Choose the **Apple Silicon** installer for M-series Macs, or **Intel Chip** for older Macs
- Open the DMG, drag Docker to Applications, and launch it

**Windows:** Download Docker Desktop from https://docs.docker.com/desktop/setup/install/windows-install/
- Requires WSL 2 — install it first if needed (`wsl --install` in an admin PowerShell, then restart); Docker Desktop then detects it automatically
- After installation, `docker` commands work inside your WSL2 terminal without extra configuration
- Run the installer and follow the setup wizard

**Linux:** See https://docs.docker.com/engine/install/ for distro-specific instructions

```bash
# Linux convenience script (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # allow non-root usage (re-login after)
```
