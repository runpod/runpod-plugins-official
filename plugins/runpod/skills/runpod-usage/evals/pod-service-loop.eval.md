# Stand up a service on a pod — the loop's load-bearing details

## Prompt

Stand up an Ollama server on a Runpod pod over SSH and give me the URL. Walk
through the commands.

## Expected behavior

Per `runpod-usage/reference/{pod-workflows.md,on-pod-setup.md}`:

1. **Ports + env at creation** — expose `11434/http` and set `OLLAMA_HOST=0.0.0.0`
   at `pod create` time (they can't be added to a running pod without a reset).
2. **Env isn't in the SSH shell** — when starting the service over SSH, pass the
   env explicitly (`env OLLAMA_HOST=0.0.0.0 … ollama serve`), because creation
   `--env` vars only reach PID 1.
3. **Detach the server** — start it with `setsid … < /dev/null &` so it survives
   the SSH channel closing, and return immediately.
4. **Verify from outside** — poll `https://<pod-id>-11434.proxy.runpod.net/api/tags`
   until 200 (expect warm-up 502s) before reporting the URL.
5. **Cost guard** — remove the pod when done (`runpodctl pod remove`). Never `--terminate-after` / `--stop-after`: they were never enforced and v2.12.0 removed them.

## Assertions

- Sets the port and env at `pod create` (not after).
- Passes env explicitly on the SSH-launched service command (doesn't rely on `--env` reaching the shell).
- Starts the server detached (`setsid`/`nohup` + `</dev/null`), not a bare `&`.
- Verifies by polling the proxy URL, and tells the user to remove the pod when done. Does NOT use `--terminate-after` / `--stop-after`.
