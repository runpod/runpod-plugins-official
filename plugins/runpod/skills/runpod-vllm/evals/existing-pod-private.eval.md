# vLLM on a Pod the user already runs stays private and pinned

## Prompt

I have a running A40 Pod on the PyTorch template and a shell on it. Install vLLM on it and
serve `Qwen/Qwen2.5-0.5B-Instruct` so only processes on the Pod can call it. Prove it works.
Do not create a new Pod.

## Expected behavior

Per `runpod-vllm/reference/existing-pod.md`:

1. Writes the full plan first (install, download, check, serve, verify, stop) with a deadline
   on each step, and creates no Pod.
2. Compares the torch version the chosen vLLM release needs with the base image's torch, and
   installs into a fresh venv when they differ. It does not install into the system Python.
3. Downloads the model files from an exact revision (a commit, not `main`) and checks each
   file's SHA-256 on the Pod.
4. Serves with `--host 127.0.0.1` on a port the Pod does not expose, with a generated key in
   the `VLLM_API_KEY` environment variable, never on the command line, and never printed.
5. Verifies three things on the Pod: a missing and a wrong key both get 401, one small chat
   request returns 200 with its actual text quoted, and `vllm:request_success_total` equals
   the number of requests sent.
6. Stops the server and says that Pod billing continues until the user stops the Pod.

## Assertions

- No `create-pod` call and no change to the Pod's exposed ports.
- The install command pins `vllm==<version>`; the model URL contains a commit hash.
- The serve command binds `127.0.0.1` and has no `--api-key` argument.
- The answer reports both 401 results, the 200 result and the metrics count.
