# Routing: check the worked example before planning a multi-step job

## Prompt

Two requests, answer both:

(a) Stop pod `abc123`.
(b) I want to serve a HuggingFace model on a serverless endpoint without baking the
weights into the image or managing a network volume. Get me there.

## Expected behavior

The two halves must route **differently** — that split is the point of this eval.

**(a) is a single CRUD call → skip step 0.** Goes straight to the lane per the
capability matrix (`stop-pod` if MCP is connected, else `runpodctl pod stop abc123`).
Opening a golden path for this is wrong: it burns a file read on a one-liner.

**(b) is multi-resource and provisions something billable → step 0 applies.** Before
planning or calling anything, matches the task against the golden-paths index in
`runpod/SKILL.md` and finds the row *"Serve a HuggingFace model without baking it in or
a volume (host-cached)"* → opens
[golden path 20](../golden-paths/20-model-caching-endpoint.md) and follows it, including
its `--model-reference` syntax, its GPU-only constraint, and its cost/cleanup section.
It does **not** re-derive a plan from the lane tables, and does not go straight to
`create-endpoint`/`serverless create` and improvise the model wiring.

A partial match would still count: if the task were a model the path does not use, the
path's ordering and gotchas still transfer, and opening it is correct.

## Assertions

- **(a)** answers with a single call and does **not** open a golden path
- **(b)** consults the golden-paths index **before** proposing commands or a plan
- **(b)** identifies path 20 (model caching / `--model-reference`) specifically, not
  just "there are examples"
- **(b)** does not present a hand-derived multi-step plan as the primary answer when a
  verified path covers it
- Neither half claims a capability is missing without checking (see
  `no-unchecked-absence-claims.eval.md`)

---

## Scenario B — entering a lane directly (the discriminating case)

Scenario A above is a **weak test**, established by measurement: run against the router,
agents opened the matching path with or without the step-0 rule, because the router's
"Want to…" table has a near-verbatim row and agents read the file end to end. Keep A for
the skip-on-trivial-call half, but A alone does not detect a regression.

The case that separates them is an agent that **never reads the router** — it is already
in a lane, which is the normal case once a session is underway.

### Prompt

*(session where the Runpod MCP tools are connected; entrypoint is
`runpod-mcp/SKILL.md`, not the router)*

I need a highly-available serverless endpoint. Same model weights available in three
different data centers so a regional outage doesn't take me down. Walk me through it.

### Expected behavior

1. **Opens `runpod/golden-paths/README.md` before planning**, on the strength of the
   lane's own "for a multi-step job, read the worked example before calling tools"
   pointer — not because the user said "check the examples".
2. **Lands on path 19** (3-region) or path 10 (2-region HA).
3. **One endpoint, one volume per DC** — `--network-volume-ids v1,v2,v3` with
   `--data-center-ids`. Not three separate endpoints behind a hand-rolled failover
   layer, and not "bake the weights, volumes can't do this".
4. **Flags that volumes do not replicate automatically** — a partial sync means a
   fraction of traffic silently serves stale weights.
5. Notes that MCP's `create-endpoint` does not express a multi-volume attach, so this
   step needs runpodctl or the GraphQL `saveEndpoint` fallback.

### Assertions

- Opens a golden path **before** settling on an approach
- Plan attaches several per-DC volumes to **one** endpoint
- Warns about non-replication
- Does **not** assert that a multi-DC endpoint cannot mount per-DC volumes — that is a
  false absence claim, and it is the observed failure mode when the example is not read

### Measured 2026-08-19

Same prompt, 2 runs per arm, `origin/main` vs this branch, agents reporting the files
they opened:

| | opened a golden path | plan source | one endpoint + per-DC volumes |
| --- | --- | --- | --- |
| without the lane pointer | 0 / 2 | derived | 0 / 2 |
| with it | 2 / 2, before planning | golden-path | 2 / 2 |

Both control runs invented a limitation to justify the derived plan — *"you cannot
attach one network volume to a multi-DC endpoint"* and *"network volumes are not a
mechanism for multi-DC redundancy"* — both falsified by path 10's live 2026-07-10 run.
