#!/usr/bin/env python3
"""Free live evals against the Runpod REST v2 API.

Creates, reads back and deletes only free resources (a template, an account
secret, a registry credential) and reads the catalog. Nothing billable is
created. Safety rails, in order:

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
# Fields that change on their own (status, cost, usage); ignored by the field diff.
VOLATILE = {"cost", "runtime", "uptimeSeconds", "lastStatusChange", "lastStartedAt",
            "startedAt", "updatedAt", "lastUsedAt", "usage", "desiredStatus",
            "runtimeStatus", "machine", "workers", "status"}


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def call(method: str, path: str, body: dict | None = None, key: str = "") -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "User-Agent": "runpod-plugins-official-live-evals"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode() or "{}"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise ApiError(e.code, raw) from None
    raise AssertionError("unreachable")


def scrub(obj):
    """Drop env values (they can hold plaintext keys) before anything hits disk."""
    if isinstance(obj, dict):
        return {k: ({kk: "[omitted]" for kk in v} if k == "env" and isinstance(v, dict) else scrub(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def list_all(kind: str, key: str) -> list[dict]:
    path, field = KINDS[kind]
    out, cursor = [], None
    while True:
        q = f"{path}?cursor={urllib.parse.quote(cursor, safe='')}" if cursor else path
        _, body = call("GET", q, key=key)
        if field not in body:
            # A renamed list key would otherwise read as an empty list in both snapshots.
            raise RuntimeError(f"{path}: no {field!r} key in the list response")
        out.extend(body[field])
        page = body.get("pagination") or {}
        if not page.get("hasNextPage") or not page.get("nextCursor"):
            return out
        cursor = page["nextCursor"]


def snapshot(key: str) -> dict:
    return {k: scrub(list_all(k, key)) for k in KINDS}


def diff(base: dict, final: dict) -> dict:
    """Return problems: missing baseline items, leftover skills-test- items, field drift."""
    report = {"missing": [], "leftover": [], "changed": []}
    for kind in KINDS:
        b = {x["id"]: x for x in base.get(kind, [])}
        f = {x["id"]: x for x in final.get(kind, [])}
        report["missing"] += [(kind, i, b[i].get("name")) for i in b if i not in f]
        report["leftover"] += [(kind, x["id"], x.get("name")) for x in final.get(kind, [])
                               if str(x.get("name", "")).startswith(PREFIX_ROOT)]
        for i in b:
            if i in f:
                strip = lambda o: {k: v for k, v in o.items() if k not in VOLATILE}
                if strip(b[i]) != strip(f[i]):
                    report["changed"].append((kind, i, b[i].get("name")))
    return report


class Ledger:
    def __init__(self, path: str, run: str):
        self.path, self.run, self.items, self.n = path, run, [], 0

    def name(self, check: str) -> str:
        self.n += 1
        return f"{PREFIX_ROOT}free-{self.run}-{check}-{self.n}"

    def add(self, kind: str, rid: str, name: str):
        self.items.append({"kind": kind, "id": rid, "name": name, "deleted": False})
        self.save()

    def save(self):
        with open(self.path, "w") as fh:
            json.dump(self.items, fh, indent=1)


DELETE_PATH = {"template": "/v2/templates/{}", "secret": "/v2/account/secrets/{}",
               "registry": "/v2/registries/{}"}
GET_PATH = DELETE_PATH


def delete_recorded(ledger: Ledger, key: str) -> list[str]:
    """Delete ledger ids only, after confirming the live name carries this run's prefix."""
    leftovers = []
    run_prefix = f"{PREFIX_ROOT}free-{ledger.run}-"
    for it in ledger.items:
        if it["deleted"]:
            continue
        path = DELETE_PATH[it["kind"]].format(it["id"])
        try:
            _, live = call("GET", path, key=key)
        except ApiError as e:
            if e.status == 404:
                it["deleted"] = True
                continue
            raise
        if not str(live.get("name", "")).startswith(run_prefix):
            leftovers.append(f"{it['kind']} {it['id']}: live name {live.get('name')!r} lacks the run prefix; not deleted")
            continue
        for attempt in (1, 2):
            try:
                call("DELETE", path, key=key)
                it["deleted"] = True
                break
            except ApiError as e:
                if e.status == 404:
                    it["deleted"] = True
                    break
                if attempt == 2:
                    leftovers.append(f"{it['kind']} {it['id']}: delete failed twice ({e})")
        ledger.save()
    return leftovers


def get_status(path: str, key: str) -> int:
    """Status of a GET; a delete check expects 404."""
    try:
        return call("GET", path, key=key)[0]
    except ApiError as e:
        return e.status


def run_checks(key: str, ledger: Ledger,
               results: list[tuple[str, bool, str]]) -> list[tuple[str, bool, str]]:
    """Append each result to the caller's list, so results survive a mid-run exception."""

    def record(check, ok, evidence):
        results.append((check, ok, evidence))
        print(f"{'PASS' if ok else 'FAIL'} {check}: {evidence}")

    # Catalog reads (free).
    _, g = call("GET", "/v2/catalog/gpus?product=SERVERLESS&include=AVAILABILITY", key=key)
    _, c = call("GET", "/v2/catalog/cpus", key=key)
    _, d = call("GET", "/v2/catalog/datacenters", key=key)
    record("catalog", bool(g.get("gpus")) and bool(c.get("cpus")) and bool(d.get("dataCenters")),
           f"{len(g.get('gpus', []))} gpus, {len(c.get('cpus', []))} cpus, {len(d.get('dataCenters', []))} data centers")

    # Template: create, read back, delete, confirm gone.
    name = ledger.name("tpl")
    _, t = call("POST", "/v2/templates", {"name": name, "image": "ubuntu:22.04",
                                           "env": {"SKILLS_TEST": "1"}}, key=key)
    ledger.add("template", t["id"], name)
    _, tr = call("GET", f"/v2/templates/{t['id']}", key=key)
    record("template-readback", tr.get("name") == name and tr.get("image") == "ubuntu:22.04",
           f"category={tr.get('category')!r} (skills say it defaults to NVIDIA)")
    delete_recorded(ledger, key)
    st = get_status(f"/v2/templates/{t['id']}", key)
    record("template-delete", st == 404, f"GET after delete -> {st}")

    # Secret: create, read back (value must not come back), collision 409, delete.
    name = ledger.name("secret")  # hyphens are allowed in secret names
    value = pysecrets.token_urlsafe(24)
    _, s = call("POST", "/v2/account/secrets", {"name": name, "value": value}, key=key)
    ledger.add("secret", s["id"], name)
    _, sr = call("GET", f"/v2/account/secrets/{s['id']}", key=key)
    record("secret-write-only", "value" not in sr and value not in json.dumps(sr), "read-back has no value")
    try:
        _, dup = call("POST", "/v2/account/secrets", {"name": name, "value": value}, key=key)
        if dup.get("id"):
            ledger.add("secret", dup["id"], name)
        record("secret-name-collision", False, "duplicate name was accepted (skills say 409)")
    except ApiError as e:
        record("secret-name-collision", e.status == 409, f"duplicate create -> {e.status}")
    delete_recorded(ledger, key)
    st = get_status(f"/v2/account/secrets/{s['id']}", key)
    record("secret-delete", st == 404, f"GET after delete -> {st}")

    # Registry credential: create with throwaway creds, read back, delete.
    name = ledger.name("reg")
    _, r = call("POST", "/v2/registries", {"name": name, "username": "skills-test",
                                            "password": pysecrets.token_urlsafe(24)}, key=key)
    ledger.add("registry", r["id"], name)
    _, rr = call("GET", f"/v2/registries/{r['id']}", key=key)
    record("registry-write-only", "password" not in rr and "username" not in rr,
           "read-back has no username/password")
    delete_recorded(ledger, key)
    st = get_status(f"/v2/registries/{r['id']}", key)
    record("registry-delete", st == 404, f"GET after delete -> {st}")
    return results


def self_test() -> int:
    led = Ledger(os.devnull, "t1")
    assert led.name("tpl") == "skills-test-free-t1-tpl-1"
    base = {"pods": [{"id": "p1", "name": "keep", "cost": 1}], "templates": [{"id": "t1", "name": "a"}]}
    same = {"pods": [{"id": "p1", "name": "keep", "cost": 2}], "templates": [{"id": "t1", "name": "a"}]}
    r = diff(base, same)
    assert r == {"missing": [], "leftover": [], "changed": []}, r
    bad = {"pods": [], "templates": [{"id": "t1", "name": "b"}, {"id": "t2", "name": "skills-test-free-x-1"}]}
    r = diff(base, bad)
    assert r["missing"] == [("pods", "p1", "keep")], r
    assert r["leftover"] == [("templates", "t2", "skills-test-free-x-1")], r
    assert r["changed"] == [("templates", "t1", "a")], r
    assert scrub({"env": {"K": "secret"}})["env"] == {"K": "[omitted]"}
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
    os.makedirs(a.out, exist_ok=True)
    # Run id plus attempt, so a re-run never reuses an earlier attempt's names.
    gh_run = (os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT"))
    run = "-".join(x for x in gh_run if x) or time.strftime("%Y%m%d%H%M%S")
    ledger = Ledger(os.path.join(a.out, "created.json"), run)
    base = snapshot(key)
    with open(os.path.join(a.out, "baseline.json"), "w") as fh:
        json.dump(base, fh, indent=1)
    results: list[tuple[str, bool, str]] = []
    leftovers: list[str] = []
    error = None
    try:
        run_checks(key, ledger, results)
    except Exception as e:  # stop creating, clean up, report
        error = repr(e)
        print(f"ERROR: {error}")
    finally:
        leftovers = delete_recorded(ledger, key)
    final = snapshot(key)
    with open(os.path.join(a.out, "final.json"), "w") as fh:
        json.dump(final, fh, indent=1)
    rep = diff(base, final)
    summary = {"results": results, "diff": rep, "leftovers": leftovers, "error": error}
    with open(os.path.join(a.out, "report.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    # The job log is public: print only counts for pre-existing resources (ids and names
    # stay in report.json); leftovers are this run's own skills-test- resources.
    log_diff = {"missing": len(rep["missing"]), "changed": len(rep["changed"]),
                "leftover": rep["leftover"]}
    print(json.dumps({**summary, "diff": log_diff}, indent=1))
    ok = (error is None and all(r[1] for r in results) and not leftovers
          and not rep["missing"] and not rep["leftover"])
    if rep["changed"]:
        print(f"note: {len(rep['changed'])} baseline items changed fields (not by this run's "
              "writes, which touch only new ids); see report.json")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
