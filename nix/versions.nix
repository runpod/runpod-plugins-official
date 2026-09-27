#
# nix/versions.nix — runpod-plugins-official
#
# Single source of truth for the pinned toolchain (the xtcp2 idiom). Every tool
# resolves from the flake.lock-pinned nixpkgs, so the only thing this file
# decides is *which* attributes we depend on — the versions themselves move only
# when flake.lock is updated.
#
# The interpreter (3.15) runs ahead of the repo's CI floor (3.14): unittest runs
# on this current CPython, while ruff `target-version` and mypy `python_version`
# in pyproject.toml keep us from emitting syntax that floor can't run.
#
{ pkgs }:
{
  # The interpreter the repo's own code RUNS on (unittest + the dev shell). Pinned
  # to 3.15 per the project's "run on the latest Python" decision.
  python = pkgs.python315;

  # Static-analysis tools. mypy is decoupled from `python` on purpose: it is a
  # static analyzer (bundled typeshed, `python_version` read from pyproject.toml),
  # so it need not be BUILT against the interpreter — and on a Python 3.15 RC the
  # mypy package's own build is broken (its check-dep pytest-xdist fails under the
  # RC). Taking mypy from the default-python `pkgs.mypy` keeps the type gate
  # buildable and cached while the code still runs on 3.15. Also: shell, ruff,
  # bandit, JavaScript (wired for future first-party JS; testdata excluded), and
  # the tools the Nix tree lints itself with.
  inherit (pkgs)
    ruff
    mypy
    bandit
    shellcheck
    shfmt
    biome
    nixfmt
    deadnix
    statix
    ;
}
