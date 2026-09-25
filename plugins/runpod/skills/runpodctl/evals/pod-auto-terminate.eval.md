# Create a pod that auto-terminates at a datetime

## Prompt

Create a GPU pod from the Docker image `myorg/trainer:latest` that automatically
terminates itself at 2026-07-01T00:00:00Z. Give me the exact command.

## Expected behavior

The agent should:

1. Use `runpodctl pod create` with `--image myorg/trainer:latest`
2. Not use `--terminate-after` or `--stop-after`. runpodctl before v2.12.0 accepts them, but the backend never enforced them, and v2.12.0 removed them
3. Tell the user the pod will not delete itself at that time, and offer a working alternative: `runpodctl pod remove <pod-id>` when the work is done, or a stop scheduled from inside the pod
4. Tell a user on runpodctl older than v2.12.0 to run `runpodctl update`

## Assertions

- Runs `runpodctl pod create --image myorg/trainer:latest ...`
- Does NOT use `--terminate-after` or `--stop-after`
- States that the flags never enforced the deadline and were removed in v2.12.0
- Gives `runpodctl pod remove <pod-id>` or an in-pod scheduled stop as the alternative
