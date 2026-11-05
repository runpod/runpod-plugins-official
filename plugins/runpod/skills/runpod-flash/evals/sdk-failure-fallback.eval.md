# Fall back to runpod-flash when the SDK path fails

## Prompt

I moved my project to `runpod` 2.x with `rp flash`. `rp flash deploy` succeeds, but the GPU
worker crash-loops before my function runs, with a traceback inside `runpod/apps/`. The same
code deployed fine with `runpod-flash` last week. I need this endpoint up today.

## Expected behavior

The agent should:

1. Treat it as a possible SDK bug, not only a code bug: check the installed version with
   `pip show runpod`, upgrade, and look at the runpod-python CHANGELOG and the commit history
   for `runpod/apps` for a fix
2. If no fix is out, offer `runpod-flash` as the fallback for this project, installed as an
   environment of its own with the project's requirements and `runpod<2`
3. Deploy with `flash deploy` from the pre-migration code (the previous commit), and keep any
   working `runpod-flash` endpoints running
4. Tell the user `runpod-flash` gets no fixes after October 29, 2026, and to move back to the
   SDK once the fix ships

## Assertions

- Checks the installed `runpod` version or upgrades before falling back
- Points to the runpod-python CHANGELOG or commit history
- Installs `runpod-flash` in a separate environment with `runpod<2` and the project's requirements, not into the project's `runpod` 2.x environment
- Does NOT install `runpod-flash` into the project environment in a way that downgrades `runpod`
- Does NOT delete working `runpod-flash` endpoints while the SDK version is broken
- Mentions the October 29, 2026 no-fixes date
