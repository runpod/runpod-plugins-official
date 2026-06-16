# Run a custom image as a serverless endpoint (template first)

## Prompt

I have my own custom Docker image `myrepo/infer:latest`. I want to run it as a
Runpod serverless endpoint that scales from 0 to 3 workers on an A40 GPU. Give me
the exact commands.

## Expected behavior

The agent should:

1. Recognize that serverless endpoints are created from a `--template-id` or `--hub-id`, NOT directly from a raw image
2. First create a serverless template: `runpodctl template create --name ... --image myrepo/infer:latest --serverless`
3. Then create the endpoint from that template id: `runpodctl serverless create --template-id <id> --workers-min 0 --workers-max 3 ...`
4. Order the two steps correctly (template before endpoint)

## Assertions

- Step 1 creates a template with `runpodctl template create --image myrepo/infer:latest --serverless`
- Step 2 creates the endpoint with `runpodctl serverless create --template-id <id-from-step-1>`
- Sets `--workers-min 0` and `--workers-max 3`
- Does NOT attempt `runpodctl serverless create --image ...` (no `--image` flag exists on serverless create)

## Notes

The template-id path is more lenient about `--gpu-id` than the hub path (it accepts
display names like `"NVIDIA A40"`), but see hub-deploy-serverless.eval.md and
runpod/runpodctl#287 for the pool-id inconsistency.
