# Rollback flag: keeping v1 one env var away

While v2 is new to a team, an env-var switch that returns to the old code path is cheap
insurance. It is what makes a migration shippable on a Friday.

**Offer it, do not impose it.** Worth it for a service in production or anything on a
schedule. Skip it for a one-off script, a notebook, or a codebase with two call sites —
there the flag is more code than the migration.

Say out loud that it is **temporary**: v1 is deprecated, so this scaffolding comes out
once v2 has run clean for a release or two. Leave a note in the code saying so, or it
becomes permanent.

## The shape

Gate at the **client boundary**, not at each call site. One `USE_V1` read, one branch per
operation, both paths in the same function so they cannot drift apart unnoticed:

```python
import os

USE_V1 = os.environ.get("RUNPOD_API_V1", "").lower() in ("1", "true", "yes")

V1_BASE = "https://rest.runpod.io/v1"
V2_BASE = "https://api.runpod.io/v2"


def list_pods() -> list[dict]:
    if USE_V1:
        pods = session.get(f"{V1_BASE}/pods", params={"desiredStatus": "RUNNING"}).json()
        return [{**p, "status": p["desiredStatus"], "cost": p["costPerHr"]} for p in pods]

    pods = session.get(f"{V2_BASE}/pods").json()["pods"]
    return [p for p in pods if p["status"] == "RUNNING"]
```

Note what that example does: the v1 branch **normalizes to the v2 field names**. Callers
see one shape either way, so the flag stays contained in the client instead of leaking
`if USE_V1` into business logic.

## Rules that keep it honest

1. **Default to v2.** The flag turns v1 back *on*. A flag that defaults to the old path
   never gets removed, because nothing exercises the new one.
2. **Normalize responses to v2's shape** in the v1 branch (above). The alternative —
   normalizing to v1 — means you migrate twice.
3. **Log which path ran, once at startup.** `log.info("Runpod API: %s", "v1 (rollback)"
   if USE_V1 else "v2")`. Otherwise nobody can tell from the outside which one
   production is on, which defeats the point.
4. **Do not flag things v1 cannot do.** Availability-aware GPU selection, `requestUrls`,
   worker `isStale`, SSE logs — these have no v1 branch to fall back to. Either keep the
   feature v2-only and degrade gracefully under the flag, or leave it out of the
   migration commit entirely.
5. **One flag for the whole client.** Per-resource flags (`RUNPOD_PODS_V1`,
   `RUNPOD_ENDPOINTS_V1`) multiply the states you have to test and nobody tests them.

## Tell the scanner the v1 code is deliberate

A rollback path is legacy code you meant to keep, so `rp_api_inventory.py` would
otherwise report it forever and `--fail-on-legacy` could never pass. Mark it:

```python
V1_BASE = "https://rest.runpod.io/v1"  # rp-migrate: keep-v1

def _list_pods_v1():
    # rp-migrate: keep-v1 start   (rollback path, delete with the RUNPOD_API_V1 flag)
    pods = session.get(f"{V1_BASE}/pods", params={"desiredStatus": "RUNNING"}).json()
    return [{**p, "status": p["desiredStatus"], "cost": p["costPerHr"]} for p in pods]
    # rp-migrate: keep-v1 end
```

| Marker | Scope |
| --- | --- |
| `rp-migrate: keep-v1` or `rp-migrate: ignore` | that line |
| `rp-migrate: keep-v1 start` … `end` | the region between them |
| `rp-migrate: keep-v1 file` | the whole file |

Marked sites still appear in the report — under *kept on purpose* — but drop out of the
migration plan and out of `--fail-on-legacy`. Use the same markers for the GraphQL calls
that have no v2 equivalent (`myself`, secrets, spot pods, clusters), so a clean exit code
means "everything that can be migrated has been".

Deleting the markers is how you find the rollback code again when it is time to remove
it: `rg 'rp-migrate: keep-v1'`.

## Removing it

The exit criteria are worth writing into the PR description:

- v2 has served production traffic for N releases with no rollback,
- the v1 branches have no coverage in CI that the v2 branches lack,
- then delete the flag and the v1 branches in one commit, and re-run
  `rp_api_inventory.py --fail-on-legacy` to prove nothing was left behind.
