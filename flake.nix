#
# flake.nix — runpod-plugins-official
#
# Thin orchestrator. Every concern lives under ./nix/ and is wired up there.
# See ./nix/default.nix for the per-system aggregator and ./nix/README.md for
# the guided tour.
#
# This repo ships no application — it is a plugin marketplace (Markdown skills)
# with a Python toolchain (CI hooks + skill scripts; a 3.14 floor, run on 3.15
# under Nix), two bash scripts and a unittest suite. The Nix tree exists to run
# detailed static analysis over every language present, hermetically and
# reproducibly.
#
# ---- Getting started: how to run the targets --------------------------------
#
#   Run EVERY check at once (the whole gate — sandboxed, no network). This is the
#   "run all targets" command; CI runs exactly this:
#       nix flake check
#       #  -> ruff-lint ruff-format mypy bandit unittest shellcheck shfmt
#       #     biome nixfmt deadnix statix
#
#   Run ONE check on its own:
#       nix build .#checks.<system>.<name>      # e.g. .#checks.x86_64-linux.mypy
#       #  <name>:   any gate listed above
#       #  <system>: x86_64-linux | aarch64-linux | aarch64-darwin
#       #  (x86_64-darwin is intentionally absent — nixpkgs dropped it)
#
#   Iterate in a dev shell (tools on PATH; the check-* helpers mirror the gate,
#   so a green shell means a green `nix flake check`):
#       nix develop
#       # then:  check-all         run every check against the working tree
#       #        check-lint / check-types / check-security / check-shell /
#       #        check-nix / check-tests / check-format   run one group
#       #        rpp-help          re-print the banner
#
#   Format the Nix tree:      nix fmt
#
#   Build the portable lint image (an OCI image bundling the pinned toolchain +
#   a `check-all` entrypoint, for CI/hosts WITHOUT Nix — Linux only):
#       nix run .#lint-image | docker load
#       docker run --rm -v "$PWD:/work" -w /work <loaded-image>   # runs check-all
#
#   Run without cloning:      nix flake check github:runpod/runpod-plugins-official
#                             nix develop     github:runpod/runpod-plugins-official
#
# See ./nix/README.md for the full guide.
# -----------------------------------------------------------------------------
#
{
  description = "runpod-plugins-official — static-analysis and dev tooling for the Runpod plugin marketplace";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    # x86_64-darwin is intentionally omitted: nixpkgs 26.11 dropped support for
    # it, so the pinned toolchain no longer evaluates there. The default set minus
    # that one platform.
    flake-utils.lib.eachSystem
      [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ]
      (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          inherit (nixpkgs) lib;

          aggregator = import ./nix {
            inherit pkgs lib;
            src = ./.;
          };
        in
        {
          inherit (aggregator)
            devShells
            checks
            formatter
            packages
            ;
        }
      );
}
