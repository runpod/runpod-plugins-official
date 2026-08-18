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


# `?include=AVAILABILITY&product=POD` in a documented URL. Query parameters were the
# blind spot that let the docs teach a call that 400s in 17 places while this check
# stayed green: paths were verified, everything after the `?` was not.
QUERY_CALL = re.compile(r"(/v2/[A-Za-z0-9/_{}.-]*)\?([A-Za-z0-9_]+=[^\s`'\")]*)")
# Spec descriptions state co-requirements in prose: "Required with include=AVAILABILITY".
# Deriving the pairs from that text rather than hardcoding them means a new requirement
# starts being enforced as soon as the spec documents it.
REQUIRED_WITH = re.compile(r"[Rr]equired with[ `]+([A-Za-z0-9_]+)=([A-Za-z0-9_]+)")


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


def load_query_params(doc):
    """path -> {param: description}, plus the derived required-with pairs."""
    params = doc.get("components", {}).get("parameters", {})
    per_path, pairs = {}, {}
    for raw, item in (doc.get("paths") or {}).items():
        known = {}
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            for prm in op.get("parameters", []) or []:
                if "$ref" in prm:
                    prm = params.get(prm["$ref"].split("/")[-1], {})
                if prm.get("in") == "query" and prm.get("name"):
                    desc = prm.get("description", "") or ""
                    known[prm["name"]] = desc
                    m = REQUIRED_WITH.search(desc)
                    if m:
                        pairs[(normalise(raw), m.group(1), m.group(2))] = prm["name"]
        per_path[normalise(raw)] = known
    return per_path, pairs


def extract_query_calls(skill_dir: Path):
    """(npath, {param: value}) -> [locations] for every documented URL with a query."""
    calls = collections.defaultdict(list)
    for f in sorted(skill_dir.rglob("*.md")):
        for lineno, line in enumerate(f.read_text().splitlines(), 1):
            for path, query in QUERY_CALL.findall(line):
                kv = {}
                for part in query.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        kv[k] = v
                key = (normalise(path), tuple(sorted(kv.items())))
                calls[key].append(f"{f.relative_to(skill_dir)}:{lineno}")
    return calls


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

    # ---- query parameters -------------------------------------------------
    qp_per_path, required_pairs = load_query_params(doc)
    calls = extract_query_calls(a.skill)
    bad_param, missing_pair = [], []
    for (npath, kv), locs in sorted(calls.items()):
        known = qp_per_path.get(npath)
        if known is None:
            continue  # unknown path already reported above
        sent = dict(kv)
        for name in sent:
            if name not in known:
                bad_param.append((npath, name, sorted(known), locs))
        for (ppath, trigger, value), needed in required_pairs.items():
            if ppath == npath and sent.get(trigger) == value and needed not in sent:
                missing_pair.append((npath, f"{trigger}={value}", needed, locs))

    if bad_param:
        print(f"## QUERY PARAM NOT ON THAT PATH ({len(bad_param)})")
        for npath, name, known, locs in bad_param:
            print(f"  {npath}?{name}=...   spec allows: {', '.join(known) or '(none)'}")
            for l in locs:
                print(f"         {l}")
        print()
    if missing_pair:
        print(f"## REQUIRED COMPANION PARAM MISSING ({len(missing_pair)})")
        print("   The spec marks these required together \u2014 the documented call is a 400.")
        for npath, trigger, needed, locs in missing_pair:
            print(f"  {npath}?{trigger}   requires: {needed}")
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
    print(f"verified {ok}/{total} claims and {len(calls)} query-bearing calls  "
          f"({len(bad_path) + len(bad_bare)} unknown path, {len(bad_method)} wrong method, "
          f"{len(bad_param)} unknown param, {len(missing_pair)} missing companion)")
    return 1 if (bad_path or bad_method or bad_bare or stale_allow
                 or bad_param or missing_pair) else 0


if __name__ == "__main__":
    sys.exit(main())
