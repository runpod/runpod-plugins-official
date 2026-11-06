---
concepts: [pod, exposed-port, container-image, gpu-type, pod-volume-disk]
---

# vLLM on a Pod

A Pod runs the stock `vllm/vllm-openai` image. The image's entrypoint is `vllm serve`, so the Pod's `args` are the `vllm serve` arguments: the model id first, then the flags. Use a Pod for a server the user keeps, for debugging a boot, and as the first stop for a new or very large model. A Pod has no health watchdog, so a long first boot (download, `torch.compile`, CUDA graph capture) is fine.

## Create it in one call

`create-pod` takes the image, the arguments, the env, the ports and the CUDA floor together. A template is optional.

```json
{
  "name": "vllm-qwen3-8b",
  "image": "vllm/vllm-openai:v0.32.0",
  "args": "Qwen/Qwen3-8B --max-model-len 8192 --gpu-memory-utilization 0.90 --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3 --enable-prefix-caching",
  "env": { "VLLM_API_KEY": "<random 48-hex secret>", "HF_HOME": "/workspace/hf" },
  "disk": 30,
  "mounts": { "persistent": { "size": 40, "path": "/workspace" } },
  "ports": ["8000/http"],
  "gpu": { "id": "NVIDIA A40", "count": 1, "minCudaVersion": "13.0" },
  "cloud": "SECURE"
}
```

- **Image tag.** Pin a version tag (`v0.32.0`), never `latest`. Pick the tag that the model needs, from the model card or the vLLM recipe.
- **`VLLM_API_KEY`.** The proxy URL is public. vLLM reads the key from this env var, so it never appears in `args` or the process list. Generate it locally (`python3 -c 'import secrets; print(secrets.token_hex(24))'`) and never print it in the answer.
- **`HF_HOME` on the volume disk.** Weights go to `/workspace/hf`, so a stop and start skips the download. Size the volume disk for the weights plus about 25 %. Gated weights need `HF_TOKEN` in `env`.
- **Container disk.** 30 GB is enough when the weights live on the volume disk. Without a volume disk, size the container disk for the weights plus 20 GB.
- **Ports.** `8000/http` only. The stock image runs only `vllm serve` and starts no SSH server, so `22/tcp` gives no shell; read the boot with `stream-pod-logs`. A user who needs a shell needs an image that also starts `sshd`.
- **CUDA floor.** `vllm/vllm-openai:v0.32.0` needs `cuda>=13.0` (`NVIDIA_REQUIRE_CUDA` in the image config; read it for other tags). Read Pod stock at that floor with `get-capacity` (`cudaVersions`) before the create: stock without a CUDA filter can be on hosts the floor excludes.
- **Multi-GPU.** Set `gpu.count` and `--tensor-parallel-size` to the same value.

The create returns `cudaVersion`: confirm it meets the floor.

## Watch the boot

Read `stream-pod-logs` in short steps (`tail` 40, `maxWaitMs` a few seconds). The milestones, in order:

1. `non-default args: {...}`: the flags vLLM received. Check them now.
2. `Resolved architecture: ...` and `Using max model len ...`.
3. `Loading weights took ...` and the KV cache size line.
4. `torch.compile` and CUDA graph capture lines (the slowest step on the first boot).
5. `Application startup complete.`

Failures and fixes: [boot-log-triage.md](boot-log-triage.md).

## Call it

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://<pod-id>-8000.proxy.runpod.net/v1",
                api_key=os.environ["VLLM_API_KEY"])
```

Then run [`scripts/test_endpoint.py`](../scripts/test_endpoint.py) against the same base URL.

## Stop or delete

Stopping keeps the volume disk (and the cached weights) and bills only for it. Deleting removes everything. Delete a Pod made for a test in the same session and confirm with `list-pods`.

## Exact rules

- [pod](../../runpod-usage/concepts/pod.yaml) · [exposed-port](../../runpod-usage/concepts/exposed-port.yaml) · [pod-volume-disk](../../runpod-usage/concepts/pod-volume-disk.yaml)
