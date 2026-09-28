#
# nix/dev/commands.nix — runpod-plugins-official
#
# Single source of truth for the dev-shell `check-*` helpers. Each entry maps a
# helper name to the exact command it runs against the project's own config.
# ./shell.nix renders this attrset into BOTH the shell functions and the help
# banner, so the command list is written exactly once (the composite `check-all`
# is derived from these keys, and so lives in ./shell.nix).
#
# These mirror the sandboxed gates in ../checks/default.nix — same tools, same
# flags — so a green dev shell means a green `nix flake check`. They are written
# separately (not shared with the gate `text`s) on purpose: the gate runs inside
# a fileset-scoped copy where `.` already IS the first-party tree, whereas these
# run against the live working tree, so where the gate can say `.` these name the
# first-party paths (e.g. `-r hooks plugins`, `scripts/*.sh`) to get the same
# scope. Keep the two behaviourally equivalent when you change either.
#
{
  check-format = "ruff format --check .";
  check-lint = "ruff check .";
  check-types = "mypy . && mypy --python-version 3.10 plugins/runpod/skills/runpod-migrate/scripts plugins/runpod/skills/runpod-templates/scripts";
  check-security = "bandit -c pyproject.toml --severity-level medium -r hooks plugins";
  check-shell = "shellcheck scripts/*.sh && shfmt --diff --indent 2 --case-indent scripts";
  # nixfmt is passed explicit files (not `.`): nixfmt deprecated directory args,
  # and this matches the sandboxed gate's file-walk. `-exec … {} +` is portable
  # (BSD + GNU find) and needs no `xargs -r`. deadnix/statix still accept `.`.
  check-nix = "find . -name '*.nix' -not -path './.git/*' -exec nixfmt --check {} + && deadnix --fail . && statix check .";
  check-tests = "python3 -B -m unittest discover -s plugins/runpod/skills/runpod-templates/tests -p 'test_*.py' && python3 -B -m unittest discover -s plugins/runpod/skills/runpod-migrate/tests -p 'test_*.py'";
}
