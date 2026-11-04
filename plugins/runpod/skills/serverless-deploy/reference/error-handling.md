---
concepts: [serverless-endpoint, job, worker]
---

# Serverless deploy — error handling

The failure → action table for the [serverless-deploy](../SKILL.md) playbook, moved here.
The playbook's phases and hard rules still apply; this says what to do when a
create or the smoke job fails.

- Smoke job returns `FAILED` with `gated` / `403` in the message → the asset is gated and no token was supplied. Say so and ask for the token; do not auto-recreate.
- Smoke job returns `FAILED` with `out of memory` → the GPU is too small for the real pattern; move up one GPU class and note the new hourly cost. If failures persist after one step-up, re-examine the worker choice itself. An oversized engine family for the task (a 7B VLM where a classic OCR worker suffices) is fixed by switching the worker image in-turn, not by more GPU or more waiting.
- Job stays `IN_QUEUE` / `IN_PROGRESS` past a hold → usually a cold start; keep blocking with `get-job-status wait:300000` on that job id (at most three holds, the playbook's phase 3), then report either the terminal result or the evidenced state. Hold server-side rather than handing the user a raw poll loop.
- Smoke job returns `400` / a payload-shape error → the input is wrong or a required model env was never set; re-read the release config, set the missing env or fix the payload shape to what the worker's config documents, and re-run. Do not stop and ask the user.
- Jobs go terminal almost instantly with empty or degraded output on a worker whose capability is token-gated → the gate is the first suspect, not the payload: read the job's `output`/`error` field verbatim and check whether the token env was set on the template/endpoint, before theorizing about input shape. Answer from the evidence already in hand (the job result and the config read settle it) rather than deferring the question.
- Create returns `409` (name collision) → append a fresh short suffix and retry once; if it still collides, surface it and stop.
- A GGUF repo fails to load on a vLLM worker → this is the wrong-engine case, not a stock or size problem; re-provision on a GGUF-capable worker.
- The Hub / community catalog returns nothing for the modality → report "none found on the catalog" and stop; do not fabricate a repo.
- A delete returns `204` with no body → that is success, not an error; confirm with a read-back.
