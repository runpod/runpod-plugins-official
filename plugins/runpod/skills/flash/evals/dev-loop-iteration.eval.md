# Iterate on an SDK app against a live remote worker

> **LIVE eval.** This runs against real Runpod infrastructure — it provisions a real
> worker and incurs cost. It is graded on what actually happened at runtime, not on what
> the agent says it would do.

## Setup

- Requires `runpod>=2.0.0rc2` installed in the active environment and a valid key
  (`rp login` or `RUNPOD_API_KEY`).
- Copy the fixture to a scratch dir so the graded fix does not mutate the committed
  fixture: `cp -r flash/evals/fixtures/dev-loop /tmp/dev-loop-eval && cd /tmp/dev-loop-eval`.
- The fixture's `describe` function imports `humanize`, which is not in its `dependencies`, so
  it fails on the worker with `No module named 'humanize'` until the dependency is declared.

## Prompt

Use the Runpod SDK app in this directory. `main()` fails when `describe` runs on a worker.
Iterate against a **real** remote worker: start the dev loop, read the worker's output, fix
what is broken, and confirm `main()` succeeds. I don't want to deploy on every change.

## Expected behavior

The agent should actually execute (not merely describe) the following:

1. Use `rp flash dev main.py` (not `rp flash deploy`) and run it in the **background** with
   stdin closed and output captured to a log, or use `rp flash dev main.py --once` per attempt.
2. Read the captured log to observe the **real** error from the worker.
3. Diagnose it: the worker lacks `humanize`. Fix by adding `"humanize"` to the decorator's
   `dependencies`, not by vendoring or `pip install` inside the function.
4. Re-run without deploying: save the file and let the background session re-run, or run
   `--once` again.
5. Confirm the entrypoint succeeds (`✓` result line, the `assert` passes).
6. End the session with `kill` (SIGTERM) or SIGINT (or let `--once` exit) and confirm the log reports its
   temporary endpoints deleted.

## Assertions

- Runs `rp flash dev` non-blocking (background with captured output) or with `--once`; does
  NOT hang on an interactive session
- Does NOT run `rp flash deploy` during the loop
- Reports the **verbatim** worker error containing `No module named 'humanize'`, from the live run
- Fixes it by adding `humanize` to `dependencies=[...]`
- Obtains a successful entrypoint run: `main()` prints `3.0 MB` and the log has no `✗` failure line
- Confirms cleanup from the log (`cleaning up ... deleted`); if cleanup failed, deletes only the
  `dev-dev-loop-eval-...` endpoint by id with `runpodctl serverless delete`

## Cleanup

- The dev session must delete its temporary endpoint. Verify with `runpodctl serverless list`
  that no `dev-dev-loop-eval-` endpoint remains.
- The agent must only stop processes it started.
- Restore the fixture if it was edited in place: `git checkout flash/evals/fixtures/dev-loop`.
