#!/usr/bin/env python3
"""Validate every golden path's skill.json before the Runpod backend syncs it.

The backend mirrors each `golden-paths/<folder>/skill.json` into its database twice a
day and skips any file it rejects, so a bad file silently keeps the Hub on the last good
copy. This check fails the build on what the sync would reject:

- the file does not match `golden-paths/skill.schema.json`;
- `id` is not the folder name (the backend keys rows on it);
- more than one variant is marked `default` (JSON Schema cannot express this);
- a `skill`, variant or supplemental URL does not point at a file in this repo.

Needs jsonschema with its format validators (CI installs a pinned copy):
  pip install 'jsonschema[format-nongpl]'
Run from the repo root: python3 hooks/check_skill_json.py [--self-test]
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATHS = ROOT / "plugins/runpod/skills/runpod/golden-paths"
SCHEMA_PATH = GOLDEN_PATHS / "skill.schema.json"
RAW_PREFIX = "https://raw.githubusercontent.com/runpod/runpod-plugins-official/main/"

try:
    jsonschema = importlib.import_module("jsonschema")
except ModuleNotFoundError:
    print("check_skill_json needs jsonschema: pip install 'jsonschema[format-nongpl]'")
    sys.exit(2)


class Validator(Protocol):
    def iter_errors(self, instance: object) -> Iterable[Any]: ...


def validator() -> Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    check: Validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
    )
    return check


def problems(data: object, folder: str, check: Validator) -> list[str]:
    """Every reason the backend sync would reject this skill.json."""
    found = [
        f"{'/'.join(str(p) for p in error.absolute_path) or '(root)'}: {error.message}"
        for error in sorted(check.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]
    if found or not isinstance(data, dict):
        return found

    if data["id"] != folder:
        found.append(f"id: {data['id']!r} must equal the folder name {folder!r}")

    defaults = [v["id"] for v in data.get("variants", []) if v.get("default")]
    if len(defaults) > 1:
        found.append(f"variants: only one may be default, found {', '.join(defaults)}")

    urls = [("skill", data["skill"])]
    urls += [(f"variants/{v['id']}", v["url"]) for v in data.get("variants", [])]
    urls += [
        (f"supplementalSkills/{s['name']}", s["url"]) for s in data.get("supplementalSkills", [])
    ]
    for where, url in urls:
        if not url.startswith(RAW_PREFIX):
            found.append(f"{where}: {url} is not on this repo's main branch")
        elif not (ROOT / url[len(RAW_PREFIX) :]).is_file():
            found.append(f"{where}: {url[len(RAW_PREFIX) :]} does not exist in this repo")
    return found


def self_test() -> None:
    check = validator()
    folder = "02-comfyui-pod"
    base = f"{RAW_PREFIX}plugins/runpod/skills/runpod/golden-paths/{folder}/"
    variant: dict[str, object] = {
        "id": "variant-b-prebuilt",
        "name": "B",
        "url": base + "variant-b-prebuilt.md",
        "default": True,
    }
    good: dict[str, object] = {
        "id": folder,
        "name": "ComfyUI",
        "description": "x",
        "skill": base + "README.md",
        "variants": [variant],
        "tags": ["comfyui"],
        "createdAt": "2026-07-14T21:20:11Z",
        "updatedAt": "2026-10-13T14:51:26Z",
    }
    assert problems(good, folder, check) == [], problems(good, folder, check)

    def fails(change: dict[str, object], expect: str) -> None:
        found = problems({**good, **change}, folder, check)
        assert any(expect in p for p in found), f"expected {expect!r} in {found}"

    # A missing format validator makes jsonschema skip the check silently; this catches that.
    fails({"updatedAt": "yesterday"}, "date-time")
    fails({"extra": 1}, "Additional properties")
    fails({"tags": ["Image Gen"]}, "does not match")
    fails({"id": "03-other"}, "folder name")
    fails({"skill": base + "MISSING.md"}, "does not exist")
    fails({"variants": [variant, {**variant, "id": "variant-a"}]}, "only one may be default")
    print("skill.json self-test OK")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return

    check = validator()
    files = sorted(GOLDEN_PATHS.glob("*/skill.json"))
    failed = False
    for path in files:
        rel = path.relative_to(ROOT)
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"{rel}: not valid JSON: {e}")
            failed = True
            continue
        for problem in problems(data, path.parent.name, check):
            print(f"{rel}: {problem}")
            failed = True

    if failed:
        sys.exit(1)
    print(f"skill.json OK ({len(files)} file{'s' if len(files) != 1 else ''})")


if __name__ == "__main__":
    main()
