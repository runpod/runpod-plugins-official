#
# nix/checks/default.nix — runpod-plugins-official
#
# The `nix flake check` gate: one derivation per tool, each running that tool
# against the project's own config in a network-free sandbox.
#
# Two ideas keep this small and DRY:
#   1. lib.fileset scoping — every check sees ONLY the files that can change its
#      result, so editing Markdown invalidates nothing and editing a `.sh`
#      rebuilds only the shell checks. The `filesWithExt` / `toSrc` helpers below
#      remove the per-check boilerplate.
#   2. one data table (`checks`) mapped once through ./mk-check.nix — a check is
#      just `{ runtimeInputs; src; text; }`, so adding a gate is adding one entry.
#
# First-party scope (the important difference from a whole-tree lint): the Python
# / shell / JS source sets are explicit unions of the first-party roots, so the
# intentionally-broken scanner corpora under `testdata/**`, the container
# payloads under `**/golden-paths/**/template/**`, and the eval fixtures under
# `skills/flash/evals/fixtures/**` are never linted.
#
# Policy: these are ALL hard gates and there are NO suppressions. A finding is
# fixed by changing the code, never by an ignore comment. mypy runs `--strict`
# and bandit runs on the whole first-party tree (both configured in pyproject.toml).
#
{
  pkgs,
  lib,
  src,
  versions,
}:
let
  fs = lib.fileset;

  # Every check is a shellchecked writeShellApplication + a one-line runner.
  mkCheck = import ./mk-check.nix { inherit pkgs lib; };

  # ---- fileset helpers ----------------------------------------------------
  # `filesWithExt "py" root` → the .py files under root; `toSrc fileset` → a store
  # path holding exactly that fileset, rooted at the repo.
  filesWithExt = ext: root: fs.fileFilter (f: f.hasExt ext) root;
  toSrc =
    fileset:
    fs.toSource {
      inherit fileset;
      root = src;
    };

  # ---- first-party roots --------------------------------------------------
  hooks = src + "/hooks";
  migrate = src + "/plugins/runpod/skills/runpod-migrate";
  templates = src + "/plugins/runpod/skills/runpod-templates";
  scriptsDir = src + "/scripts";

  # Skill scripts and their unit tests. The tests add ../scripts to sys.path, so
  # the two travel together (they are the unittest source set).
  pyScriptRoots = [
    (migrate + "/scripts")
    (templates + "/scripts")
  ];
  pyTestRoots = [
    (migrate + "/tests")
    (templates + "/tests")
  ];
  # The .py the tools own: CI hooks + skill scripts + tests.
  pyRoots = [ hooks ] ++ pyScriptRoots ++ pyTestRoots;

  # ---- scoped sources -----------------------------------------------------
  # ruff/mypy/bandit also read their config from pyproject.toml, so it ships too.
  pySrc = toSrc (fs.unions (map (filesWithExt "py") pyRoots ++ [ (src + "/pyproject.toml") ]));
  testSrc = toSrc (fs.unions (map (filesWithExt "py") (pyScriptRoots ++ pyTestRoots)));
  shSrc = toSrc (filesWithExt "sh" scriptsDir);
  nixSrc = toSrc (filesWithExt "nix" src);
  # First-party JS = every .js EXCEPT the testdata fixtures. There is none today,
  # so the gate carries biome.json to stay non-empty and become active the moment
  # a first-party .js lands.
  jsSrc = toSrc (
    fs.unions [
      (fs.difference (filesWithExt "js" src) (src + "/testdata"))
      (src + "/biome.json")
    ]
  );

  # Walk the scoped copy for tools that don't recurse a directory themselves
  # (shellcheck, nixfmt): every match, NUL-delimited so paths with spaces are
  # safe, `-r` so an empty match is not an error.
  walk = ext: tool: "find . -name '*.${ext}' -print0 | xargs -0 -r ${tool}";

  # ---- the checks (pure data; one entry == one gate) ----------------------
  checks = {
    ruff-lint = {
      runtimeInputs = [ versions.ruff ];
      src = pySrc;
      text = "ruff check .";
    };
    ruff-format = {
      runtimeInputs = [ versions.ruff ];
      src = pySrc;
      text = "ruff format --check .";
    };
    mypy = {
      runtimeInputs = [ versions.mypy ];
      src = pySrc;
      text = "mypy .";
    };
    # bandit reads exclude_dirs and the `--severity-level medium` policy from
    # pyproject.toml — a documented policy, not a per-finding suppression.
    bandit = {
      runtimeInputs = [ versions.bandit ];
      src = pySrc;
      text = "bandit -c pyproject.toml --severity-level medium -r .";
    };
    # Mirrors the `unittest discover` invocations in .github/workflows/validate.yml
    # so the gate and CI can't drift; runs on the pinned interpreter (the repo's
    # code is stdlib-only, so no extra packages are needed).
    unittest = {
      runtimeInputs = [ versions.python ];
      src = testSrc;
      text = ''
        export PYTHONDONTWRITEBYTECODE=1
        for skill in runpod-templates runpod-migrate; do
          python3 -B -m unittest discover \
            -s "plugins/runpod/skills/$skill/tests" -p "test_*.py"
        done
      '';
    };
    shellcheck = {
      runtimeInputs = [ versions.shellcheck ];
      src = shSrc;
      text = walk "sh" "shellcheck";
    };
    shfmt = {
      runtimeInputs = [ versions.shfmt ];
      src = shSrc;
      text = "shfmt --diff --indent 2 --case-indent .";
    };
    biome = {
      runtimeInputs = [ versions.biome ];
      src = jsSrc;
      text = "biome ci --error-on-warnings .";
    };
    nixfmt = {
      runtimeInputs = [ versions.nixfmt ];
      src = nixSrc;
      text = walk "nix" "nixfmt --check";
    };
    deadnix = {
      runtimeInputs = [ versions.deadnix ];
      src = nixSrc;
      text = "deadnix --fail .";
    };
    statix = {
      runtimeInputs = [ versions.statix ];
      src = nixSrc;
      text = "statix check .";
    };
  };
in
lib.mapAttrs (name: c: mkCheck ({ name = "rpp-${name}"; } // c)) checks
