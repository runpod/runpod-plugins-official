---
concepts: [container-image]
---

# Docker — setup for the selected build route

First inspect the existing environment. `docker --version` checks only the CLI in the
current shell: a Windows host may lack it while an existing WSL distribution or remote
builder already works. Identify the intended shell and available installations before
installing anything. `docker info` checks the daemon/context; inspect `docker context ls`
if it is unreachable. A stopped daemon or wrong context is not a missing installation.

File authoring and eligible hosted builds do not require local Docker. Choose a local
setup only when that is the user's build route. Credentials, tagging and build/push
commands are in [docker.md](docker.md).

- **macOS:** follow [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
  for the current hardware/OS requirements. Choose the installer for the machine's
  architecture; build explicitly for the deployment platform.
- **Windows:** follow [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
  for the selected supported backend and current requirements. Existing WSL Docker,
  native Desktop and remote contexts are different setups. Verify engine startup and
  WSL integration if chosen; do not assume installation automatically makes every
  distribution's CLI work. Administrator/reboot steps are human setup only when needed.
- **Linux:** follow [Docker Engine installation](https://docs.docker.com/engine/install/)
  for the actual distribution. Inspect a chosen installer before executing it; do not
  pipe a downloaded convenience script into a shell as a routine diagnostic.

After the chosen setup, verify a reachable Linux engine, intended context, builder
platform and sufficient disk. Docker daemon access is privileged: diagnose permission
failures without broad socket permissions or unrequested group/system changes.
