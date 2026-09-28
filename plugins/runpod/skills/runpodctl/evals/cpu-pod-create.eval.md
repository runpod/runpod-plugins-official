# Create a CPU-only pod

## Prompt

Create a CPU-only pod for lightweight file preprocessing using the image
`ubuntu:22.04`. Give me the exact command.

## Expected behavior

The agent should:

1. Use `runpodctl pod create` with `--compute-type cpu`
2. Pass `--image ubuntu:22.04`
3. Explain that the default is 2 vCPUs and the CLI generates a name when omitted
4. NOT pass GPU flags (`--gpu-id`, `--gpu-count`) — they don't belong on a CPU pod

## Assertions

- Runs `runpodctl pod create --compute-type cpu --image ubuntu:22.04`
- States the 2-vCPU default and generated-name behavior
- Does NOT include `--gpu-id` or `--gpu-count`
