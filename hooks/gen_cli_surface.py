#!/usr/bin/env python3
"""Regenerate testdata/runpodctl/command-surface.json from a runpodctl binary.

    python3 hooks/gen_cli_surface.py                    # use `runpodctl` on PATH
    python3 hooks/gen_cli_surface.py --bin ./runpodctl  # a specific build

Refresh this when runpodctl cuts a release, then re-run
hooks/check_cli_absence_claims.py and fix whatever it now reports. The snapshot is
the gate's source of truth precisely so a release cannot quietly falsify a doc.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "testdata/runpodctl/command-surface.json"
# Deprecated paths cobra hides from --help but still serves. Absence claims about them
# would be wrong too, so they are part of the surface.
HIDDEN = ["get pod", "get cloud", "create pod", "remove pod", "exec", "project", "config"]


def run(binp: str, path: str, *extra: str) -> str:
    return subprocess.run([binp] + path.split() + list(extra),
                          capture_output=True, text=True).stdout


def subcommands(binp: str, path: str) -> list[str]:
    out, seen, found = run(binp, path, "--help"), False, []
    for ln in out.splitlines():
        if ln.startswith("Available Commands:"):
            seen = True
            continue
        if seen and ln.startswith(("Flags:", "Global Flags:")):
            break
        if seen:
            m = re.match(r"\s+(\S+)\s", ln)
            if m and m.group(1) not in ("help", "completion"):
                found.append(m.group(1))
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", default="runpodctl")
    args = ap.parse_args()
    version = run(args.bin, "version").strip()
    if not version:
        print(f"could not run {args.bin!r}", file=sys.stderr)
        return 1

    cmds: dict[str, dict] = {}
    for top in subcommands(args.bin, ""):
        for path in [top] + [f"{top} {s}" for s in subcommands(args.bin, top)]:
            out = run(args.bin, path, "--help")
            alias = re.search(r"Aliases:\n\s+(.+)", out)
            cmds[path] = {
                "flags": sorted(set(re.findall(r"(--[a-z][a-z0-9-]+)", out))),
                "aliases": [a.strip() for a in alias.group(1).split(",")] if alias else [],
            }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "_comment": "Vendored runpodctl command surface. Regenerate with "
                    "hooks/gen_cli_surface.py against a released binary. "
                    "Gates hooks/check_cli_absence_claims.py.",
        "version": version,
        "hidden_commands": HIDDEN,
        "commands": cmds,
    }, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} — {version}, {len(cmds)} commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
