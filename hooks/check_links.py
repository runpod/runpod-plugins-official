#!/usr/bin/env python3
"""Verify every relative Markdown link in the repo resolves — path AND #anchor.

Skips http(s)/mailto links. For a link with a #fragment into a Markdown file
(or a bare #fragment within the same file), verifies the fragment matches a
heading, using GitHub's slug rules. Run from the repo root: python3 hooks/check_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def slug(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)  # drop punctuation except word/space/hyphen
    return s.replace(" ", "-")


def slugs_for(path: Path) -> set[str]:
    out: set[str] = set()
    try:
        for line in path.read_text(errors="replace").splitlines():
            m = HEADING.match(line)
            if m:
                out.add(slug(m.group(1)))
    except OSError:
        pass
    return out


bad: list[tuple[Path, int, str, str]] = []
for md in ROOT.rglob("*.md"):
    if ".git" in md.parts or "node_modules" in md.parts:
        continue
    d = md.parent
    for line_no, line in enumerate(md.read_text(errors="replace").splitlines(), 1):
        for m in LINK.finditer(line):
            link = m.group(1).strip()
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, _, frag = link.partition("#")
            target = md if path_part == "" else (d / path_part).resolve()
            if path_part and not target.exists():
                bad.append((md.relative_to(ROOT), line_no, link, "missing file"))
                continue
            if frag and target.suffix == ".md" and slug(frag) not in slugs_for(target):
                bad.append((md.relative_to(ROOT), line_no, link, "missing anchor"))

if bad:
    print("link check FAILED:")
    for path, ln, link, why in bad:
        print(f"  - {path}:{ln}  ->  {link}   ({why})")
    sys.exit(1)

print("link check OK")
