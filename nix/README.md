<!--
  nix/README.md — runpod-plugins-official
  Guide to the Nix flake: installing Nix, running the static-analysis gates
  straight from GitHub, the dev shell, and what each check does. Linked from the
  top-level README.
-->

# runpod-plugins-official — Nix flake

This document explains how to use **[Nix](https://nixos.org)** with this repo: how to run the full static-analysis gate with a single command, and how to get a reproducible development environment for the Python hooks and skill scripts.

This repo is a **plugin marketplace** — it ships no application. The Nix tree exists purely to run **detailed static analysis** over every language present (Python, shell, JavaScript, and the Nix files themselves), hermetically and reproducibly.

## Why Nix?

- **One command runs every check** — `nix flake check` runs ruff, mypy, bandit, the unit tests, shellcheck, shfmt, biome, nixfmt, deadnix and statix in an isolated sandbox, without installing any of them onto your system.
- **Reproducible toolchain** — every contributor (and CI) gets the identical tool versions pinned in `flake.lock`, so a lint verdict is the same everywhere. No "works on my machine".
- **No local installs** — you don't need ruff, mypy, biome, shellcheck, etc. on your PATH; Nix fetches exactly the pinned versions into `/nix/store` and they vanish when you leave the shell.

> **The Nix path is optional and self-contained.** The existing CI hooks still run as plain `python3 hooks/<name>.py` (the repo's code is stdlib-only), so if you'd rather not use Nix you can run any hook or the unittest suite directly with a system Python 3.14+. Nix is here to run the *whole* static-analysis gate at once, the same way CI does.

Nix is a package manager for Linux and macOS that gives **reproducible, isolated** environments. It tracks every dependency by content hash, so the versions you get are exactly the versions the flake pins in `flake.lock`. Nothing is installed into `/usr` or your global environment.

> **Policy: findings are fixed, never suppressed.** These are all hard gates, and there are no `# noqa` / `# type: ignore` / `# nosec` escape hatches in the tree. Where a tool's *ruleset* is calibrated (bandit runs at `--severity-level medium`; security lints are owned by bandit, not duplicated in ruff), it is documented at the policy level in `pyproject.toml` — never per line.

---

## 1. Install Nix

If you already have Nix with flakes enabled, skip to [section 2](#2-run-the-checks-straight-from-github).

Choose a **multi-user** (daemon) or **single-user** install:

- **Multi-user** (recommended on most systems) — [docs](https://nix.dev/manual/nix/2.24/installation/#multi-user)
  ```bash
  bash <(curl -L https://nixos.org/nix/install) --daemon
  ```
- **Single-user** — [docs](https://nix.dev/manual/nix/2.24/installation/#single-user)
  ```bash
  bash <(curl -L https://nixos.org/nix/install) --no-daemon
  ```

### Video walkthroughs

| Platform | Video |
|----------|-------|
| Ubuntu | [Installing Nix on Ubuntu](https://youtu.be/cb7BBZLhuUY) |
| Fedora | [Installing Nix on Fedora](https://youtu.be/RvaTxMa4IiY) |

### Enable flakes

Flakes are still an opt-in feature. Enable them permanently:

```bash
test -d /etc/nix || sudo mkdir /etc/nix
echo 'experimental-features = nix-command flakes' | sudo tee -a /etc/nix/nix.conf
```

Or enable them per-command without editing config:

```bash
nix --extra-experimental-features 'nix-command flakes' flake check github:runpod/runpod-plugins-official
```

> **First run** downloads the pinned tools (a few minutes). Later runs reuse the `/nix/store` cache and are effectively instant.

---

## 2. Run the checks straight from GitHub

No clone required — reference the repository directly:

```bash
# Run the whole static-analysis gate
nix flake check github:runpod/runpod-plugins-official

# Drop into the dev shell with the full toolchain
nix develop github:runpod/runpod-plugins-official
```

The bare reference resolves to the repository's **default branch**; pin a branch, tag, or commit for reproducibility:

```bash
nix flake check github:runpod/runpod-plugins-official/<commit-sha>
```

---

## 3. Local development

From a clone of the repo:

```bash
nix develop        # dev shell with the full toolchain + check-* helpers
nix flake check    # every gate, hermetic (no network)
nix fmt            # format the Nix tree with nixfmt
```

Run one gate on its own (substitute your system, e.g. `aarch64-darwin`):

```bash
nix build .#checks.x86_64-linux.mypy
nix build .#checks.x86_64-linux.ruff-lint
nix build .#checks.x86_64-linux.unittest
```

### Dev shell helpers

Entering `nix develop` prints a banner (`rpp-help` re-prints it). The interpreter on PATH runs the hooks, skill scripts and unittest suite directly — the code is stdlib-only, so there is no install step. The helpers mirror the sandboxed gates exactly, so a green dev shell means a green `nix flake check`:

| Helper | Runs |
|--------|------|
| `check-format`   | `ruff format --check .` |
| `check-lint`     | `ruff check .` |
| `check-types`    | `mypy .` |
| `check-security` | `bandit -c pyproject.toml --severity-level medium -r hooks plugins` |
| `check-shell`    | `shellcheck scripts/*.sh` + `shfmt` |
| `check-nix`      | `nixfmt --check .` + `deadnix --fail .` + `statix check .` |
| `check-tests`    | `python3 -B -m unittest discover …` |
| `check-all`      | all of the above, in order |

### Portable lint image (CI without Nix)

For CI systems or hosts that will **not** install Nix, the flake builds an OCI
(Docker) image bundling the exact pinned toolchain plus the same `check-all`
entrypoint. It is **Linux-only** (`dockerTools` builds Linux containers) and is
exposed only on the Linux systems.

```bash
# Build the image and load it into the local Docker daemon
nix run .#lint-image | docker load          # → loads rpp-lint:latest

# Run the whole gate against a checkout (mount it at /work)
docker run --rm -v "$PWD:/work" -w /work rpp-lint:latest

# …or a single group (any check-* name)
docker run --rm -v "$PWD:/work" -w /work rpp-lint:latest check-lint
```

The `check-*` bodies come from the same `dev/commands.nix` the dev shell uses, so
the image, the dev shell and the sandboxed gate run byte-identical commands. Tool
caches are redirected to `/tmp` so the mounted repo is left untouched.

---

## 4. What's in here

The flake is intentionally modular — a thin `flake.nix` orchestrator at the repo root delegates to the files under `nix/`, grouped by concern. Modules are wired with plain `import ./x.nix { inherit … }` so every argument is visible at its call site:

| Path | Purpose |
|------|---------|
| `../flake.nix` | Entry point: inputs (nixpkgs + flake-utils) + `import ./nix`; exposes `devShells`, `checks`, `formatter`, `packages`. Uses `eachSystem` for the default systems **minus `x86_64-darwin`** (nixpkgs dropped it) |
| `default.nix` | Per-system aggregator; wires the modules together. Exposes `packages.lint-image` on Linux only |
| `versions.nix` | **Single source of truth** for the pinned toolchain — the interpreter the code runs on (Python 3.15) plus every static-analysis tool. mypy is a standalone tool here (not layered on the interpreter) so the type gate stays buildable on a Python 3.15 RC |
| `dev/shell.nix` | `nix develop` shell + the generated `check-*` helpers and `rpp-help` banner. Its package list is *derived* from `versions.nix`, so a new tool there appears in the shell automatically |
| `dev/commands.nix` | **Single source** for the `check-*` command list (shell functions + help banner are generated from it) |
| `checks/default.nix` | The `nix flake check` gate — `lib.fileset` scoping (`filesWithExt` / `toSrc` helpers) + one data table of checks mapped through `mk-check.nix` |
| `checks/mk-check.nix` | Helper: each check is a shellchecked `writeShellApplication` + a one-line runner, so the check logic is itself `set -euo pipefail` + shellcheck-verified |
| `packages/lint-image.nix` | The portable OCI lint image (Linux-only) — bundles the pinned toolchain + a `check-all` entrypoint rendered from `dev/commands.nix`, for CI/hosts without Nix |

All tools come straight from the `flake.lock`-pinned nixpkgs (via `versions.nix`); the interpreter is pinned there too. Every check — ruff, mypy, bandit, the unittest suite, and the rest — is one entry in the `checks` table in `checks/default.nix`.

### The checks

`nix flake check` runs, in a sandbox with no network:

- **ruff-lint** — `ruff check .` over the first-party Python
- **ruff-format** — `ruff format --check .`
- **mypy** — `mypy .` under `--strict`
- **bandit** — `bandit --severity-level medium` (security; see the policy note above)
- **unittest** — the stdlib `unittest` suite (mirrors the CI invocation)
- **shellcheck** — every first-party `*.sh` in `scripts/`
- **shfmt** — those same scripts are formatted (`-i 2 -ci`)
- **biome** — first-party JavaScript
- **nixfmt** / **deadnix** / **statix** — the Nix tree lints itself

**Scope.** The Python / shell / JS checks are scoped to the **first-party** tree only. The intentionally-broken scanner corpora under `testdata/**`, the container payloads under `**/golden-paths/**/template/**`, and the eval fixtures under `skills/flash/evals/fixtures/**` are never linted — linting or "fixing" them would corrupt the fixtures the migrate scanner is tested against.

> **The `biome` gate is wired but currently empty.** The only `.js` files in the repo are migrate-scanner fixtures under `testdata/`, which are deliberately excluded. `biome` carries the root `biome.json` so the check stays valid, and it activates the moment a first-party `.js` file lands.

All Nix packages come from [nixpkgs](https://github.com/NixOS/nixpkgs) and are searchable at [search.nixos.org](https://search.nixos.org/packages?channel=unstable).

---

## Troubleshooting

**`error: experimental Nix feature 'nix-command' is disabled`** — flakes aren't enabled; see [Enable flakes](#enable-flakes) above, or prefix the command with `--extra-experimental-features 'nix-command flakes'`.

**`nix flake check github:...` is slow the first time** — that's the initial tool download; subsequent runs use the `/nix/store` cache.

**Want newer tool pins?** — from a clone, run `nix flake update` to refresh `flake.lock`, then re-run the gate.
