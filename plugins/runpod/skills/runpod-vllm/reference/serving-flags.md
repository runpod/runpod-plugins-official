---
concepts: [gpu-type, container-image, network-volume]
---

# vLLM serving flags

The flags that decide whether a model boots and how it serves. On a Pod or a load-balancing endpoint they go in `args` after the model id. On the Hub worker each flag is an env key: upper case, `-` becomes `_`.

| Flag | Hub worker env | What it does | How to set it |
|---|---|---|---|
| `--max-model-len N` | `MAX_MODEL_LEN` | longest prompt plus output, in tokens | Cap it to what the job needs. The KV cache must hold at least one sequence of this length, so a long native context on a small GPU fails the boot. |
| `--gpu-memory-utilization F` | `GPU_MEMORY_UTILIZATION` | share of VRAM vLLM takes for weights, activations and KV cache | `0.90`. Lowering it shrinks the KV cache, not the weights, so it does not fix a weights OOM. |
| `--tensor-parallel-size N` | `TENSOR_PARALLEL_SIZE` | splits each layer across N GPUs | = GPU count (1, 2, 4 or 8). |
| `--enable-expert-parallel` | `ENABLE_EXPERT_PARALLEL` | spreads MoE experts across the GPUs | Only for MoE models when the recipe says so. |
| `--enable-auto-tool-choice --tool-call-parser P` | `ENABLE_AUTO_TOOL_CHOICE`, `TOOL_CALL_PARSER` | OpenAI `tools` support | The parser comes from the model card or the vLLM recipe (`hermes` for Qwen3, `llama3_json` for Llama 3.x, `mistral` for Mistral). |
| `--reasoning-parser P` | `REASONING_PARSER` | moves the model's thinking out of `content` into its own field: `reasoning` in vLLM 0.32.0, `reasoning_content` in older versions | Reasoning models only (`qwen3`, `deepseek_r1`). Clients read both fields. |
| `--enable-prefix-caching` | `ENABLE_PREFIX_CACHING` | reuses the KV cache for shared prompt prefixes | On for chat and agents. |
| `--max-num-seqs N` | `MAX_NUM_SEQS` | most sequences per batch | Keep the default. Lower it when a hybrid or state-space model fails with a state-cache size error. |
| `--enforce-eager` | `ENFORCE_EAGER` | skips `torch.compile` and CUDA graphs | Faster boot, slower serving. Use it to fit a load-balancing health window, not by default. |
| `--quantization M` | `QUANTIZATION` | quantization method | Leave it off for a quantized checkpoint (FP8, AWQ, GPTQ): vLLM reads the method from the checkpoint. |
| `--kv-cache-dtype fp8` | `KV_CACHE_DTYPE` | halves the KV cache size | When the context does not fit; check output quality after. |
| `--served-model-name NAME` | `OPENAI_SERVED_MODEL_NAME_OVERRIDE` | the `model` value clients send | Optional; the default is the model id. |

## Env vars

| Env | Use |
|---|---|
| `HF_TOKEN` | gated weights and higher Hugging Face rate limits. Never print it. |
| `HF_HOME` | where weights download. Put it on persistent storage (`/workspace/...` on a Pod, `/runpod-volume/...` with a network volume) so a restart skips the download. |
| `VLLM_CACHE_ROOT` | where `torch.compile` artifacts go. On persistent storage, the second boot skips most of the compile. |
| `VLLM_API_KEY` | vLLM's own API key. Pods only; never on a load-balancing endpoint. |
| `NCCL_NVLS_ENABLE=0` | multi-GPU only, when NCCL init fails on a host whose CUDA already meets the image floor. |

## Sampling

A model's `generation_config.json` becomes the server's default sampling (vLLM logs `Using default sampling params from model`). Clients that need repeatable output send `temperature`, `top_p` and the other values the model card recommends on every request.

## Exact rules

- [gpu-type](../../runpod-usage/concepts/gpu-type.yaml) · [network-volume](../../runpod-usage/concepts/network-volume.yaml)
