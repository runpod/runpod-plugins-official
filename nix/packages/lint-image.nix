#
# nix/packages/lint-image.nix — runpod-plugins-official
#
# A portable OCI (Docker) image that bundles the pinned static-analysis toolchain
# plus a `check-all` entrypoint, for CI or hosts that will not install Nix. Build
# and load it with:
#
#   nix run .#lint-image | docker load
#   docker run --rm -v "$PWD:/work" -w /work <loaded-image>          # runs check-all
#   docker run --rm -v "$PWD:/work" -w /work <loaded-image> check-lint   # one group
#
# DRY: the `check-*` bodies come from ../dev/commands.nix — the SAME single source
# the dev shell renders — so the image, the dev shell and the sandboxed gate all
# run byte-identical commands. A tool added to ../versions.nix appears here
# automatically (the toolchain is derived from it), and a command changed in
# commands.nix changes here too.
#
# Linux-only: `dockerTools` builds Linux containers, so ../default.nix exposes this
# package only on Linux systems.
#
{
  pkgs,
  lib,
  versions,
}:
let
  commands = import ../dev/commands.nix;

  # Everything the check-* commands invoke: the interpreter + every tool from the
  # single source of truth, plus the base utilities a bare container lacks.
  toolchain = [
    versions.python
    # gitMinimal, not full git: no check invokes the git binary, but ruff/biome
    # resolve VCS roots when it is present, and it avoids git's large Perl closure.
    pkgs.gitMinimal
    pkgs.coreutils
    pkgs.bashInteractive
    pkgs.findutils
    pkgs.gnugrep
  ]
  ++ builtins.attrValues (builtins.removeAttrs versions [ "python" ]);

  # Render commands.nix into shell functions + the composite check-all, exactly as
  # ../dev/shell.nix does for the interactive shell.
  funcDefs = lib.concatStringsSep "\n" (
    lib.mapAttrsToList (name: cmd: "${name}() { ${cmd}; }") commands
  );
  checkAllChain = lib.concatStringsSep " && " (lib.attrNames commands);

  # The entrypoint is a writeShellApplication, so shellcheck runs over the rendered
  # commands at build time and PATH is pinned to the toolchain.
  entrypoint = pkgs.writeShellApplication {
    name = "rpp-lint";
    runtimeInputs = toolchain;
    text = ''
      # Keep tool caches out of the caller's mounted repo.
      export PYTHONDONTWRITEBYTECODE=1
      export MYPY_CACHE_DIR="''${MYPY_CACHE_DIR:-/tmp/mypy-cache}"
      export RUFF_CACHE_DIR="''${RUFF_CACHE_DIR:-/tmp/ruff-cache}"

      ${funcDefs}
      check-all() { ${checkAllChain}; }

      # No args → run the whole gate; otherwise run the named check(s).
      if [ "$#" -eq 0 ]; then
        check-all
      else
        "$@"
      fi
    '';
  };
in
pkgs.dockerTools.streamLayeredImage {
  name = "rpp-lint";
  tag = "latest";
  contents = [ entrypoint ] ++ toolchain;

  # A bare image has no /tmp; the caches above and mktemp need it.
  extraCommands = "mkdir -p tmp work";

  config = {
    Entrypoint = [ (lib.getExe entrypoint) ];
    WorkingDir = "/work";
    Env = [
      "HOME=/tmp"
      "TMPDIR=/tmp"
    ];
  };
}
