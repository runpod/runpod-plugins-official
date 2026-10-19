# Image construction, startup and model cache integration

These are manual review scenarios, not an automated test suite.

## Prompt

"I have a Runpod PyTorch image and want a Pod with SSH plus my HTTP app. I currently
replace CMD with a Python script that prints CUDA information and exits. Can you fix
the startup and speed up rebuilds? I use Windows and Docker may already be in WSL."

## Expected behavior

- Preserve the selected base's `/start.sh` and explain its SSH/key/service startup.
- Give a concrete `/post_start.sh` hook or a long-running app startup pattern, and
  distinguish a successful one-shot check from a usable running pod.
- Check actual SSH and HTTP readiness rather than treating a fixed sleep as proof.
- Keep the dependency install before changing code, retain a published base tag and
  digest, and distinguish build cache reuse from deployment-host layer residency.
- Inspect existing native/WSL/remote Docker and its daemon before installation.
  If selecting a missing WSL2 setup, retain the `wsl --install` route.
- For a new Windows installation, install and launch Docker Desktop before enabling
  distribution integration and checking `docker info` in that distribution.
- For local Linux Docker Engine permission errors, explain the optional `docker`
  group command, its root-level privileges, and logging out and back in before
  verifying access. Do not apply host installation steps to a Runpod pod.

## Additional prompts

1. "My queue worker uses Transformers. Does attaching the cached model make it load
   automatically, and is HF_HOME the same as my downloaded model folder?"
2. "For my load-balanced API, should I test handler.py through the queue job API?"
3. "Can I copy all of PyTorch to my network volume each startup to improve startup?"

## Assertions

- A custom handler configures its cache or resolves a matching snapshot. Explain
  `HF_HOME` versus `HF_HUB_CACHE` and a plain local model directory. Cite the public
  cache integration docs; do not assert an unverified relationship between `MODEL_NAME`
  and the endpoint's Model field.
- Queue testing uses a local handler input; load-balanced testing hits HTTP routes and
  follows GP14. Do not add SSH, exposed ports or a pod proxy to a queue endpoint.
- Preserve immutable runtime layers outside mounts and persist mutable application
  data deliberately. Explain local-image versus network-volume I/O and the training
  storage tradeoff, linking GP25/GP21 without reclassifying their live-verified results.
