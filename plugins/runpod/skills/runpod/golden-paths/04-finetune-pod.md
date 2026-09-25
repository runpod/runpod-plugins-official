# Golden path 04 — LoRA fine-tune (training run) on a pod

**Goal:** the standalone **training half** — LoRA-fine-tune a small LLM on a GPU
**pod**, persist the adapter to a **network volume**, then free the GPU (the volume
keeps the adapter). This is a **batch job**, not a server: no port, no proxy URL —
success is "training finished + adapter on the volume", verified by tailing a log.
Serving the adapter is out of scope here (that's golden path
[08](08-finetune-to-serverless.md); the volume handoff mechanics are
[07](07-network-volume-handoff.md)).
**Status:** COVERED — training phase live-verified 2026-07-10. This exact
train-to-volume run was executed as the **train phase of golden path
[08](08-finetune-to-serverless.md)** on 2026-07-10: a pod LoRA-trained
`TinyLlama/TinyLlama-1.1B-Chat-v1.0` with a **minimal peft + transformers
`Trainer`** script (loss **2.07 → 1.68** over 20 steps, **~5 min** incl. install +
model download on one RTX 4090 in EU-RO-1), writing `adapter_config.json` +
`adapter_model.safetensors` to `/workspace/outputs/lora-out` on a network volume.
No fresh pod was run for this doc — it's the same evidence, scoped to just the
training run. The serve half is proven separately in 08.
**Lane(s):** runpodctl (pod + network volume) + SSH-exec (batch training)

## When to use this
You want to **produce a trained artifact**, not stand up a service: fine-tune an
adapter, preprocess/convert a model, or run any long GPU batch job whose output is
files on a volume. The shape differs from a server path (01/02) at both ends —
**nothing is exposed** (no `--ports`, no `0.0.0.0` bind, no proxy poll), and
**"done" is a log line + files on the volume**, not an HTTP 200.

If your end goal is to *serve* the adapter afterwards, do this path first, then
follow [08](08-finetune-to-serverless.md) (train → serve loop) — 08 reuses this
exact training step and adds a serverless reader on the same volume.

## Batch job vs. server — the distinction that shapes everything
| | This path (batch job) | A server path (01/02) |
| --- | --- | --- |
| Exposes a port? | **No** — omit `--ports` | Yes — `--ports 'N/http'` |
| "Ready" means | log shows falling loss → final save line; files on volume | proxy URL answers a real request |
| How you monitor | **tail the log** in separate SSH calls | poll the proxy URL |
| Survives SSH drop | must **detach** (`setsid … </dev/null &`) | server process already detached |
| Deliverable | adapter files on the **volume** (outlive the pod) | a live endpoint |

## Prerequisites
- `RUNPOD_API_KEY` resolvable; `runpodctl` installed.
- An SSH key registered **before** creating the pod (`runpodctl ssh list-keys`;
  see [`../../runpod-usage/reference/getting-started.md`](../../runpod-usage/reference/getting-started.md)).
- `HF_TOKEN` only if you scale to a **gated** base model — TinyLlama is ungated, so
  the verified run needed none.

## Walkthrough (verified commands)

### 1. Create the volume (holds the adapter + model cache; persists past the pod)
```bash
runpodctl network-volume create --name ft-train --size 30 --data-center-id EU-RO-1
# → <vol-id>, pinned to EU-RO-1. The pod MUST run in this DC (volumes are DC-locked).
```

### 2. Provision a training pod — GPU, PyTorch template, volume, SSH, cost guard
No `--ports`: a training run serves nothing.
```bash
runpodctl pod create --name ft-train \
  --template-id runpod-torch-v280 --gpu-id "NVIDIA GeForce RTX 4090" \
  --data-center-ids EU-RO-1 \
  --network-volume-id <vol-id> --volume-mount-path /workspace \
  --ssh

runpodctl pod get <pod-id>                              # poll until it has a runtime
# once the runtime is up, read ip / port / key from `ssh info` (JSON) into shell vars —
# the SSH-over-TCP form golden paths 06/07 use. Every ssh/scp below uses "$IP"/"$PORT"/"$KEY":
eval "$(runpodctl ssh info <pod-id> | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print(f"IP={d[\"ip\"]} PORT={d[\"port\"]} KEY={d[\"ssh_key\"][\"path\"]}")')"
# → IP=213.173.108.151 PORT=17740 KEY=/Users/you/.runpod/ssh/RunPod-Key-Go
```
> A brand-new pod can draw a bad machine where the runtime never becomes ready
> (`ssh info` stays "pod not ready", `runtime: false`). Delete it and create a
> fresh one rather than waiting indefinitely (learned in 07).

### 3. Train — minimal `peft` + `transformers` Trainer (Option A, what ran)
This is the primary, fastest, most robust path: it **reuses the template's torch**
(no dependency fights), installs only `peft` + `datasets`, and trains 20 steps on a
200-row slice of `mhenrichsen/alpaca_2k_test`. Cache the base model on the
**volume** (`HF_HOME=/workspace/hf-cache`) so a restart — or a later serve step —
doesn't re-download. Run it over SSH:
```bash
export HF_HOME=/workspace/hf-cache                     # cache base model on the VOLUME
pip install --break-system-packages -q peft datasets   # PEP 668: into the template torch
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
For a **real** run (longer than a few minutes), don't paste the script interactively —
**write it to the volume as `/workspace/train.py`**, launch it **detached** so it survives
SSH disconnect, and monitor by tailing the log in separate calls:
```bash
# 1. install deps, then write the SAME script (above) to a file on the volume
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

# 2. launch detached, logging to the VOLUME (setsid + </dev/null survive SSH disconnect)
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" \
  'export HF_HOME=/workspace/hf-cache; \
   setsid bash -c "python3 /workspace/train.py" > /workspace/train.log 2>&1 </dev/null & echo LAUNCHED'

# 3. monitor in SEPARATE calls — loss trends down, final line is TRAIN_DONE
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" 'tail -n 30 /workspace/train.log'
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" \
  'nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv'
```
> Monitor by **tailing the log**, not by polling a URL — there is no URL. A run
> that finishes in seconds with no adapter files is a failure, not a success.

**Option B — axolotl (config-driven, for scaling up).** Heavier install; use it
when you outgrow the minimal script (multi-GPU, richer configs, QLoRA). Pin
`flash_attention: false` in the config if you skip flash-attn:
```bash
export HF_HOME=/workspace/hf-cache
pip install --break-system-packages "axolotl[flash-attn]" || pip install --break-system-packages axolotl
axolotl fetch examples
axolotl train examples/tiny-llama/lora.yml --output_dir /workspace/outputs/lora-out
```
Same contract either way: outputs land under `/workspace/outputs/lora-out` on the
volume.

## Verify it works (the actual test + observed output)
Success = the adapter files exist on the volume:
```bash
ssh -i "$KEY" -o StrictHostKeyChecking=no -p "$PORT" root@"$IP" 'ls -la /workspace/outputs/lora-out'
```
**Verified (2026-07-10, as the train phase of golden path 08):** on one RTX 4090
in EU-RO-1, the whole thing (install `peft`+`datasets` + download TinyLlama + train
20 steps) ran in **~5 min**; training loss fell **2.07 → 1.68**; the script printed
`TRAIN_DONE` and `ls` showed:
```
adapter_config.json
adapter_model.safetensors
```
Those files are the deliverable — they persist on the volume independent of the
pod. (08 then loaded base + this adapter from the same volume on a serverless
worker and generated text — proof the artifact is usable downstream.)

## Free the GPU (the volume keeps the adapter)
Once the files are confirmed on the volume, remove the pod — you stop paying for
the GPU immediately, and the adapter survives on the volume:
```bash
runpodctl pod remove <pod-id>          # volume (with the adapter + model cache) persists
runpodctl network-volume list          # confirm the volume is still listed
```

## Gotchas this path must respect
- **Size VRAM for training, not inference.** Full fine-tuning ≈ weights + gradients
  + optimizer state + activations (~4× the inference figure); LoRA/QLoRA cut this a
  lot (the 1.1B LoRA fit comfortably on a 4090). If a bigger model OOMs, escalate
  to a bigger tier or enable QLoRA — don't silently retry
  ([`gpu-selection.md`](../../runpod-usage/reference/gpu-selection.md)).
- **PEP 668 / template torch.** Official PyTorch templates keep torch in the
  **system** Python; `pip install` needs `--break-system-packages`. Install into
  the existing interpreter — a fresh `uv venv` won't inherit torch
  ([`on-pod-setup.md`](../../runpod-usage/reference/on-pod-setup.md)).
- **Detach long runs.** A plain `&` dies on SSH disconnect (SIGHUP). Use
  `setsid … </dev/null &` and monitor in separate SSH calls; don't `sleep` in the
  launch invocation.
- **Persist everything on the volume.** Base model + dataset cache (`HF_HOME` →
  `/workspace/hf-cache`) and `--output_dir`/`OUT` under `/workspace/outputs`.
  Container disk is wiped on stop/terminate ([`storage.md`](../../runpod-usage/reference/storage.md)).
- **Volume ↔ GPU same DC.** A network volume is DC-locked; create the pod in the
  volume's DC or scheduling fails.
- **Gated base model / dataset** needs `HF_TOKEN` + an accepted license (a manual
  step). If `hf download` 401/403s, **stop and ask** for the token/license —
  TinyLlama + the alpaca test set are ungated, so the verified run needed neither.
- **Remove the pod as soon as the run finishes.** It bills until removed. Don't use
  `--terminate-after` / `--stop-after`: they were never enforced, and runpodctl
  v2.12.0 removed them.

## Scaling up (what changes — and what doesn't)
**Changes:** `BASE` (model id), the `--gpu-id` to a bigger-VRAM tier, and the
dataset/steps. Add `HF_TOKEN` for gated models; use **QLoRA** (axolotl
`load_in_4bit: true`) when the base won't fit for full LoRA.
**Doesn't change:** the shape — one volume, pod trains and writes the adapter to
`/workspace/outputs`, then `pod remove` frees the GPU. To *serve* the result, hand
off to [08](08-finetune-to-serverless.md) (same volume, read at `/runpod-volume`).

## Cost & cleanup
```bash
runpodctl pod remove <pod-id>                 # already done above — frees the GPU
runpodctl network-volume delete <vol-id>      # deletes the adapter + model cache
runpodctl pod list && runpodctl network-volume list   # confirm clean
```
Pod cost guard: `runpodctl pod remove <pod-id>` when done (`--terminate-after` never worked). Keep the
volume only while you still need the adapter (e.g. until 08 has served it); it bills
for stored GB.

## Skill gaps folded back
Nothing new surfaced beyond what golden paths 07 and 08 already folded back — this
path is the training subset of 08, so the relevant facts are already captured in
the skills:
- `on-pod-setup.md` — PEP 668 `--break-system-packages` into the template torch.
- `storage.md` — `/workspace` (pod) mount; container disk is ephemeral, volume
  persists past the pod.
- `gpu-selection.md` — VRAM sizing for training vs. inference.
- The **batch-job vs. server** distinction (tail-the-log, not poll-a-URL; detach
  with `setsid`) is reinforced here and cross-referenced from 08's training step.
