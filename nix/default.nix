#
# nix/default.nix — runpod-plugins-official
#
# Per-system aggregator. Called once per system by ../flake.nix with a concrete
# `pkgs`, `lib`, and repo `src`. Wires the modules together into the flat outputs
# the flake re-exports:
#
#   { devShells, checks, formatter, packages }
#
# This repo is a plugin marketplace, so there is no application to build. The Nix
# tree's job is the dev shell and the static-analysis gates, both driven by a
# single pinned toolchain (see ./versions.nix): the interpreter the code runs on
# plus every static-analysis tool, incl. a standalone mypy.
#
# The one buildable artifact is `packages.lint-image` — an OCI image bundling that
# same toolchain + a `check-all` entrypoint, for CI/hosts without Nix. It is a
# Linux-only container, so it is exposed only on Linux systems (darwin can't build
# a Linux image without a remote builder).
#
# Modules are wired with plain `import ./x.nix { inherit … }` so every argument is
# visible at its call site; each module declares exactly the inputs it uses.
#
{
  pkgs,
  lib,
  src,
}:
let
  # The pinned toolchain: interpreter + every static-analysis tool.
  versions = import ./versions.nix { inherit pkgs; };

  devShell = import ./dev/shell.nix { inherit pkgs lib versions; };

  checks = import ./checks {
    inherit
      pkgs
      lib
      src
      versions
      ;
  };

  # OCI lint image: Linux-only (dockerTools builds Linux containers), so darwin
  # advertises no `packages` rather than a package that can't build there.
  packages = lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
    lint-image = import ./packages/lint-image.nix { inherit pkgs lib versions; };
  };
in
{
  devShells.default = devShell;

  inherit checks packages;

  formatter = versions.nixfmt;
}
