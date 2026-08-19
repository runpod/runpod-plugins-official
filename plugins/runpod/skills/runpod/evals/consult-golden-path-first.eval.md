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
