# Inventory before editing, and leave the job API alone

## Prompt

Here's our repo. Move us over to the new Runpod REST API. Files:

```
gpu_farm/runpod_client.py    calls https://rest.runpod.io/v1/pods
scripts/submit_job.py        calls https://api.runpod.ai/v2/{endpoint_id}/run
ops/volumes_v2.py            calls https://api.runpod.io/v2/network-volumes
```

## Expected behavior

Per `runpod-migrate/SKILL.md`:

1. Runs `scripts/rp_api_inventory.py` **before** editing anything, and shows the user
   the resulting table.
2. Reports that `ops/volumes_v2.py` is **already on v2** and needs no work — users
   frequently do not know this about their own repo.
3. Reports that `scripts/submit_job.py` is the serverless **job API**
   (`api.runpod.ai/v2/<endpointId>/run`), a different API that is out of scope, and
   does **not** rewrite it — despite the `v2` in the path.
4. Migrates only `gpu_farm/runpod_client.py`.

## Assertions

- **Resolves the scanner's path before running it.** The script ships in the installed
  skill directory, not in the user's repo; the agent's working directory is the repo.
  Running `python3 scripts/rp_api_inventory.py .` verbatim is a `No such file or
  directory` failure, and the agent must not respond to that by abandoning the inventory
  and falling back to ad-hoc grep.
- Inventory is produced and shown before any file edit.
- `scripts/submit_job.py` is left byte-for-byte unchanged and is explicitly called out
  as out of scope.
- `ops/volumes_v2.py` is identified as already migrated and left unchanged.
- Does NOT treat `api.runpod.ai/v2/...` as evidence the codebase is already on REST v2.
