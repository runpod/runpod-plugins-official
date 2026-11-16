---
concepts: [batch-job, serverless-endpoint, job]
---

# Batch jobs

A batch is a set of requests submitted to a **queue-based** endpoint as one unit. It runs
asynchronously on dedicated batch workers, so it never takes capacity from the endpoint's
`/run` traffic, and you read the results back per request. Load-balancing endpoints have no
batch routes.

## Batch or `/run`?

| | Batch | `/run` / `/runsync` |
| --- | --- | --- |
| Use for | Bulk, offline work: nightly dataset runs, embeddings, evaluations | Anything a user is waiting on |
| Latency | Hours; Runpod attempts each batch within 24 hours, with no guaranteed start | Seconds to minutes |
| Workers | Dedicated batch workers, on the endpoint's GPU type | The endpoint's workers |
| Results | Poll the batch, or the terminal notification | The job's `/status` |

Batch requests bill for the compute time each one uses, at a discounted rate. No estimate is
shown before a batch runs, so run a small test batch first (about 100 requests) and
extrapolate before submitting the rest.

## Which lane

The batch routes sit on the serverless API host next to `/run`
(`https://api.runpod.ai/v2/<endpoint-id>/batch`) and take the same API key. The
[router capability matrix](../../runpod/SKILL.md#runpod-mcp-vs-runpodctl-the-overlap) picks
the lane for the batch calls and for creating the endpoint and testing one request. Each
request in a batch has the same `{"input": {...}}` shape as a `/run` body.

## Run a batch

```bash
EP=https://api.runpod.ai/v2/<endpoint-id>
AUTH="Authorization: Bearer $RUNPOD_API_KEY"

# 1. Create it with a first set of requests (a top-level array; [] for an empty draft) -> {"id", "status":"DRAFT"}
curl -s -X POST "$EP/batch" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '[{"input":{"text":"first"}},{"input":{"text":"second"}}]'

# 2. Append more while it is a draft, up to 10 MiB per call
curl -s -X POST "$EP/batch/<batch-id>/requests" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"requests":[{"input":{"text":"third"}}]}'

# 3. Finalize: locks the requests and starts processing. A DRAFT batch never runs.
curl -s -X POST "$EP/batch/<batch-id>/finalize" -H "$AUTH"

# 4. Progress: status plus requestTotal / requestInProgress / requestCompleted / requestFailed
curl -s "$EP/batch/<batch-id>" -H "$AUTH"

# 5. Results, paged while hasMore is true
curl -s "$EP/batch/<batch-id>/requests?offset=0&limit=50" -H "$AUTH"
```

- **Done is `status`, not the counts.** The batch stays `FINALIZED` while requests run and
  turns `COMPLETED` when every request has finished. `COMPLETED` can include failures, so read
  `requestFailed`. `FAILED` and `CANCELLED` are the other terminal states.
- **Check each output.** A handler that returns an error instead of raising marks its request
  `COMPLETED`. Raised errors show as `FAILED` with the handler's `error` text.
- **Other routes:** `GET $EP/batch` lists the endpoint's batches, newest first; `PUT
  $EP/batch/<batch-id>` sets attributes such as the name; `DELETE
  $EP/batch/<batch-id>/requests/<request-id>` removes one request from a draft.
- **Notifications:** at a terminal state Runpod sends one console Inbox notification and, with
  a webhook subscription for batch events, one webhook event. Progress is read by polling.

## Limits and failures

- An endpoint holds at most 10 active batches, a batch at most 5,000 requests, and an
  endpoint runs at most 50,000 batch requests a day (support or sales can raise the daily
  limit). Split larger workloads across batches and days.
- Requests run in no particular order, on the endpoint's GPU type; there is no per-batch GPU
  choice.
- A batch fails once failed requests reach 10 or 2% of its requests (rounded up), whichever is
  greater, and the remaining requests do not run:

  | `failureCode` | What to do |
  | --- | --- |
  | `REQUEST_FAILURE_LIMIT` | Read the failed requests' errors, fix the handler or inputs, submit a new batch |
  | `ALL_BATCH_WORKERS_UNHEALTHY` | No batch worker started; check the endpoint's configuration and the logs of the workers in `failedWorkerIds` |

- **Cancel:** `POST $EP/batch/<batch-id>/cancel`. Queued requests are cancelled at once and not
  billed; in-progress requests finish and are billed, then the batch turns `CANCELLED`.

## Exact rules

These facts come from [`batch-job`](../concepts/batch-job.yaml), which cites the public batch
jobs page, and [`job`](../concepts/job.yaml) for the request shape a batch reuses.
