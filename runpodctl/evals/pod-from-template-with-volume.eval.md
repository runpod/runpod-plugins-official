# Create a pod from a template with a network volume

## Prompt

Create a GPU pod named `trainer` from template id `tmpl-1`, and attach the network
volume with id `nv-9`. Give me the exact command.

## Expected behavior

The agent should:

1. Use `runpodctl pod create` with `--template-id tmpl-1`
2. Set `--name trainer`
3. Attach the volume with `--network-volume-id nv-9`
4. Not need any extra GPU flag, since GPU is the default compute type

## Assertions

- Runs `runpodctl pod create ...`
- Uses `--template-id tmpl-1`
- Uses `--name trainer`
- Uses `--network-volume-id nv-9`
