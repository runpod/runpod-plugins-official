#!/usr/bin/env python3
"""Free live evals against the Runpod REST v2 API.

Creates, reads back and deletes only free resources (a template, an account
secret, a registry credential, and scale-to-zero endpoints that are never
invoked, so no worker starts) and reads the catalog. Nothing billable runs.
Each check id in CHECK_IDS is cited as ``live:<id>`` by the golden paths it
covers (``evals:`` frontmatter); hooks/check_golden_paths.py keeps them in sync.
Safety rails, in order:

1. Snapshot every listable resource (pods, endpoints, templates, network
   volumes, global volumes, secrets, registries) before any write.
2. Name every created resource ``skills-test-free-<run>-<check>-<n>`` and append its id
   to the ledger file right after the create returns.
3. Delete only ids recorded in the ledger whose live name still carries this
   run's prefix; never delete by prefix alone. Each delete is retried once.
4. Re-list everything and diff against the snapshot: nothing named
   ``skills-test-`` may remain and every snapshot item must still be present.

Without RUNPOD_API_KEY the script prints a skip notice and exits 0, so the
scheduled workflow is a no-op on forks and on repos without the secret.
``--self-test`` exercises the diff and naming logic offline.
Secret and registry values are generated at random and never printed; env
values are stripped from every snapshot written to disk.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets as pysecrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

JsonObj = dict[str, Any]
Result = tuple[str, bool, str]
# (kind, id, name) of a resource the final diff flags.
Problem = tuple[str, Any, Any]

API = os.environ.get("RUNPOD_REST_V2_URL", "https://api.runpod.io")
PREFIX_ROOT = "skills-test-"
KINDS = {
    # kind: (list path, response list key)
    "pods": ("/v2/pods", "pods"),
    "endpoints": ("/v2/serverless", "endpoints"),
    "templates": ("/v2/templates", "templates"),
    "networkVolumes": ("/v2/network-volumes", "networkVolumes"),
    "globalVolumes": ("/v2/global-volumes", "globalVolumes"),
    "secrets": ("/v2/account/secrets", "secrets"),
    "registries": ("/v2/registries", "registries"),
}
# Kinds whose list takes `limit`/`cursor`. Send a page size: without one the server
# uses 1000, and a large page can fail with 413 ResponseTooLargeError.
PAGINATED = frozenset({"pods", "endpoints", "templates", "networkVolumes", "globalVolumes"})
PAGE_SIZE = 200
# Fields that change on their own (status, cost, usage); ignored by the field diff.
VOLATILE = {
    "cost",
    "runtime",
    "uptimeSeconds",
    "lastStatusChange",
    "lastStartedAt",
    "startedAt",
    "updatedAt",
    "lastUsedAt",
    "usage",
    "desiredStatus",
    "runtimeStatus",
    "machine",
    "workers",
    "status",
}


class ApiError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def call(method: str, path: str, body: JsonObj | None = None, key: str = "") -> tuple[int, JsonObj]:
    url = API + path
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"refusing a non-http(s) API URL: {API!r}")
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "runpod-plugins-official-live-evals",
    }
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.build_opener().open(req, timeout=60) as r:
                raw = r.read().decode() or "{}"
                parsed: JsonObj = json.loads(raw)
                return int(r.status), parsed
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            # 429 means the request was not processed, so any method may retry. A 5xx on a
            # POST/PATCH may have applied server-side; retrying could create an unrecorded
            # duplicate that the ledger never deletes, so only GET/DELETE retry on 5xx.
            idempotent = method in ("GET", "DELETE")
            retryable = e.code == 429 or (e.code in (500, 502, 503, 504) and idempotent)
            if retryable and attempt < 3:
                time.sleep(2**attempt)
                continue
            raise ApiError(e.code, raw) from None
    raise AssertionError("unreachable")


def scrub(obj: object) -> object:
    """Drop env values (they can hold plaintext keys) before anything hits disk."""
    if isinstance(obj, dict):
        return {
            k: (dict.fromkeys(v, "[omitted]") if k == "env" and isinstance(v, dict) else scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def list_all(kind: str, key: str) -> list[JsonObj]:
    path, field = KINDS[kind]
    out: list[JsonObj] = []
    cursor: str | None = None
    while True:
        params = ({"limit": str(PAGE_SIZE)} if kind in PAGINATED else {}) | (
            {"cursor": cursor} if cursor else {}
        )
        q = f"{path}?{urllib.parse.urlencode(params)}" if params else path
        _, body = call("GET", q, key=key)
        if field not in body:
            # A renamed list key would otherwise read as an empty list in both snapshots.
            raise RuntimeError(f"{path}: no {field!r} key in the list response")
        out.extend(body[field])
        page = body.get("pagination") or {}
        if not page.get("hasNextPage") or not page.get("nextCursor"):
            return out
        cursor = page["nextCursor"]


def snapshot(key: str) -> dict[str, object]:
    return {k: scrub(list_all(k, key)) for k in KINDS}


def stable(o: JsonObj) -> JsonObj:
    """The item without its VOLATILE fields, for the field diff."""
    return {k: v for k, v in o.items() if k not in VOLATILE}


def diff(base: dict[str, Any], final: dict[str, Any]) -> dict[str, list[Problem]]:
    """Return problems: missing baseline items, leftover skills-test- items, field drift."""
    report: dict[str, list[Problem]] = {"missing": [], "leftover": [], "changed": []}
    for kind in KINDS:
        b = {x["id"]: x for x in base.get(kind, [])}
        f = {x["id"]: x for x in final.get(kind, [])}
        report["missing"] += [(kind, i, b[i].get("name")) for i in b if i not in f]
        report["leftover"] += [
            (kind, x["id"], x.get("name"))
            for x in final.get(kind, [])
            if str(x.get("name", "")).startswith(PREFIX_ROOT)
        ]
        report["changed"] += [
            (kind, i, b[i].get("name")) for i in b if i in f and stable(b[i]) != stable(f[i])
        ]
    return report


class Ledger:
    def __init__(self, path: Path, run: str) -> None:
        self.path = path
        self.run = run
        self.items: list[JsonObj] = []
        self.n = 0

    def name(self, check: str) -> str:
        self.n += 1
        return f"{PREFIX_ROOT}free-{self.run}-{check}-{self.n}"

    def add(self, kind: str, rid: str, name: str) -> None:
        self.items.append({"kind": kind, "id": rid, "name": name, "deleted": False})
        self.save()

    def save(self) -> None:
        with self.path.open("w") as fh:
            json.dump(self.items, fh, indent=1)


# Check ids golden paths may cite as `live:<id>`.
CHECK_IDS = (
    "catalog",
    "datacenter-volume-tiers",
    "template-readback",
    "template-delete",
    "secret-write-only",
    "secret-name-collision",
    "secret-delete",
    "registry-write-only",
    "registry-delete",
    "endpoint-timeout",
    "endpoint-scaler",
    "lb-endpoint",
    "endpoint-delete-keeps-template",
)
DELETE_PATH = {
    "endpoint": "/v2/serverless/{}",
    "template": "/v2/templates/{}",
    "secret": "/v2/account/secrets/{}",
    "registry": "/v2/registries/{}",
}
# Dependency order: an endpoint goes before the template it was created from.
DELETE_ORDER = {"endpoint": 0, "template": 1, "secret": 2, "registry": 3}


def delete_recorded(
    ledger: Ledger,
    key: str,
    kinds: frozenset[str] | None = None,
    api: Callable[..., tuple[int, JsonObj]] = call,
) -> list[str]:
    """Delete ledger ids only, after confirming the live name carries this run's prefix.

    `kinds` limits the pass to those resource kinds; `api` is `call` (a fake in the self-test).
    """
    leftovers: list[str] = []
    run_prefix = f"{PREFIX_ROOT}free-{ledger.run}-"
    for it in sorted(ledger.items, key=lambda x: DELETE_ORDER[x["kind"]]):
        if it["deleted"] or (kinds is not None and it["kind"] not in kinds):
            continue
        path = DELETE_PATH[it["kind"]].format(it["id"])
        try:
            _, live = api("GET", path, key=key)
        except ApiError as e:
            # A failed read is a leftover, never an abort: this also runs from main()'s
            # finally, where raising would skip the remaining items and the report.
            if e.status == 404:
                it["deleted"] = True
            else:
                leftovers.append(f"{it['kind']} {it['id']}: read before delete failed ({e})")
            continue
        except (OSError, ValueError) as e:  # URLError, TimeoutError, JSONDecodeError
            leftovers.append(f"{it['kind']} {it['id']}: read before delete failed ({e!r})")
            continue
        if not str(live.get("name", "")).startswith(run_prefix):
            leftovers.append(
                f"{it['kind']} {it['id']}: live name {live.get('name')!r} lacks the run prefix;"
                " not deleted"
            )
            continue
        for attempt in (1, 2):
            try:
                api("DELETE", path, key=key)
                it["deleted"] = True
                break
            except ApiError as e:
                if e.status == 404:
                    it["deleted"] = True
                    break
                if attempt == 2:
                    leftovers.append(f"{it['kind']} {it['id']}: delete failed twice ({e})")
            except (OSError, ValueError) as e:
                if attempt == 2:
                    leftovers.append(f"{it['kind']} {it['id']}: delete failed twice ({e!r})")
        ledger.save()
    # The 404 and skip branches continue past the per-item save; record their state too.
    ledger.save()
    return leftovers


def get_status(path: str, key: str) -> int:
    """Status of a GET; a delete check expects 404."""
    try:
        return call("GET", path, key=key)[0]
    except ApiError as e:
        return e.status


def run_checks(key: str, ledger: Ledger, results: list[Result]) -> None:
    """Append each result to the caller's list, so results survive a mid-run exception."""

    def record(check: str, ok: bool, evidence: str) -> None:
        results.append((check, ok, evidence))
        print(f"{'PASS' if ok else 'FAIL'} {check}: {evidence}")

    # Catalog reads (free).
    _, g = call("GET", "/v2/catalog/gpus?product=SERVERLESS&include=AVAILABILITY", key=key)
    _, c = call("GET", "/v2/catalog/cpus", key=key)
    _, d = call("GET", "/v2/catalog/datacenters", key=key)
    record(
        "catalog",
        bool(g.get("gpus")) and bool(c.get("cpus")) and bool(d.get("dataCenters")),
        f"{len(g.get('gpus', []))} gpus, {len(c.get('cpus', []))} cpus, "
        f"{len(d.get('dataCenters', []))} data centers",
    )

    vt = {t for dc in d.get("dataCenters", []) for t in (dc.get("networkVolumeTypes") or [])}
    hp = [
        dc["id"]
        for dc in d.get("dataCenters", [])
        if "HIGH_PERFORMANCE" in (dc.get("networkVolumeTypes") or [])
    ]
    record(
        "datacenter-volume-tiers",
        vt <= {"STANDARD", "HIGH_PERFORMANCE"} and bool(hp),
        f"tiers seen {sorted(vt)}; HIGH_PERFORMANCE in {hp} "
        "(golden path 21 picks the DC from this read)",
    )

    # Endpoints (golden paths 10, 13, 14; gotchas "Endpoint timeout comes back 0"). Scale to
    # zero and never invoked, so no worker starts and nothing bills.
    cpu = [{"id": "cpu3c", "vcpuCount": 2}]
    name = ledger.name("eptpl")
    _, et = call(
        "POST",
        "/v2/templates",
        {"name": name, "image": "ubuntu:22.04", "serverless": True, "category": "CPU"},
        key=key,
    )
    ledger.add("template", et["id"], name)
    name = ledger.name("ep")
    _, ep = call(
        "POST",
        "/v2/serverless",
        {
            "name": name,
            "type": "QUEUE",
            "templateId": et["id"],
            "cpu": cpu,
            "workers": {"min": 0, "max": 1, "idleTimeout": 5},
            "scaling": {"type": "QUEUE_DELAY", "queueDelay": 4},
        },
        key=key,
    )
    ledger.add("endpoint", ep["id"], name)
    record(
        "endpoint-timeout",
        ep.get("timeout") == 0,
        f"create without timeout -> timeout={ep.get('timeout')!r} "
        "(skills say 0; if this changes, update gotchas.md)",
    )
    call(
        "PATCH",
        f"/v2/serverless/{ep['id']}",
        {"timeout": 600000, "scaling": {"type": "REQUEST_COUNT", "requestCount": 2}},
        key=key,
    )
    _, er = call("GET", f"/v2/serverless/{ep['id']}", key=key)
    record(
        "endpoint-scaler",
        er.get("timeout") == 600000
        and er.get("scaling") == {"type": "REQUEST_COUNT", "requestCount": 2},
        f"after PATCH: timeout={er.get('timeout')!r} scaling={er.get('scaling')!r} "
        f"idleTimeout={(er.get('workers') or {}).get('idleTimeout')!r}",
    )
    name = ledger.name("lb")
    _, lb = call(
        "POST",
        "/v2/serverless",
        {
            "name": name,
            "type": "LOAD_BALANCER",
            "image": "ubuntu:22.04",
            "env": {"PORT": "80"},
            "cpu": cpu,
            "workers": {"min": 0, "max": 1},
            "scaling": {"type": "REQUEST_COUNT", "requestCount": 1},
            "timeout": 600000,
        },
        key=key,
    )
    ledger.add("endpoint", lb["id"], name)
    urls = lb.get("requestUrls") or {}
    record(
        "lb-endpoint",
        lb.get("type") == "LOAD_BALANCER"
        and lb.get("timeout") == 600000
        and str(urls.get("health", "")).endswith("/ping")
        and lb.get("ports") == ["80/http"],
        f"type={lb.get('type')!r} timeout={lb.get('timeout')!r} ports={lb.get('ports')!r} "
        f"health={urls.get('health')!r}",
    )
    # Delete the endpoints first (dependency order), then check their template survived.
    leftovers = delete_recorded(ledger, key, kinds=frozenset({"endpoint"}))
    try:
        _, still = call("GET", f"/v2/templates/{et['id']}", key=key)
        kept = still.get("id") == et["id"]
    except ApiError as e:
        if e.status != 404:
            raise
        kept = False
    record(
        "endpoint-delete-keeps-template",
        not leftovers and kept,
        "templateId template still exists after its endpoint's delete "
        "(golden path 14: delete it yourself)"
        + (f"; endpoint delete left {leftovers}" if leftovers else ""),
    )
    for line in delete_recorded(ledger, key):
        print(line)

    # Template: create, read back, delete, confirm gone.
    name = ledger.name("tpl")
    _, t = call(
        "POST",
        "/v2/templates",
        {"name": name, "image": "ubuntu:22.04", "env": {"SKILLS_TEST": "1"}},
        key=key,
    )
    ledger.add("template", t["id"], name)
    _, tr = call("GET", f"/v2/templates/{t['id']}", key=key)
    record(
        "template-readback",
        tr.get("name") == name and tr.get("image") == "ubuntu:22.04",
        f"category={tr.get('category')!r} (skills say it defaults to NVIDIA)",
    )
    for line in delete_recorded(ledger, key):
        print(line)
    st = get_status(f"/v2/templates/{t['id']}", key)
    record("template-delete", st == 404, f"GET after delete -> {st}")

    # Secret: create, read back (value must not come back), collision 409, delete.
    name = ledger.name("secret")  # hyphens are allowed in secret names
    value = pysecrets.token_urlsafe(24)
    _, s = call("POST", "/v2/account/secrets", {"name": name, "value": value}, key=key)
    ledger.add("secret", s["id"], name)
    _, sr = call("GET", f"/v2/account/secrets/{s['id']}", key=key)
    record(
        "secret-write-only",
        "value" not in sr and value not in json.dumps(sr),
        "read-back has no value",
    )
    try:
        _, dup = call("POST", "/v2/account/secrets", {"name": name, "value": value}, key=key)
        if dup.get("id"):
            ledger.add("secret", dup["id"], name)
        record("secret-name-collision", False, "duplicate name was accepted (skills say 409)")
    except ApiError as e:
        record("secret-name-collision", e.status == 409, f"duplicate create -> {e.status}")
    for line in delete_recorded(ledger, key):
        print(line)
    st = get_status(f"/v2/account/secrets/{s['id']}", key)
    record("secret-delete", st == 404, f"GET after delete -> {st}")

    # Registry credential: create with throwaway creds, read back, delete.
    name = ledger.name("reg")
    _, r = call(
        "POST",
        "/v2/registries",
        {"name": name, "username": "skills-test", "password": pysecrets.token_urlsafe(24)},
        key=key,
    )
    ledger.add("registry", r["id"], name)
    _, rr = call("GET", f"/v2/registries/{r['id']}", key=key)
    record(
        "registry-write-only",
        "password" not in rr and "username" not in rr,
        "read-back has no username/password",
    )
    for line in delete_recorded(ledger, key):
        print(line)
    st = get_status(f"/v2/registries/{r['id']}", key)
    record("registry-delete", st == 404, f"GET after delete -> {st}")


def self_test() -> int:
    led = Ledger(Path(os.devnull), "t1")
    assert led.name("tpl") == "skills-test-free-t1-tpl-1"
    calls: list[tuple[str, str]] = []

    def fake(
        method: str, path: str, body: JsonObj | None = None, key: str = ""
    ) -> tuple[int, JsonObj]:
        calls.append((method, path))
        return 200, {"name": "skills-test-free-t1-x"}

    for kind in ("registry", "template", "endpoint"):
        led.add(kind, kind[0], "skills-test-free-t1-x")
    # One unfiltered pass deletes in dependency order: endpoint before its template.
    assert delete_recorded(led, "", api=fake) == []
    assert [c for c in calls if c[0] == "DELETE"] == [
        ("DELETE", "/v2/serverless/e"),
        ("DELETE", "/v2/templates/t"),
        ("DELETE", "/v2/registries/r"),
    ], calls

    # `kinds` limits a pass to those kinds and leaves the rest undeleted.
    only = Ledger(Path(os.devnull), "t1")
    for kind in ("template", "endpoint"):
        only.add(kind, kind[0], "skills-test-free-t1-x")
    calls.clear()
    assert delete_recorded(only, "", kinds=frozenset({"endpoint"}), api=fake) == []
    assert calls == [("GET", "/v2/serverless/e"), ("DELETE", "/v2/serverless/e")], calls
    assert [it["deleted"] for it in only.items] == [False, True]

    # A ledger id whose live name lacks the run prefix is a leftover and is never deleted.
    foreign = Ledger(Path(os.devnull), "t1")
    foreign.add("template", "f", "skills-test-free-t1-x")
    calls.clear()

    def renamed(
        method: str, path: str, body: JsonObj | None = None, key: str = ""
    ) -> tuple[int, JsonObj]:
        calls.append((method, path))
        return 200, {"name": "someone-elses-template"}

    left = delete_recorded(foreign, "", api=renamed)
    assert len(left) == 1 and "lacks the run prefix" in left[0], left
    assert calls == [("GET", "/v2/templates/f")], calls
    assert not foreign.items[0]["deleted"]

    # A ledger id that already reads back 404 is marked deleted, with no DELETE sent.
    gone = Ledger(Path(os.devnull), "t1")
    gone.add("secret", "g", "skills-test-free-t1-x")
    calls.clear()

    def missing(
        method: str, path: str, body: JsonObj | None = None, key: str = ""
    ) -> tuple[int, JsonObj]:
        calls.append((method, path))
        raise ApiError(404, "")

    assert delete_recorded(gone, "", api=missing) == []
    assert calls == [("GET", "/v2/account/secrets/g")], calls
    assert gone.items[0]["deleted"]

    base = {
        "pods": [{"id": "p1", "name": "keep", "cost": 1}],
        "templates": [{"id": "t1", "name": "a"}],
    }
    same = {
        "pods": [{"id": "p1", "name": "keep", "cost": 2}],
        "templates": [{"id": "t1", "name": "a"}],
    }
    r = diff(base, same)
    assert r == {"missing": [], "leftover": [], "changed": []}, r
    bad = {
        "pods": [],
        "templates": [{"id": "t1", "name": "b"}, {"id": "t2", "name": "skills-test-free-x-1"}],
    }
    r = diff(base, bad)
    assert r["missing"] == [("pods", "p1", "keep")], r
    assert r["leftover"] == [("templates", "t2", "skills-test-free-x-1")], r
    assert r["changed"] == [("templates", "t1", "a")], r
    assert scrub({"env": {"K": "secret"}}) == {"env": {"K": "[omitted]"}}
    print("live_free_evals self-test OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", default="live-evals")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    key = os.environ.get("RUNPOD_API_KEY", "")
    if not key:
        print("RUNPOD_API_KEY not set: skipping live evals.")
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    # Run id plus attempt, so a re-run never reuses an earlier attempt's names.
    gh_run = (os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT"))
    run = "-".join(x for x in gh_run if x) or time.strftime("%Y%m%d%H%M%S")
    ledger = Ledger(out / "created.json", run)
    base = snapshot(key)
    with (out / "baseline.json").open("w") as fh:
        json.dump(base, fh, indent=1)
    results: list[Result] = []
    leftovers: list[str] = []
    error: str | None = None
    try:
        run_checks(key, ledger, results)
    except Exception as e:  # stop creating, clean up, report
        error = repr(e)
        print(f"ERROR: {error}")
    finally:
        leftovers = delete_recorded(ledger, key)
    rep: dict[str, list[Problem]] = {"missing": [], "leftover": [], "changed": []}
    try:
        final = snapshot(key)
    except (ApiError, OSError, ValueError, RuntimeError) as e:
        # Cleanup already ran; still write report.json, and fail the job via `error`.
        error = "; ".join(x for x in (error, f"final snapshot failed: {e!r}") if x)
        print(f"ERROR: final snapshot failed: {e!r}")
    else:
        with (out / "final.json").open("w") as fh:
            json.dump(final, fh, indent=1)
        rep = diff(base, final)
    summary = {"results": results, "diff": rep, "leftovers": leftovers, "error": error}
    with (out / "report.json").open("w") as fh:
        json.dump(summary, fh, indent=1)
    # The job log is public: print only counts for pre-existing resources (ids and names
    # stay in report.json); leftovers are this run's own skills-test- resources.
    log_diff = {
        "missing": len(rep["missing"]),
        "changed": len(rep["changed"]),
        "leftover": rep["leftover"],
    }
    print(json.dumps({**summary, "diff": log_diff}, indent=1))
    ok = (
        error is None
        and all(r[1] for r in results)
        and not leftovers
        and not rep["missing"]
        and not rep["leftover"]
    )
    if rep["changed"]:
        print(
            f"note: {len(rep['changed'])} baseline items changed fields (not by this run's "
            "writes, which touch only new ids); see report.json"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
