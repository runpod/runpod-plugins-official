#!/usr/bin/env python3
"""Check runpod-migrate's Class-3 "capability removed" table against the v2 spec.

Class 3 in reference/breaking-changes.md is headed:

    Capability removed: no v2 equivalent at any price

so every identifier named in that table is an assertion of ABSENCE. This checks
each one and reports any that still exist. No natural-language parsing of the
"Status in v2" column is needed — existence alone falsifies the row.

Why this matters more than the other tables: SKILL.md step 3 tells the agent to
STOP AND ASK the user when their code depends on a Class-3 capability. A row
that is wrong does not produce a 422 anyone sees — it produces an interruption
about a decision that does not exist, followed by a deliberate workaround.

    python3 hooks/check_migrate_class3.py          # vendored snapshot (CI gate)
    python3 hooks/check_migrate_class3.py --live   # live API (drift job)

Exit 1 if any Class-3 identifier is present in v2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

type JSONValue = bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILL = ROOT / "plugins/runpod/skills/runpod-migrate"
DEFAULT_SPEC = ROOT / "testdata/runpod-migrate/v2-openapi.json"
LIVE_SPEC_URL = "https://api.runpod.io/v2/openapi.json"

# A Class-3 row asserts a capability is gone from *writes*. An identifier that survives
# only as a read filter does not falsify that, so query-parameter-only survivals are
# reported as a separate, non-failing note — the row is still true, it is just less
# complete than it could be. Only request-body fields and routes fail the check.
# GraphQL-only identifiers: operation/selection names that would never appear in
# a REST spec. Their absence proves nothing, so they are reported as unchecked
# rather than silently counted as verified.
GRAPHQL_ONLY = re.compile(r"^(myself|pod(Rent|Bid)\w*|machine\s*\{|.*\{.*)$|.*\(.*\)$")
# Tokens that are prose or types, not field names.
NOT_A_FIELD = {"true", "false", "null", "array", "string", "none", "n/a"}


def as_obj(value: JSONValue) -> dict[str, JSONValue]:
    """Return `value` if it is a JSON object, else an empty object."""
    return value if isinstance(value, dict) else {}


def ref_target(val: JSONValue) -> str | None:
    """The schema name a property value references, via $ref, allOf[0].$ref, or items.$ref."""
    if not isinstance(val, dict):
        return None
    ref = val.get("$ref")
    if isinstance(ref, str):
        return ref.split("/")[-1]
    all_of = val.get("allOf")
    if isinstance(all_of, list) and all_of and isinstance(all_of[0], dict):
        first_ref = all_of[0].get("$ref")
        if isinstance(first_ref, str):
            return first_ref.split("/")[-1]
    if val.get("type") == "array":
        items = val.get("items")
        if isinstance(items, dict):
            items_ref = items.get("$ref")
            if isinstance(items_ref, str):
                return items_ref.split("/")[-1]
    return None


def fetch_live() -> Path:
    """Download the live spec to a temp file. Used by the scheduled drift job."""
    import tempfile
    import urllib.parse
    import urllib.request

    if urllib.parse.urlsplit(LIVE_SPEC_URL).scheme not in ("http", "https"):
        raise ValueError(f"refusing to fetch non-http(s) URL: {LIVE_SPEC_URL!r}")
    with urllib.request.build_opener().open(LIVE_SPEC_URL, timeout=30) as r:
        body = r.read()
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_bytes(body)
    return tmp


def load_spec(
    path: Path,
) -> tuple[dict[str, set[str]], set[str], dict[str, JSONValue], list[str]]:
    doc: dict[str, JSONValue] = json.loads(path.read_text())
    schemas = as_obj(as_obj(doc.get("components")).get("schemas"))

    def merge(
        node: JSONValue, acc: dict[str, JSONValue] | None = None, depth: int = 0
    ) -> dict[str, JSONValue]:
        acc = acc if acc is not None else {}
        if depth > 6 or not isinstance(node, dict):
            return acc
        ref = node.get("$ref")
        if isinstance(ref, str):
            return merge(schemas.get(ref.split("/")[-1]), acc, depth + 1)
        all_of = node.get("allOf")
        if isinstance(all_of, list):
            for sub in all_of:
                merge(sub, acc, depth + 1)
        props = node.get("properties")
        if isinstance(props, dict):
            acc.update(props)
        return acc

    def flatten(name: str, depth: int = 0, seen: frozenset[str] | None = None) -> set[str]:
        """All field names reachable in a schema, nested included."""
        seen = seen if seen is not None else frozenset()
        out: set[str] = set()
        if depth > 4 or name not in schemas or name in seen:
            return out
        seen = seen | {name}
        for key, val in merge(schemas[name]).items():
            out.add(key)
            ref = ref_target(val)
            if ref:
                out |= flatten(ref, depth + 1, seen)
        return out

    request_fields: dict[str, set[str]] = {}
    for name in schemas:
        if re.match(r"^(Create|Update)\w+Request$", name):
            request_fields[name] = flatten(name)

    params = as_obj(as_obj(doc.get("components")).get("parameters"))
    query_params: set[str] = set()
    for item in as_obj(doc.get("paths")).values():
        for op in as_obj(item).values():
            if not isinstance(op, dict):
                continue
            raw_params = op.get("parameters")
            for raw_prm in raw_params if isinstance(raw_params, list) else []:
                if not isinstance(raw_prm, dict):
                    continue
                prm = raw_prm
                if "$ref" in prm:
                    ref = prm.get("$ref")
                    prm = as_obj(params.get(ref.split("/")[-1])) if isinstance(ref, str) else {}
                pname = prm.get("name")
                if prm.get("in") == "query" and isinstance(pname, str) and pname:
                    query_params.add(pname)

    enums: dict[str, JSONValue] = {
        n: s["enum"] for n, s in schemas.items() if isinstance(s, dict) and s.get("enum")
    }
    return request_fields, query_params, enums, sorted(as_obj(doc.get("paths")))


def parse_class3(md: Path) -> list[tuple[str, list[str], str]]:
    """Yield (capability, [identifiers], status_text) for each Class-3 row."""
    lines = md.read_text().splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## Class 3")), None)
    if start is None:
        return []
    rows: list[tuple[str, list[str], str]] = []
    for line in lines[start + 1 :]:
        if line.startswith(("## ", "### ")):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", " "} or cells[0].lower() == "capability":
            continue
        cap = re.sub(r"\*\*", "", cells[0])
        idents = list(re.findall(r"`([^`]+)`", cells[1]))
        rows.append((cap, idents, cells[2]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    ap.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC,
        help="OpenAPI document (default: the vendored snapshot)",
    )
    ap.add_argument(
        "--live", action="store_true", help=f"fetch {LIVE_SPEC_URL} instead of using --spec"
    )
    a = ap.parse_args()

    if a.live:
        a.spec = fetch_live()

    md = a.skill / "reference" / "breaking-changes.md"
    if not md.exists():
        print(f"not found: {md}", file=sys.stderr)
        return 2

    req_fields, qparams, _enums, paths = load_spec(a.spec)
    rows = parse_class3(md)
    print(f"spec:  {a.spec} — {len(req_fields)} request schemas, {len(qparams)} query params")
    print(f"table: {md.name} Class 3 — {len(rows)} rows\n")

    violations: list[tuple[str, list[str], str]] = []
    unchecked: list[tuple[str, list[str]]] = []
    ok: list[str] = []
    read_only: list[tuple[str, list[str]]] = []
    for cap, idents, status in rows:
        found: list[str] = []
        skipped: list[str] = []
        reads: list[str] = []
        for ident in idents:
            tok = ident.strip()
            kind = "field"

            # `?desiredStatus=` / `?includeMachine=` -> query parameter name
            if tok.startswith("?"):
                tok, kind = tok.lstrip("?").rstrip("=").strip(), "query"
            # `POST /pods/{id}/reset` -> route
            elif re.match(r"^(GET|POST|PATCH|PUT|DELETE)\s+/", tok):
                route = tok.split(None, 1)[1]
                norm = re.sub(r"\{[^}]+\}", "{}", route.strip().rstrip("/"))
                if not norm.startswith("/v2"):
                    norm = "/v2" + norm
                if norm in {re.sub(r"\{[^}]+\}", "{}", p2.rstrip("/")) for p2 in paths}:
                    found.append(f"{tok} → route exists")
                continue
            # `gpuTypeIds: [a, b, c]` / `interruptible: true` -> field name
            elif ":" in tok:
                tok = tok.split(":", 1)[0].strip()

            if tok.lower() in NOT_A_FIELD or not tok:
                continue
            if GRAPHQL_ONLY.match(tok) or " " in tok or "/" in tok:
                skipped.append(ident.strip())
                continue

            if kind == "query":
                if tok in qparams:
                    reads.append(f"{tok} → query parameter")
                continue
            where = [s for s, fields in req_fields.items() if tok in fields]
            if where:
                found.append(f"{tok} → {', '.join(sorted(where))}")
            elif tok in qparams:
                reads.append(f"{tok} → query parameter (read filter only)")
        checkable = [
            t for t in idents if t.strip() not in skipped and t.strip().lower() not in NOT_A_FIELD
        ]
        if reads:
            read_only.append((cap, reads))
        if found:
            violations.append((cap, found, status))
        elif not idents:
            # No backticked identifier at all — e.g. "create/update CPU endpoints".
            # Nothing was checked, so this must NOT be reported as verified.
            unchecked.append((cap, ["<no identifier in the table cell>"]))
        elif skipped and not checkable:
            unchecked.append((cap, skipped))
        else:
            ok.append(cap)

    if violations:
        print(f"## CLASS-3 ROWS THAT ARE WRONG — capability still exists ({len(violations)})\n")
        for cap, found, status in violations:
            print(f"  {cap}")
            print(f"    table says: {status[:96]}")
            for f in found:
                print(f"    STILL EXISTS: {f}")
            print()

    if read_only:
        print(f"## SURVIVES AS A READ FILTER ONLY ({len(read_only)}) — row still true, note it\n")
        for cap, reads in read_only:
            print(f"  {cap}: {', '.join(reads)}")
        print()

    if unchecked:
        print(f"## NOT MECHANICALLY CHECKABLE ({len(unchecked)}) — GraphQL-only, verify by hand\n")
        for cap, sk in unchecked:
            print(f"  {cap}: {', '.join(sk)}")
        print()

    print(
        f"verified absent: {len(ok)}/{len(rows)} rows"
        f"   wrong: {len(violations)}   read-filter-only: {len(read_only)}"
        f"   unchecked: {len(unchecked)}"
    )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
