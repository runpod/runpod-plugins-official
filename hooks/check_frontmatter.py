#!/usr/bin/env python3
"""Verify every YAML frontmatter block under plugins/ parses to a mapping.

The plugin directory blocks a version whose skill or command frontmatter does not
parse (`Frontmatter couldn't be parsed`), and `claude plugin validate --strict` does
not catch it. The usual cause is an unquoted value YAML reads as something else,
e.g. `argument-hint: [scope] [path]` — two bracketed groups on one line. Quote it.

Needs PyYAML (CI installs a pinned copy): pip install pyyaml
Run from the repo root: python3 hooks/check_frontmatter.py [--self-test]
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    yaml = importlib.import_module("yaml")
except ModuleNotFoundError:
    print("check_frontmatter needs PyYAML: pip install pyyaml")
    sys.exit(2)


def frontmatter(text: str) -> str | None:
    """Return the block between the opening and closing `---`, or None if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:i])
    return ""  # opened but never closed: let the parse below report it


def problem(block: str) -> str | None:
    """Return why the block is invalid, or None when it parses to a mapping."""
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        return str(e).replace("\n", " ")
    if not isinstance(data, dict):
        return f"parses to {type(data).__name__}, not a key: value mapping"
    return None


def self_test() -> None:
    bad = "description: x\nargument-hint: [scope: all | rest] [path]"
    good = 'description: x\nargument-hint: "[scope: all | rest] [path]"'
    assert problem(bad) is not None, "unquoted double-bracket value should fail"
    assert problem(good) is None, "quoted value should pass"
    assert frontmatter("---\na: 1\n---\nbody") == "a: 1"
    assert frontmatter("# no frontmatter") is None
    print("frontmatter self-test OK")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    bad: list[tuple[Path, str]] = []
    checked = 0
    for md in sorted((ROOT / "plugins").rglob("*.md")):
        block = frontmatter(md.read_text(errors="replace"))
        if block is None:
            continue
        checked += 1
        why = problem(block) if block else "no closing --- line"
        if why:
            bad.append((md.relative_to(ROOT), why))
    if bad:
        print(f"frontmatter check FAILED — {len(bad)} file(s):")
        for path, why in bad:
            print(f"  {path}: {why}")
        print("Quote values containing [ ] : # | > or a leading * & ! %.")
        sys.exit(1)
    print(f"frontmatter OK ({checked} files)")


if __name__ == "__main__":
    main()
