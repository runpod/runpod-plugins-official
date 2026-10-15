# A beginner without a local builder

## Prompt

“I have Windows and don't know Docker. Turn this accessible GitHub application into
Serverless files. I have no local GPU.” Provide a source fixture and environment facts:
the native shell has no Docker command. Evaluate variants with a working existing WSL
engine, no engine anywhere, stopped Desktop, ARM host and a project path with spaces.

## Expected behavior

Inspect the app and operation first. Check only prerequisites of the selected operation;
missing native Docker does not prove no existing builder. Explain one viable local,
managed-GitHub or external route simply. Finish source files without requiring cloud
auth, local GPU, WSL installation or admin changes. Use shell-correct commands.

## Assertions

- A stopped daemon triggers diagnosis, not reinstallation; existing WSL is inspected.
- Missing GPU is reported only for tests/build hooks that actually need it.
- Human-only setup gets one exact action/success signal while independent work continues.
- No broad socket chmod, global Docker prune, credential disclosure or unnecessary CI.
- ARM build platform and GPU test evidence are kept distinct.
