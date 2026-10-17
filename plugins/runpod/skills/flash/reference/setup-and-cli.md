---
concepts: [flash, api-key]
---

# Runpod SDK — setup & `rp` CLI reference

## Setup

The SDK and the `rp` CLI ship together in the `runpod` package (2.0 and later). Install it
into the project's virtual environment, because dev sessions run your local interpreter.

```bash
# requires Python 3.10-3.14
uv add "runpod>=2.0.0rc2"          # uv project
pip install "runpod>=2.0.0rc2"     # pip / venv
pip show runpod                    # confirm the version (2.x)
rp update                          # upgrade the package in place; rp update --version X pins one
```

The `>=2.0.0rc2` specifier also accepts the 2.0 release candidate, so it resolves to 2.x
whether or not a stable 2.0.0 is published. A plain `pip install runpod` on an index with only
the release candidate installs 1.x, which has no `rp flash`.

The CLI is also installed as `runpod`, so `runpod flash deploy` and `rp flash deploy` are the
same command.

### Auth

```bash
rp login                            # browser approval; saves the key to ~/.runpod/config.toml
rp login --no-open                  # headless: print the approval URL instead of opening a browser
rp login --api-key "$KEY"           # store a key directly, no browser
export RUNPOD_API_KEY=your_key      # headless agents and CI
```

- The SDK reads `RUNPOD_API_KEY` first, then `~/.runpod/config.toml`. A set env var wins, so
  a stale exported key causes 401s even after a good `rp login`.
- `runpodctl` reads the same `config.toml`, so one `rp login` serves both. A key saved by the
  legacy `flash login` keeps working.
- With no key at all, calls fail with "no api key configured. run `rp login` or set RUNPOD_API_KEY."

### Scaffold

```bash
rp flash init my-app      # writes my-app/main.py, requirements.txt, .runpodignore
rp flash init .           # scaffold into the current directory
rp flash init my-app -f   # overwrite existing files
```

The scaffold is a CPU queue function plus a `@runpod.local_entrypoint`, so
`cd my-app && rp flash dev main.py --once` is a working first run.

## CLI

```bash
rp --help                                   # top level: flash, login, logs, pod, registry, secret, ssh, update

# develop
rp flash dev main.py                        # temporary endpoints + run the entrypoint, re-run on save, ^C cleans up
rp flash dev main.py --once                 # run once, tear down, exit non-zero on failure (CI smoke test)

# deploy
rp flash deploy                             # every app found in the cwd -> "default" environment
rp flash deploy main.py --env staging       # one target file, another environment
rp flash deploy --python-version 3.12       # worker Python for dependency wheels (defaults to the local one)
rp flash deploy --exclude scipy,numba       # leave packages out of the artifact (they must come from the image)
rp flash deploy --build-only                # write <app>-artifact.tar.gz, deploy nothing

# apps and environments
rp flash app list                           # every app and its environments
rp flash app get my-app
rp flash app delete my-app --yes            # undeploys every environment in the app
rp flash env list --app my-app
rp flash env add staging --app my-app
rp flash env get staging --app my-app       # an environment with its endpoints
rp flash env delete staging --app my-app --yes

# tear down one environment (the app and its build history remain)
rp flash undeploy --app my-app --env default --yes

# platform helpers in the same CLI
rp secret add hf-token --value "$HF_TOKEN"  # read in code with runpod.Secret("hf-token")
rp registry add my-registry --username USER --password TOKEN   # private images (registry_auth="my-registry")
rp logs POD_ID --follow                     # a Pod's container and system logs
rp ssh POD_ID
```

Take exact flags from `rp <command> --help`; the list above is the shape of the surface.

### Build artifact

- `rp flash deploy` packages your code plus resolved `dependencies` into one artifact of up to
  **1,500 MB**. On the built-in GPU images `torch`, `torchvision`, `torchaudio` and `triton` are
  left out automatically, because the image ships them.
- `.runpodignore` and the project's `.gitignore` files decide what source goes in. `.env`
  files, keys and credential files are always left out.
- `--build-only` resolves dependencies and packages without touching your account, which makes
  it a quick check that discovery and dependency resolution succeed.

## Exact rules

- [flash](../../runpod-usage/concepts/flash.yaml)
- [api-key](../../runpod-usage/concepts/api-key.yaml)
