# Never assert a tool cannot do something without checking

## Prompt

I'm on runpodctl and I don't have the Runpod MCP connected. Can I read the logs of
the workers behind my serverless endpoint from the CLI, or do I need the MCP server
or the Console for that?

## Expected behavior

Per `runpod/SKILL.md` → *"These skills are a snapshot; the tools are the source of
truth"*:

1. **Answers yes, and names the command** — `runpodctl serverless logs <endpoint-id>`
   (v2.10.0+), optionally narrowed with `--worker`. Reaching for
   `runpodctl serverless --help` or `runpodctl version` to confirm the local binary
   has it is *better*, not worse.
2. **Does not answer from a remembered limitation.** "The CLI has no worker-log
   command, use MCP or the Console" was true through v2.9.0 and is the exact answer
   this eval exists to catch. A model that has internalized the older docs — or an
   older copy of this skill — will produce it confidently.
3. **If it hedges on version, it hedges with a floor, not a denial** — "needs
   runpodctl ≥ v2.10.0; check `runpodctl version`" is correct. "runpodctl cannot do
   this" is not.
4. **Names the pre-v2.10.0 fallbacks as fallbacks**, if it mentions them at all: the
   v2 REST SSE path, MCP `stream-worker-logs`, or the Console Workers tab.

The same rule generalizes: the only capability claim this plugin should make in the
negative is one carrying a version, a named API, or a "check it yourself" pointer.

## Assertions

- Answers **yes** and names `runpodctl serverless logs`
- Does **not** claim runpodctl lacks a worker-log command
- Does **not** require MCP or the Console to be the answer
- Any version caveat is expressed as a floor (`≥ v2.10.0` / `runpodctl version`), not
  as an absence
- Bonus, not required: verifies against `runpodctl serverless --help` rather than
  asserting from the skill text alone
