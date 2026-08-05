# Create a pod and wait until it is actually usable

## Prompt

Spin me up an A40 pod from `runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404` and
tell me when I can ssh into it.

## Expected behavior

The agent should:

1. Create with `runpodctl pod create --image ... --gpu-id "NVIDIA A40" --wait`, which returns
   only once port 22 answers with an ssh banner.
2. Read the printed payload (the `pod get` shape, so it carries the live `ssh` block) and give
   the user the ssh command.
3. NOT write its own poll loop around `pod get`/`ssh info`, and NOT treat
   `desiredStatus: RUNNING` as "ready" — that is true while the image is still pulling.
4. If the wait times out, recognise that the pod **was created and still bills**, take the id
   from the error object's `id` field, and offer to delete it.

## Assertions

- Uses `--wait` (optionally with `--wait-timeout`) rather than a hand-rolled polling loop
- Does not claim the pod is ready based on `desiredStatus` alone; if it inspects status, it reads `runtimeStatus`
- Reports the ssh connection details from the waited-for output
- On `wait_timeout` / `wait_interrupted`, surfaces the pod id from the error object and proposes cleanup instead of assuming nothing was created
