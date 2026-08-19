# Golden path 08 — fine-tune → serve (LoRA on a pod → serverless)

**Goal:** the smallest end-to-end **train-then-serve** loop: LoRA-fine-tune a tiny LLM
on a **pod** with axolotl, write the adapter to a **network volume**, then load base +
adapter from that same volume on a **serverless** endpoint and generate. Designed as a
fast/cheap validation that **scales to larger models by changing three things** (model id,
GPU, dataset) — nothing structural changes.
**Status:** COVERED — live-verified 2026-07-10 end to end. A pod LoRA-trained
TinyLlama-1.1B (loss 2.07→1.68, ~5 min incl. install + download), wrote the adapter to the
volume; a flash serverless worker then loaded base + adapter from `/runpod-volume` and
generated. The live run used a **minimal peft + transformers `Trainer`** script (below) —
it reuses the pod template's torch (no dependency fights) and is the fastest small-model
path; the **axolotl** flow is documented alongside it as the richer option for scaling.
Composes the verified network-volume handoff (golden path [07](07-network-volume-handoff.md)).
**Lane(s):** runpodctl (pod + volume) + flash (serverless) + Runpod MCP (`stream-worker-logs`, for diagnosis)

## The loop in one picture
```
[pod: axolotl train]  --writes-->  /workspace/outputs/lora-out   (network volume)
                                          | same volume, different mount path
[serverless worker]   --reads-->   /runpod-volume/outputs/lora-out  --> base+adapter --> generate
```
This is golden path 07's handoff with a LoRA adapter as the payload instead of a text file.
Read [07](07-network-volume-handoff.md) first — the `/workspace` (pod) vs `/runpod-volume`
(serverless) mount-path rule and the flash handler contract are the two things that bite.

## Why start tiny
Pick the **smallest model that proves the pipeline**, get the whole loop green, then scale
only the model id + GPU. Validation defaults:

| Knob | Validation value | Scale up by |
| --- | --- | --- |
| Base model | `TinyLlama/TinyLlama-1.1B-Chat-v1.0` (1.1B, ungated) | swap to Llama-3.1-8B, Qwen2.5-14B, … |
| GPU | one RTX 4090 (`ADA_24`) | bigger VRAM tier (see `../../runpod-usage/reference/gpu-selection.md`); QLoRA for memory |
| Dataset / steps | axolotl's bundled alpaca example, a few dozen steps | your dataset + full epochs |
| Serving | transformers + PEFT (simple) | vLLM with LoRA for throughput |

A 1.1B LoRA on a 4090 trains in **minutes** — fast enough to iterate the loop itself before
spending on a real run.

## Prerequisites
- `RUNPOD_API_KEY` resolvable; `runpodctl` + `flash` installed.
- An SSH key registered **before** creating the pod (`runpodctl ssh list-keys`; see
  `../../runpod-usage/reference/getting-started.md`).
- `HF_TOKEN` only if you scale to a **gated** base model (TinyLlama is ungated).

## 1. Storage — one volume, reused across both phases
```bash
runpodctl network-volume create --name ft-loop --size 30 --data-center-id <dc>
# → <vol-id>, pinned to <dc>. The pod AND the endpoint must run in this DC.
```

## 2. Train on a pod (axolotl → adapter on the volume)
```bash
runpodctl pod create --name ft-train \
  --template-id runpod-torch-v280 --gpu-id "NVIDIA GeForce RTX 4090" \
  --data-center-ids <dc> \
  --network-volume-id <vol-id> --volume-mount-path /workspace \
  --ssh --terminate-after <iso8601 a few hours out>          # no --ports: training serves nothing
```
Poll until the runtime is up, then read ip / port / key from `ssh info` into shell vars — the
SSH-over-TCP form from golden path [07](07-network-volume-handoff.md)/[06](06-dev-pod.md).
Every `ssh` below uses `"$IP"`/`"$PORT"`/`"$KEY"`:
```bash
runpodctl pod get <pod-id>                             # poll until it has a runtime
eval "$(runpodctl ssh info <pod-id> | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(f"IP={d[\"ip\"]} PORT={d[\"port\"]} KEY={d[\"ssh_key\"][\"path\"]}")')"
```
Two options for the training run itself:

**Option A — minimal `peft` + `transformers` Trainer (what the live run used; fastest, most
robust).** Reuses the template's torch, installs only `peft` + `datasets`, trains ~20 steps
on a 200-row slice of `mhenrichsen/alpaca_2k_test`. Whole thing (install + download + train)
ran in **~5 min** on one 4090:
```bash
export HF_HOME=/workspace/hf-cache                     # cache base model on the VOLUME (reused at serve)
pip install --break-system-packages -q peft datasets
python3 - <<'PY'
import torch
from datasets import load_dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer, TrainingArguments,
                          Trainer, DataCollatorForLanguageModeling)
from peft import LoraConfig, get_peft_model
BASE="TinyLlama/TinyLlama-1.1B-Chat-v1.0"; OUT="/workspace/outputs/lora-out"
tok=AutoTokenizer.from_pretrained(BASE); tok.pad_token=tok.eos_token
ds=load_dataset("mhenrichsen/alpaca_2k_test", split="train[:200]")
def f(ex): return tok([f"### Instruction:\n{i}\n\n### Response:\n{o}{tok.eos_token}"
                       for i,o in zip(ex["instruction"],ex["output"])], truncation=True, max_length=256)
ds=ds.map(f, batched=True, remove_columns=ds.column_names)
m=get_peft_model(AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16),
    LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj","v_proj"], task_type="CAUSAL_LM"))
Trainer(model=m, args=TrainingArguments(output_dir=OUT, max_steps=20, per_device_train_batch_size=2,
    logging_steps=1, save_strategy="no", fp16=True, report_to=[]), train_dataset=ds,
    data_collator=DataCollatorForLanguageModeling(tok, mlm=False)).train()
m.save_pretrained(OUT); tok.save_pretrained(OUT); print("TRAIN_DONE")
PY
```
For a real (longer) run, don't paste it interactively — **write it to `/workspace/train.py`**,
launch it **detached** so it survives SSH disconnect, and poll the log (same pattern as golden
path [04](04-finetune-pod.md)):
```bash
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" \
  'export HF_HOME=/workspace/hf-cache; pip install --break-system-packages -q peft datasets'
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" 'cat > /workspace/train.py' <<'PY'
import torch
from datasets import load_dataset
from transformers import (AutoModelForCausalLM, AutoTokenizer, TrainingArguments,
                          Trainer, DataCollatorForLanguageModeling)
from peft import LoraConfig, get_peft_model
BASE="TinyLlama/TinyLlama-1.1B-Chat-v1.0"; OUT="/workspace/outputs/lora-out"
tok=AutoTokenizer.from_pretrained(BASE); tok.pad_token=tok.eos_token
ds=load_dataset("mhenrichsen/alpaca_2k_test", split="train[:200]")
def f(ex): return tok([f"### Instruction:\n{i}\n\n### Response:\n{o}{tok.eos_token}"
                       for i,o in zip(ex["instruction"],ex["output"])], truncation=True, max_length=256)
ds=ds.map(f, batched=True, remove_columns=ds.column_names)
m=get_peft_model(AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16),
    LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj","v_proj"], task_type="CAUSAL_LM"))
Trainer(model=m, args=TrainingArguments(output_dir=OUT, max_steps=20, per_device_train_batch_size=2,
    logging_steps=1, save_strategy="no", fp16=True, report_to=[]), train_dataset=ds,
    data_collator=DataCollatorForLanguageModeling(tok, mlm=False)).train()
m.save_pretrained(OUT); tok.save_pretrained(OUT); print("TRAIN_DONE")
PY
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" \
  'export HF_HOME=/workspace/hf-cache; \
   setsid bash -c "python3 /workspace/train.py" > /workspace/train.log 2>&1 </dev/null & echo LAUNCHED'
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" 'tail -n 30 /workspace/train.log'
```

**Option B — axolotl (richer config-driven flow, for scaling).** Heavier install; pin the
config's `flash_attention:false` if you skip flash-attn:
```bash
export HF_HOME=/workspace/hf-cache
pip install --break-system-packages "axolotl[flash-attn]" || pip install --break-system-packages axolotl
axolotl fetch examples
axolotl train examples/tiny-llama/lora.yml --output_dir /workspace/outputs/lora-out
```
Success = the log ends with a "training complete / saving model" line and the adapter files
exist: `ls /workspace/outputs/lora-out` shows `adapter_config.json` + `adapter_model.safetensors`.
Then free the GPU — the volume keeps the adapter:
```bash
runpodctl pod remove <pod-id>
```
> Training is a **batch job**, not a server: monitor by tailing the log, not by polling a URL
> (golden path [04](04-finetune-pod.md)). Launch it detached (`setsid … </dev/null &`) for a
> long run so it survives SSH disconnect.

## 3. Serve on serverless (load base + adapter from `/runpod-volume`)
A flash endpoint attaches the **same volume** and loads the adapter once per worker.
Mind the two things from 07: mount path is `/runpod-volume`, and the handler is called as
`handler(**job_input)` (use `**kwargs`; empty input is rejected).

This is the exact handler that ran. Note the flash rules from 07: **function** handler with a
`global` cache loaded once per worker (only the function *body* ships to the worker, so load
inside it, not at module level), `**kwargs`, and paths inlined (module-level constants don't
ship):
```python
# main.py
from runpod_flash import Endpoint, GpuGroup, DataCenter, NetworkVolume

vol = NetworkVolume(id="<vol-id>", datacenter=DataCenter.EU_RO_1)   # the SAME volume

@Endpoint(name="ft-serve", gpu=GpuGroup.ADA_24, workers=(0, 1), idle_timeout=60,
          datacenter=DataCenter.EU_RO_1, volume=vol,
          env={"HF_HOME": "/runpod-volume/hf-cache"},          # reuse training's base-model cache
          dependencies=["torch", "transformers", "peft", "accelerate"])
async def generate(**kwargs) -> dict:                          # flash spreads input as kwargs
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    global _M, _T
    try:
        _M
    except NameError:                                          # load once per worker
        _T = AutoTokenizer.from_pretrained("/runpod-volume/outputs/lora-out")
        base = AutoModelForCausalLM.from_pretrained(
            "TinyLlama/TinyLlama-1.1B-Chat-v1.0", torch_dtype=torch.float16).to("cuda")
        _M = PeftModel.from_pretrained(base, "/runpod-volume/outputs/lora-out").eval()
    text = f"### Instruction:\n{kwargs.get('prompt', 'Hello')}\n\n### Response:\n"
    ids = _T(text, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = _M.generate(**ids, max_new_tokens=int(kwargs.get("max_new_tokens", 64)), do_sample=False)
    return {"output": _T.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)}
```
```bash
RUNPOD_API_KEY=... flash deploy
runpodctl serverless list        # confirm the endpoint's networkVolumeId == <vol-id>
```

## 4. Verify with a real request
Send a **non-empty** input (empty `{}` is rejected — see 07):
```bash
curl -s https://api.runpod.ai/v2/<endpoint-id>/run -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"input":{"prompt":"Give me one tip about GPUs."}}'    # then poll /status/<job-id>
```
Verified result (2026-07-10): cold call `COMPLETED` in ~48 s queue + 9.7 s exec (fast — the
base model was already cached on the volume from training), output:
```json
"output": {"output": "Sure, here's a tip for training LLMs:\n\n1. Start with small models: ..."}
```
Green when the first (cold) call returns generated text. The pipeline is proven; now scale.

## Scaling to a larger model (what changes — and what doesn't)
**Changes:** `BASE` (model id in the axolotl config + the serve handler), the `--gpu-id` /
`GpuGroup` to a bigger-VRAM tier, and dataset/steps. Add `HF_TOKEN` for gated models. Use
**QLoRA** (axolotl `load_in_4bit: true`) when the base won't fit for full LoRA.
**Doesn't change:** the loop — one volume, pod writes the adapter to `/workspace/outputs`,
serverless reads it from `/runpod-volume/outputs`, same DC, `**kwargs` handler, non-empty
input. For high-throughput serving, swap the transformers handler for **vLLM with LoRA**
(load the base once, hot-swap adapters) — same volume handoff.

## Cost & cleanup
```bash
runpodctl serverless delete <endpoint-id>     # (undeploy+redeploy for fresh workers if a code change is stuck — see 07)
runpodctl network-volume delete <vol-id>      # pod already removed; deletes the adapter + cache
```
Pod cost guard: `--terminate-after` (deletes the pod), not `--stop-after`. Endpoint is
scale-to-zero (`workers=(0,1)`), ~$0 idle. Keep the volume only while iterating.

## Gotchas this path inherits
- **Mount-path swap:** `/workspace` on the pod == `/runpod-volume` on serverless — same volume,
  different path ([07](07-network-volume-handoff.md), `storage.md`).
- **flash handler contract:** `handler(**job_input)` — use `**kwargs`; invoke with non-empty
  `input` (flash SKILL gotcha "Request body shape").
- **Load the model once** in the class `__init__`, not per request (flash SKILL gotcha).
- **PEP 668** on the training pod: `pip install --break-system-packages …` (`on-pod-setup.md`).
- **Diagnosis:** if the endpoint job times out, pull worker logs before assuming a broken
  worker — it's usually a payload/handler issue. `runpodctl serverless logs <id> --source
  container` (v2.10.0+) or MCP `stream-worker-logs`.
- **Same DC** for volume + pod + endpoint (the volume is DC-pinned).
