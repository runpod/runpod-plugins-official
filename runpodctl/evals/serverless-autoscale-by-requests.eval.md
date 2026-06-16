# Update a serverless endpoint to autoscale by pending requests

## Prompt

Update my serverless endpoint `ep-abc123` so it autoscales based on the number of
pending requests, triggering when there are 4 pending. Give me the exact command.

## Expected behavior

The agent should:

1. Identify that `runpodctl serverless update <endpoint-id>` is the right command
2. Use the v2.3 autoscaler flags `--scale-by requests` and `--scale-threshold 4`
3. NOT use the older `--scaler-type` / `--scaler-value` flags (removed in v2.3) or values like `REQUEST_COUNT` / `QUEUE_DELAY`

## Assertions

- Runs `runpodctl serverless update ep-abc123 ...`
- Sets `--scale-by requests` (strategy = pending request count)
- Sets `--scale-threshold 4`
- Does NOT use `--scaler-type`, `--scaler-value`, `REQUEST_COUNT`, or `QUEUE_DELAY`
