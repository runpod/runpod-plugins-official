---
concepts: [container-image]
---

# Docker — one-time setup

Inspect the selected shell first. `docker --version` checks its CLI; `docker info` checks
the engine, and `docker context ls` helps identify an unintended context. A stopped engine
is not a missing installation. Check an existing WSL2 distribution or remote builder
before installing another copy. File authoring does not require a local engine.

If the chosen build route needs a new installation, use the matching setup below.
Credentials, tagging and build/push commands are in [`docker.md`](docker.md).

**macOS:** Download Docker Desktop from https://docs.docker.com/desktop/setup/install/mac-install/
- Choose the **Apple Silicon** installer for M-series Macs, or **Intel Chip** for older Macs
- Open the DMG, drag Docker to Applications, and launch it

**Windows:** Download Docker Desktop from https://docs.docker.com/desktop/setup/install/windows-install/
- For the WSL2 backend, install WSL2 first if needed (`wsl --install` in an admin PowerShell,
  then restart if prompted and finish the distribution setup)
- Run the installer and follow the setup wizard, then launch Docker Desktop
- Enable Docker Desktop's integration for the distribution you will use, then verify
  `docker info` in that terminal; do not assume every WSL distribution is integrated

**Linux:** See https://docs.docker.com/engine/install/ for distro-specific instructions

Choose the actual distribution's documented installation steps. Inspect a downloaded
installer before running it. If Docker Engine is running but your user gets socket
permission errors, the optional `sudo usermod -aG docker $USER` grants access without
`sudo` once the `docker` group exists. Log out and back in, then verify `docker info`.
The `docker` group grants root-level privileges; do not make the socket world-writable.
See [Docker's Linux post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/)
for group creation and alternatives.

After setup, verify the Linux engine, selected context and target builder platform.
