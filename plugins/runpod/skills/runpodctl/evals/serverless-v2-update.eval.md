# Update and inspect endpoints through the v2 control plane

## Prompt

My custom runpodctl build includes runpod/runpodctl#400. I set RUNPOD_API_URL to
my test API, but endpoint updates still reach production. Which setting should
I use? Give me commands to set ep-abc123's minimum workers to zero and change
only its scaling threshold to 4. Its queue-based sibling ep-requests uses
request-count scaling and prints idleTimeout: null. Should I read REST v1 or
set its idle timeout to zero?

## Expected behavior

The agent checks the build scope and reads the environment-variable and endpoint
update references. It directs the user to set RUNPOD_REST_V2_URL to the intended
v2 base, explains that the legacy REST override is independent, and leaves the
invocation and GraphQL hosts to their own overrides.

It uses `serverless update ep-abc123 --workers-min 0` and
`serverless update ep-abc123 --scale-threshold 4`. It explains that the second
command preserves the scaling strategy through a v2 read. The null idle timeout
is not applicable for the queue/request-count combination, so neither a v1
lookup nor an idle-timeout write is appropriate.

## Assertions

- Scopes the behavior to builds containing #400 without inventing a release floor.
- Names `RUNPOD_REST_V2_URL`, not `RUNPOD_API_URL`, as the v2 routing override.
- Does not assume changing a REST host moves GraphQL or invocation traffic.
- Sends zero minimum workers and verifies the result with `serverless get`.
- Uses `--scale-threshold 4` without guessing or changing the strategy.
- Interprets `idleTimeout: null` in JSON or YAML as not applicable, not zero.
- Does not call REST v1 or recommend `--idle-timeout` for ep-requests.

## Follow-up prompt

ep-abc123 uses a queue delay of 0.5 seconds. Can I switch to requests with only
`--scale-by requests`?

## Follow-up assertions

- Explains that a type-only update preserves the threshold and a fractional value
  cannot become a request count.
- Asks for a positive integer threshold, or uses one the user explicitly chooses.
- Uses `--scale-by requests --scale-threshold <count>` and verifies the read-back.
