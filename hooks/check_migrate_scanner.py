#!/usr/bin/env python3
"""Regression gate for the runpod-migrate inventory scanner.

Runs `rp_api_inventory.py` against the corpora in `testdata/runpod-migrate/` and
asserts what it must and must not report. The signal table is 60+ interacting
regexes with `unless` clauses, so a one-line change there can quietly break a
distant case — every assertion below exists because something actually broke.

    python3 hooks/check_migrate_scanner.py

Exit 0 when every corpus matches, 1 otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "plugins/runpod/skills/runpod-migrate/scripts/rp_api_inventory.py"
CORPORA = ROOT / "testdata/runpod-migrate"


def scan(corpus: str, *args: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(SCANNER), str(CORPORA / corpus), "--json", *args],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def exit_code(corpus: str, *args: str) -> int:
    return subprocess.run(
        [sys.executable, str(SCANNER), str(CORPORA / corpus), *args],
        capture_output=True, text=True,
    ).returncode


failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        failures.append(f"{label}" + (f"\n      {detail}" if detail else ""))
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")


def main() -> int:
    if not SCANNER.exists():
        print(f"scanner not found: {SCANNER}", file=sys.stderr)
        return 1
    if not CORPORA.is_dir():
        print(f"corpora not found: {CORPORA}", file=sys.stderr)
        return 1

    # ---- 1. a mixed v1 + GraphQL repo ------------------------------------
    print("v1-graphql-mixed")
    d = scan("v1-graphql-mixed")
    plan = set(d["files_needing_migration"])
    check("all four legacy files are planned",
          plan == {"dashboard/capacity.js", "dashboard/provision.js",
                   "gpu_farm/endpoints.py", "gpu_farm/runpod_client.py"},
          f"got {sorted(plan)}")
    # provision.js contains no "runpod" string — only GraphQL operation names.
    # A hand-written whole-file prefilter once skipped it entirely.
    check("provision.js is found despite containing no 'runpod' string",
          "dashboard/provision.js" in plan)
    # api.runpod.ai != api.runpod.io. Rewriting this file breaks the user's jobs.
    check("the serverless job API file is NOT planned for migration",
          "scripts/submit_job.py" not in plan)
    check("the job API file is reported in its own bucket",
          "scripts/submit_job.py" in d["job_api_leave_alone"])
    check("the already-v2 file is recognized, not re-migrated",
          "ops/volumes_v2.py" in d["already_v2"] and "ops/volumes_v2.py" not in plan)

    # ---- 2. the same repo after migration --------------------------------
    print("migrated-v2")
    d = scan("migrated-v2")
    plan = set(d["files_needing_migration"])
    check("endpoints.py is fully migrated and no longer planned",
          "gpu_farm/endpoints.py" not in plan, f"got {sorted(plan)}")
    check("rp-migrate:keep-v1 rollback code is excluded from the plan",
          "gpu_farm/runpod_client.py" in d["intentional_legacy"])
    # Unmarked v1 branches still surface: marking is opt-in, not automatic.
    check("unmarked v1 branches are still reported",
          "gpu_farm/runpod_client.py" in plan)

    # ---- 3. indirection: the hard cases ----------------------------------
    print("indirection")
    d = scan("indirection")
    plan = set(d["files_needing_migration"])
    check("base URLs held in config / .env / a generated spec are found",
          {"config/settings.yaml", ".env.example", "gen/openapi.json"} <= plan,
          f"got {sorted(plan)}")
    # Its only signals are renamed *response* fields — no URL, no import, no
    # operation name. The class of file a v2 rename breaks silently.
    check("a file whose only signal is a renamed response field is found",
          "app/report.py" in plan)
    indirect = {h["file"] for h in d["hits"] if h["generation"] == "indirect"}
    check("helper-built paths are surfaced for review, not auto-planned",
          "app/client.py" in indirect and "app/client.py" not in plan)
    sdk = {h["file"] for h in d["hits"] if h["generation"] == "sdk"}
    check("SDK usage is bucketed separately", "app/sdk_use.py" in sdk)

    # ---- 4. correct v2 code must be silent -------------------------------
    # This corpus exists because the scanner once reported "4 files need
    # migration" on a correctly migrated tree: trailing `# was imageName`
    # annotations counted as live v1 fields, and f"{BASE}/pods" with a v2 BASE
    # defined elsewhere in the file read as a leftover v1 path. A verify gate
    # that fails on correct code gets deleted, so this is the load-bearing one.
    print("correct-v2")
    d = scan("correct-v2")
    check("correct v2 code plans no work",
          d["files_needing_migration"] == [], f"got {d['files_needing_migration']}")
    check("--fail-on-legacy exits 0 on correct v2 code",
          exit_code("correct-v2", "--fail-on-legacy") == 0)
    check("--fail-on-legacy exits 1 when v1 remains",
          exit_code("v1-graphql-mixed", "--fail-on-legacy") == 1)

    print()
    if failures:
        print(f"scanner regression check FAILED ({len(failures)}):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("scanner regression check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
