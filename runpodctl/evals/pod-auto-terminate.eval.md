# Create a pod that auto-terminates at a datetime

## Prompt

Create a GPU pod from the Docker image `myorg/trainer:latest` that automatically
terminates itself at 2026-07-01T00:00:00Z. Give me the exact command.

## Expected behavior

The agent should:

1. Use `runpodctl pod create` with `--image myorg/trainer:latest`
2. Use the `--terminate-after` flag with the given datetime
3. Choose `--terminate-after` (deletes the pod) over `--stop-after` (only stops it), since the user asked for termination
4. Recognize this flag exists rather than declaring it impossible

## Assertions

- Runs `runpodctl pod create --image myorg/trainer:latest ...`
- Uses `--terminate-after 2026-07-01T00:00:00Z`
- Does NOT use `--stop-after` for this request
- Does NOT claim auto-termination is unsupported
