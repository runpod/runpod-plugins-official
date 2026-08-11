# Test corpora for the runpod-migrate scanner

Fixture repos that `hooks/check_migrate_scanner.py` runs
`plugins/runpod/skills/runpod-migrate/scripts/rp_api_inventory.py` against, asserting
what it must and must not report. CI runs that hook on every PR.

**This is deliberately not inside the skill directory.** `marketplace.json` installs
`./skills/runpod-migrate`, so anything under it ships to every user who installs the
plugin. Test data does not belong in that payload.

## The corpora

| Corpus | Represents |
| --- | --- |
| `v1-graphql-mixed/` | A real "we built this with an agent 18 months ago" repo: Python on REST v1, a GraphQL ops dashboard, a serverless **job API** caller that must not be touched, and one file already on v2. |
| `migrated-v2/` | The same code after migration, including a `RUNPOD_API_V1=1` rollback path marked `rp-migrate: keep-v1`. |
| `indirection/` | The cases plain grep cannot see: base URL only in `settings.yaml`/`.env`, paths built by a `_url()` helper, an SDK pinned in `requirements.txt`, a generated client, and a module whose only signal is a renamed *response* field. |
| `correct-v2/` | Correct, finished v2 code. Must produce **zero** findings. |

## Every assertion is here because something broke

Not hypotheticals — each of these was a real defect found during review:

- **`v1-graphql-mixed/dashboard/provision.js` contains no `runpod` string.** Only GraphQL
  operation names. A hand-written whole-file prefilter skipped it entirely; the prefilter
  is now derived from the signal table so the two cannot drift.
- **`indirection/app/report.py` has no URL, no import, no operation name** — only
  `p["costPerHr"]` and `pod["desiredStatus"]`. Same prefilter bug. This is the class of
  file a v2 rename breaks *silently*, in the callers of a wrapper.
- **`v1-graphql-mixed/scripts/submit_job.py` calls `api.runpod.**ai**/v2/…`** — the
  serverless job API, one letter from the control plane at `api.runpod.**io**`. Flagging
  it would make an agent rewrite working job submission.
- **`correct-v2/` is the load-bearing one.** The scanner once reported *"4 files need
  migration"* on a correctly migrated tree: trailing `# was imageName` annotations
  counted as live v1 fields, and `f"{BASE}/pods"` with a v2 `BASE` defined elsewhere in
  the file read as a leftover v1 path. A verify gate that fails on correct code gets
  deleted within a week — and worse, teaches agents to stop trusting the verify step.

## Running it

```bash
python3 hooks/check_migrate_scanner.py     # what CI runs
```

To confirm the gate can still fail, break something on purpose and re-run — e.g. make
`comment_index()` return `-1`, or empty the per-file `v2_names` set. Both should turn
`correct-v2` red.

Scanning the **repo root** with the scanner will flag these corpora as legacy code.
That is correct — they are v1 code on purpose. Point it at a real target instead.

## Not included, on purpose

Live API verification (`live_verify.py`) is kept out of this repo: it rents a real GPU
pod and costs money, so it must never run in CI. It lives with the maintainer's local
dev material alongside the rendered OpenAPI digests.
