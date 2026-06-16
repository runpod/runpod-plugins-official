# Create a CPU-only pod

## Prompt

Create a CPU-only pod for lightweight file preprocessing using the image
`ubuntu:22.04`. Give me the exact command.

## Expected behavior

The agent should:

1. Use `runpodctl pod create` with `--compute-type cpu`
2. Pass `--image ubuntu:22.04`
3. NOT pass any GPU flags (`--gpu-id`, `--gpu-count`) — they don't belong on a CPU pod

## Assertions

- Runs `runpodctl pod create --compute-type cpu --image ubuntu:22.04`
- Does NOT include `--gpu-id` or `--gpu-count`
