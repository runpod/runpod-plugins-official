#
# nix/dev/shell.nix — runpod-plugins-official
#
# The `nix develop` environment: the CPython interpreter plus the static-analysis
# toolchain (mypy included as a standalone tool), a `rpp-help` banner, and
# `check-*` helpers.
#
# Everything comes from Nix — no pip, no virtualenv. The repo's code is
# stdlib-only, so the interpreter on PATH runs the hooks, scripts and unittest
# suite directly.
#
# The `check-*` helpers and the help table are BOTH generated from the single
# command list in ./commands.nix, so that list is written exactly once.
#
{
  pkgs,
  lib,
  versions,
}:
let
  commands = import ./commands.nix;

  # The whole toolchain, straight from ../versions.nix (the single source of
  # truth), plus the interpreter and git. Deriving the tool list from `versions`
  # means a tool added there appears in the shell automatically — there is no
  # second list to keep in sync.
  devPackages = [
    versions.python
    pkgs.git
  ]
  ++ builtins.attrValues (builtins.removeAttrs versions [ "python" ]);

  # Left-justify a helper name into a fixed column so the help table lines up.
  pad =
    s:
    let
      n = 17 - lib.stringLength s;
    in
    s + lib.concatStrings (lib.genList (_: " ") n);

  # A shell function per command, plus the composite `check-all` over the keys.
  funcDefs = lib.concatStringsSep "\n  " (
    lib.mapAttrsToList (name: cmd: "${name}() { ${cmd}; }") commands
  );
  checkAllChain = lib.concatStringsSep " && " (lib.attrNames commands);

  # The help banner, assembled line-by-line (no heredoc indentation pitfalls).
  helpRows = lib.mapAttrsToList (name: cmd: "      ${pad name}${cmd}") commands;
  banner = lib.concatStringsSep "\n" (
    [
      ""
      "    runpod-plugins-official dev shell — all-Nix (no pip, no venv)"
      ""
      "    The interpreter on PATH runs the hooks, skill scripts and unittest"
      "    suite directly. Run the checks against the project config:"
      ""
    ]
    ++ helpRows
    ++ [
      "      ${pad "check-all"}run every check above in order"
      ""
      "    Hermetic gate (sandboxed, no network):"
      "      ${pad "nix flake check"}ruff, mypy, bandit, unittest, shellcheck,"
      "                       shfmt, biome, nixfmt, deadnix, statix"
      ""
      "    ${pad "rpp-help"}show this message"
    ]
  );
in
pkgs.mkShell {
  packages = devPackages;

  shellHook = ''
    ${funcDefs}
    check-all() { ${checkAllChain}; }

    rpp-help() { printf '%s\n' ${lib.escapeShellArg banner}; }

    rpp-help
  '';
}
