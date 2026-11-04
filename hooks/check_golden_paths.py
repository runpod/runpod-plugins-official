#!/usr/bin/env python3
"""Check that every golden path carries one honest, consistent status and its evals.

Each golden-path doc (plugins/runpod/skills/runpod/golden-paths/**/*.md, except the
index README and the files a path ships as a project template) must have:

- frontmatter `status`: live-verified | spec-checked | legacy, `verified`: a
  YYYY-MM-DD date (for legacy, the last live run), and `evals`: a list whose entries are
  `<skill>/evals/<name>` (an existing <name>.eval.md) or `live:<id>` (an id in
  CHECK_IDS of scripts/live_free_evals.py). An empty list is allowed only with a reason
  in the `> **Status:**` line ("none (...)").
- a `> **Status:** <label> — ...` line directly under the title, where <label> is
  "live-verified DATE", "spec-checked DATE" or "legacy (last live run DATE)".
- a row in golden-paths/README.md whose Status cell starts with the same label.

Run from the repo root: python3 hooks/check_golden_paths.py [--self-test]
"""

from __future__ import annotations

import datetime
import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/runpod/skills"
GP_DIR = SKILLS / "runpod/golden-paths"
LIVE = ROOT / "scripts/live_free_evals.py"
STATUSES = ("live-verified", "spec-checked", "legacy")
# Files a path ships as its deliverable (a project template), not golden-path docs.
EXCLUDE = re.compile(r"^26-template-project/template/")


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out: dict[str, str] = {}
    for line in (m.group(1) if m else "").splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip("\"'")
    return out


def is_date(s: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return False
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def label(status: str, date: str) -> str:
    return f"legacy (last live run {date})" if status == "legacy" else f"{status} {date}"


def live_ids(source: str) -> set[str]:
    m = re.search(r"CHECK_IDS = \((.*?)\)", source, re.S)
    return set(re.findall(r'"([a-z0-9-]+)"', m.group(1))) if m else set()


def problems_for(
    rel: str, text: str, readme: str, ids: set[str], exists: Callable[[str], bool]
) -> list[str]:
    fm = frontmatter(text)
    status, date, evals = fm.get("status", ""), fm.get("verified", ""), fm.get("evals", "")
    out = []
    if status not in STATUSES:
        return [f"{rel}: frontmatter status {status!r} is not one of {', '.join(STATUSES)}"]
    if not is_date(date):
        out.append(f"{rel}: frontmatter verified {date!r} is not a YYYY-MM-DD date")
    m = re.fullmatch(r"\[(.*)\]", evals)
    if not m:
        out.append(f"{rel}: frontmatter evals must be an inline [a, b] list on one line")
        items = []
    else:
        items = [e.strip() for e in m.group(1).split(",") if e.strip()]
    for e in items:
        if e.startswith("live:"):
            if e[5:] not in ids:
                out.append(
                    f"{rel}: eval {e} is not a CHECK_IDS entry in scripts/live_free_evals.py"
                )
        elif not re.fullmatch(r"[a-z0-9-]+/evals/[a-z0-9-]+", e) or not exists(e + ".eval.md"):
            out.append(f"{rel}: eval {e} is not an existing <skill>/evals/<name>.eval.md")
    want = label(status, date)
    body = text[text.index("\n---\n", 4) + 5 :] if text.startswith("---\n") else text
    head = re.search(r"^# .+\n\n> \*\*Status:\*\* (.+)$", body, re.M)
    if not head or not head.group(1).startswith(want + " — "):
        out.append(f"{rel}: no '> **Status:** {want} — ...' line directly under the title")
    elif not items and "**Evals:** none (" not in head.group(1):
        out.append(f"{rel}: empty evals needs a reason: '**Evals:** none (why)'")
    elif items and "**Evals:** none (" in head.group(1):
        out.append(f"{rel}: frontmatter lists evals but the Status line says '**Evals:** none'")
    row = re.search(
        r"^\|[^|\n]*\|[^|\n]*\]\(" + re.escape(rel) + r"\)[^\n]*\| ([^|\n]+) \|$", readme, re.M
    )
    if not row:
        out.append(f"{rel}: no row in golden-paths/README.md")
    elif not row.group(1).startswith(want):
        out.append(f"{rel}: README status {row.group(1)!r} does not start with {want!r}")
    return out


def self_test() -> None:
    good = (
        "---\nlanes: [rest]\nmcp: full\nconcepts: [pod]\nstatus: live-verified\n"
        'verified: "2026-10-29"\nevals: [runpod/evals/x, live:catalog]\n---\n\n# GP\n\n'
        "> **Status:** live-verified 2026-10-29 — ran. **Evals:** x.\n"
    )
    readme = "| 01 | [GP](01.md) | k | a | live-verified 2026-10-29 |"

    def ok(p: str) -> bool:
        return p == "runpod/evals/x.eval.md"

    assert problems_for("01.md", good, readme, {"catalog"}, ok) == []
    assert problems_for(
        "01.md", good.replace("live-verified\n", "covered\n"), readme, {"catalog"}, ok
    )
    assert problems_for("01.md", good, readme, set(), ok)
    assert problems_for("01.md", good, readme.replace("10-29", "07-01"), {"catalog"}, ok)
    assert problems_for(
        "01.md", good.replace("[runpod/evals/x, live:catalog]", "[]"), readme, {"catalog"}, ok
    )
    legacy = good.replace("status: live-verified", "status: legacy").replace(
        "live-verified 2026-10-29 —", "legacy (last live run 2026-10-29) —"
    )
    assert (
        problems_for(
            "01.md",
            legacy,
            readme.replace("live-verified 2026-10-29", "legacy (last live run 2026-10-29)"),
            {"catalog"},
            ok,
        )
        == []
    )
    assert problems_for(
        "01.md", good.replace('"2026-10-29"', '"2026-13-45"'), readme, {"catalog"}, ok
    )
    assert problems_for(
        "01.md", good.replace(" **Evals:** x.", " **Evals:** none (x)."), readme, {"catalog"}, ok
    )
    print("golden-path status self-test OK")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    readme = (GP_DIR / "README.md").read_text()
    ids = live_ids(LIVE.read_text())

    def exists(p: str) -> bool:
        return (SKILLS / p).is_file()

    errors, n = [], 0
    for md in sorted(GP_DIR.rglob("*.md")):
        rel = md.relative_to(GP_DIR).as_posix()
        if rel == "README.md" or EXCLUDE.match(rel):
            continue
        n += 1
        errors += problems_for(rel, md.read_text(), readme, ids, exists)
    if errors:
        print(f"golden-path status FAILED: {len(errors)} problem(s)")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    print(f"golden-path status OK ({n} paths)")


if __name__ == "__main__":
    main()
