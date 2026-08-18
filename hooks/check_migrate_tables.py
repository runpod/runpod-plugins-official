#!/usr/bin/env python3
"""Diff the runpod-migrate reference tables against the v2 OpenAPI spec.

The skill's reference/ docs assert concrete v2 paths. They carry a
verification date because they go stale — this makes that detectable
mechanically instead of by re-reading 1,200 lines of markdown.

    python3 hooks/check_migrate_tables.py          # vendored snapshot (CI gate)
    python3 hooks/check_migrate_tables.py --live   # live API (drift job)

Exit 1 if any claimed path/method is absent from the spec.
"""
from __future__ import annotations
import argparse, json, re, sys, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILL = ROOT / "plugins/runpod/skills/runpod-migrate"
DEFAULT_SPEC = ROOT / "testdata/runpod-migrate/v2-openapi.json"
LIVE_SPEC_URL = "https://api.runpod.io/v2/openapi.json"

METHODS = {"GET", "POST", "PATCH", "PUT", "DELETE"}
# `GET /v2/pods/{id}` and `POST /v2/pods/{id}/action` inside backticks. The mapping
# tables abbreviate a shared prefix as `\u2026/v2/templates`, so allow a leading ellipsis
# \u2014 without it those rows are silently never checked.
CLAIM = re.compile(
    r"`\s*(GET|POST|PATCH|PUT|DELETE)\s+(?:[A-Za-z0-9._-]*\u2026)?(/v2/[A-Za-z0-9/_{}.-]*)"
)


# Many table rows name a path with no method at all — `…/v2/network-volumes`,
# `/v2/catalog/gpus`. Those are claims too, and the method-bearing regex above skips
# them, so they are collected and checked for existence separately.
BARE_PATH = re.compile(r"`[^`]*?(/v2/[A-Za-z0-9/_{}-]*)[^`]*`")

# A path-only mention is not always an assertion that the path exists: the docs also
# name paths as counter-examples, and some real URLs are not `paths` entries. Absence
# from the spec is expected for these, so each needs a reason rather than a heuristic
# — a heuristic would let a genuinely stale row hide behind it.
EXPECTED_ABSENT = {
    "/v2": "the base URL, not an operation",
    "/v2/openapi": "/v2/openapi.json is the spec document itself, not a path in it",
    "/v2/networkvolumes": "cited as the 404 that /v2/network-volumes replaced",
    "/v2/{}/run": "the job API on api.runpod.ai, a different host from the control plane",
}


def fetch_live() -> Path:
    """Download the live spec to a temp file. Used by the scheduled drift job."""
    import tempfile, urllib.request
    with urllib.request.urlopen(LIVE_SPEC_URL, timeout=30) as r:
        body = r.read()
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_bytes(body)
    return tmp


def normalise(path: str) -> str:
    """Collapse param names so {id} and {podId} compare equal."""
    path = re.sub(r"\{[^}]+\}", "{}", path.rstrip("/"))
    return path or "/"


def load_spec(p: Path):
    doc = json.loads(p.read_text())
    ops = collections.defaultdict(set)
    for raw, item in (doc.get("paths") or {}).items():
        for method in item:
            if method.upper() in METHODS:
                ops[normalise(raw)].add(method.upper())
    return ops, doc


def extract_claims(skill_dir: Path):
    claims = collections.defaultdict(list)  # (method, npath) -> [locations]
    bare = collections.defaultdict(list)    # npath -> [locations]
    files = sorted(skill_dir.rglob("*.md"))
    for f in files:
        for lineno, line in enumerate(f.read_text().splitlines(), 1):
            loc = f"{f.relative_to(skill_dir)}:{lineno}"
            methodful = set()
            for method, path in CLAIM.findall(line):
                npath = normalise(path)
                methodful.add(npath)
                claims[(method, npath)].append(loc)
            for path in BARE_PATH.findall(line):
                npath = normalise(path)
                if npath not in methodful:
                    bare[npath].append(loc)
    return claims, bare, files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    ap.add_argument("--spec", type=Path, default=DEFAULT_SPEC,
                    help="OpenAPI document (default: the vendored snapshot)")
    ap.add_argument("--live", action="store_true",
                    help=f"fetch {LIVE_SPEC_URL} instead of using --spec")
    ap.add_argument("--show-uncovered", action="store_true",
                    help="also list spec operations the docs never mention")
    a = ap.parse_args()

    if a.live:
        a.spec = fetch_live()
    ops, doc = load_spec(a.spec)
    claims, bare, files = extract_claims(a.skill)

    title = (doc.get("info") or {}).get("title", "?")
    version = (doc.get("info") or {}).get("version", "?")
    print(f"spec:   {a.spec}  ({title} {version}) — {len(ops)} paths")
    print(f"skill:  {a.skill}  — {len(files)} markdown files, "
          f"{len(claims)} method+path claims, {len(bare)} path-only claims\n")

    bad_path, bad_method = [], []
    for (method, npath), locs in sorted(claims.items()):
        if npath not in ops:
            bad_path.append((method, npath, locs))
        elif method not in ops[npath]:
            bad_method.append((method, npath, sorted(ops[npath]), locs))

    if bad_path:
        print(f"## PATH NOT IN SPEC ({len(bad_path)})")
        for m, p, locs in bad_path:
            print(f"  {m:6} {p}")
            for l in locs:
                print(f"         {l}")
        print()
    if bad_method:
        print(f"## METHOD NOT ALLOWED ON THAT PATH ({len(bad_method)})")
        for m, p, allowed, locs in bad_method:
            print(f"  {m:6} {p}   spec allows: {', '.join(allowed)}")
            for l in locs:
                print(f"         {l}")
        print()

    bad_bare = [(p, locs) for p, locs in sorted(bare.items())
                if p not in ops and p not in EXPECTED_ABSENT]
    if bad_bare:
        print(f"## PATH-ONLY CLAIM NOT IN SPEC ({len(bad_bare)})")
        for p, locs in bad_bare:
            print(f"  {p}")
            for l in locs:
                print(f"         {l}")
        print()

    if a.show_uncovered:
        claimed = {p for _, p in claims} | set(bare)
        uncovered = sorted(p for p in ops if p not in claimed)
        print(f"## SPEC PATHS THE DOCS NEVER MENTION ({len(uncovered)})")
        for p in uncovered:
            print(f"  {', '.join(sorted(ops[p])):22} {p}")
        print()

    stale_allow = sorted(p for p in EXPECTED_ABSENT if p in ops)
    if stale_allow:
        print(f"## EXPECTED_ABSENT ENTRIES THAT NOW EXIST ({len(stale_allow)})")
        print("   The spec gained these; drop them from the allowlist so they are checked.")
        for p in stale_allow:
            print(f"  {p}   {EXPECTED_ABSENT[p]}")
        print()

    total = len(claims) + len(bare)
    ok = total - len(bad_path) - len(bad_method) - len(bad_bare) - len(EXPECTED_ABSENT)
    print(f"verified {ok}/{total} claims  "
          f"({len(bad_path) + len(bad_bare)} unknown path, {len(bad_method)} wrong method)")
    return 1 if (bad_path or bad_method or bad_bare or stale_allow) else 0


if __name__ == "__main__":
    sys.exit(main())
