# Routing: thousands of offline requests go to a batch, not a `/run` loop

## Prompt

My queue endpoint `ep-abc123` turns product descriptions into embeddings. I have 12,000
descriptions in a JSON file. Nobody is waiting on the results; I only need them by
tomorrow, as cheaply as possible. Set it up.

## Expected behavior

Routes through the router's capability matrix to batch jobs
([`runpod-usage/reference/batch-jobs.md`](../../runpod-usage/reference/batch-jobs.md))
rather than 12,000 `/run` calls or a `runpodctl serverless run` loop: the work is offline,
batches run on dedicated workers at a discounted rate, and they never take capacity from the
endpoint's interactive traffic.

1. Confirms `ep-abc123` is a queue endpoint by reading `type` (`QUEUE`) from `get-endpoint`
   or `GET https://api.runpod.io/v2/serverless/ep-abc123`; a load-balancing endpoint has no
   batch routes.
2. Checks one request's output first (`runsync-endpoint` or `runpodctl serverless run`), then
   runs a small test batch of about 100 requests to estimate cost, since no estimate is shown
   before a batch runs.
3. Splits the rest into batches of at most 5,000 requests (three for 12,000), within 10
   active batches per endpoint and 50,000 batch requests a day.
4. For each batch: `POST .../batch` with a top-level array of `{"input": {...}}` requests,
   appends with `.../requests` in calls of at most 10 MiB, then `.../finalize`. States that a
   `DRAFT` batch never runs.
5. Polls `GET .../batch/<batch-id>` until `status` is `COMPLETED`, `FAILED` or `CANCELLED`,
   pages `.../requests` while `hasMore` is true, reads `requestFailed`, and checks each
   `output` for errors the handler returned instead of raising.
6. Tells the user Runpod attempts each batch within 24 hours with no guaranteed start time.

## Assertions

- Uses the endpoint's `/batch` routes for the bulk work, not a loop of `/run`, `/runsync` or
  `runpodctl serverless run` calls
- Checks the session's tool list and `runpodctl --help` for a batch command before handing
  over `curl`, and does not invent an MCP batch tool
- Finalizes every batch, and says an unfinalized draft never runs
- Keeps each batch at or under 5,000 requests
- Treats `status`, not the request counts, as the signal that a batch is done, and reports
  `requestFailed` on a `COMPLETED` batch
- Runs a small test batch before the full set to estimate cost
