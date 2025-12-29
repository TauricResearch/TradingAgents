"""
DAPT (Domain-Adaptive Pretraining) for Llama 3.1 on Earnings Call Transcripts

This script mirrors the notebook logic from `DAPT_Llama31_Transcripts.ipynb`.
It performs continued pretraining (causal LM objective) of Llama 3.1 using a
local Parquet file containing earnings call transcripts.

What you'll get:
- Environment-adaptive setup (CUDA, MPS, CPU) with automatic LoRA/QLoRA selection
- Robust dataset loading from Parquet and text-column auto-detection
- Efficient token packing into fixed-length sequences
- PEFT LoRA (and QLoRA on CUDA) training pipeline with Transformers Trainer
- Save adapters and quick inference sanity check

Notes:
- Accept the Llama 3.1 license on Hugging Face and authenticate before training.
- On macOS (MPS), QLoRA is disabled (no bitsandbytes). We use standard LoRA with float16/float32.
- For best performance, use a CUDA GPU and enable QLoRA.
"""

# Install required libraries (run manually if needed):
#   pip install -U transformers datasets accelerate peft sentencepiece protobuf
# For CUDA QLoRA only (Linux/NVIDIA):
#   pip install bitsandbytes

# Minimize on-disk writes (avoid "No space left on device")
import os
import tempfile
import datasets
import transformers

# Use a small temp dir for caches or disable dataset cache writes
TMP_DIR = tempfile.mkdtemp(prefix="hf_tmp_")
os.environ["HF_HOME"] = TMP_DIR
os.environ["HF_DATASETS_CACHE"] = os.path.join(TMP_DIR, "datasets_cache")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

os.environ["HF_TOKEN"] = "hf_token"
os.environ["HUGGINGFACE_HUB_TOKEN"] = os.environ["HF_TOKEN"]

# Keep map results in memory to avoid materializing to disk
datasets.disable_caching()
print({
    "HF_HOME": os.environ.get("HF_HOME"),
    "HF_DATASETS_CACHE": os.environ.get("HF_DATASETS_CACHE"),
    "caching_disabled": True,
})

# If needed, install dependencies (do manually if missing):
#   pip install -U transformers datasets accelerate peft
# For CUDA QLoRA only (Linux/NVIDIA):
#   pip install bitsandbytes

import platform
import torch

# Detect environment
USE_CUDA = torch.cuda.is_available()
USE_MPS = (not USE_CUDA) and torch.backends.mps.is_available()
BF16_OK = USE_CUDA and torch.cuda.is_bf16_supported()
USE_QLORA = USE_CUDA  # QLoRA requires CUDA + bitsandbytes; set False on macOS/CPU
# Disable QLoRA automatically if bitsandbytes is not installed
try:
    import importlib.metadata as _ilmd
    _ = _ilmd.version("bitsandbytes")
except Exception:
    if USE_QLORA:
        print("bitsandbytes not found; disabling QLoRA (falling back to standard LoRA)")
    USE_QLORA = False

DEVICE = (
    torch.device("cuda") if USE_CUDA else (torch.device("mps") if USE_MPS else torch.device("cpu"))
)

print({
    "cuda": USE_CUDA,
    "mps": USE_MPS,
    "bf16_ok": BF16_OK,
    "use_qlora": USE_QLORA,
    "device": str(DEVICE),
    "python": platform.python_version(),
})

from datasets import load_datasets
from typing import Optional
import pandas as pds

# Paths and config
# Update this to the actual Parquet path on your system
PARQUET_PATH = "stock_earning_call_transcripts.parquet"
TEXT_COLUMN: Optional[str] = None  # override to force a column, else auto

raw_ds = load_dataset("parquet", data_files={"train": PARQUET_PATH})["train"]
print("Columns:", raw_ds.column_names)
print(raw_ds[0])

# If schema has nested `transcripts` (array of structs with speaker/content),
# flatten into a single text field for DAPT.
if "transcripts" in raw_ds.column_names:
    def flatten_segments(example):
        segments = example.get("transcripts") or []
        lines = []
        for seg in segments:
            if not seg:
                continue
            
            speaker = seg.get("speaker")
            content = seg.get("content")
            if content is None:
                continue
            if speaker and len(str(speaker)) > 0:
                lines.append(f"{speaker}: {content}")
            else:
                lines.append(str(content))
        example["__flattened_text"] = "\n".join(lines)
        return example

    raw_ds = raw_ds.map(flatten_segments)
    # Prefer flattened text unless user overrides
    if TEXT_COLUMN is None:
        TEXT_COLUMN = "__flattened_text"

# Auto-detect a reasonable text column if still unknown
if TEXT_COLUMN is None:
    preferred = [
        "__flattened_text",
        "text",
        "transcript",
        "content",
        "body",
        "cleaned_text",
        "utterance",
        "raw_text",
    ]
    for p in preferred:
        exact = [c for c in raw_ds.column_names if c.lower() == p]
        if len(exact) > 0:
            TEXT_COLUMN = exact[0]
            break

if TEXT_COLUMN is None:
    # fallback to first string-like column
    for name, feature in raw_ds.features.items():
        if getattr(feature, "dtype", "") in ("string", "large_string"):
            TEXT_COLUMN = name
            break

if TEXT_COLUMN is None:
    TEXT_COLUMN = raw_ds.column_names[0]

print("Using text column:", TEXT_COLUMN)

# Filter empty
ds = raw_ds.filter(lambda x: x.get(TEXT_COLUMN) is not None and len(str(x[TEXT_COLUMN])) > 0)
print(ds)
print("Example text:", str(ds[0][TEXT_COLUMN])[:400])

from transformers import AutoTokenizer

MODEL_ID = "meta-llama/Llama-3.1-8B"
BLOCK_SIZE = 1024  # use 512–1024 for QLoRA on 10–12 GB GPUs

# Load tokenizer
print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
# Avoid long-sequence warnings during tokenization; packing enforces BLOCK_SIZE later
try:
    tokenizer.model_max_length = 1_000_000_000
except Exception:
    pass

def tokenize_examples(batch):
    return tokenizer(batch[TEXT_COLUMN], add_special_tokens=False, truncation=False)

print("Tokenizing dataset (this may take a while)...")
tok_ds = ds.map(
    tokenize_examples,
    batched=True,
    remove_columns=[c for c in ds.column_names if c != TEXT_COLUMN],
)

# Pack tokens into fixed blocks
def group_texts(examples):
    concatenated = []
    for ids in examples["input_ids"]:
        concatenated.extend(ids + [tokenizer.eos_token_id])
    total_length = (len(concatenated) // BLOCK_SIZE) * BLOCK_SIZE
    if total_length == 0:
        return {"input_ids": [], "labels": []}
    input_ids = [
        concatenated[i : i + BLOCK_SIZE] for i in range(0, total_length, BLOCK_SIZE)
    ]
    return {"input_ids": input_ids, "labels": [x.copy() for x in input_ids]}

lm_ds = tok_ds.map(group_texts, batched=True, remove_columns=tok_ds.column_names)
print(lm_ds)

from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

OUTPUT_DIR = "llama31_dapt_transcripts_lora"
LEARNING_RATE = 2e-4
EPOCHS = 1
PER_DEVICE_BATCH = 1
GRAD_ACCUM = 32

bnb_config = None
if USE_QLORA:
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if BF16_OK else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

print("Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    torch_dtype=torch.bfloat16
    if BF16_OK
    else (torch.float16 if USE_CUDA else torch.float32),
    quantization_config=bnb_config if USE_QLORA else None,
)

if USE_QLORA:
    model = prepare_model_for_kbit_training(model)

lora_cfg = LoraConfig(
    task_type="CAUSAL_LM",
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
)
model = get_peft_model(model, lora_cfg)

print(model)

from transformers import Trainer, TrainingArguments, DataCollatorForLanguageModeling

collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=PER_DEVICE_BATCH,
    gradient_accumulation_steps=GRAD_ACCUM,
    learning_rate=LEARNING_RATE,
    logging_steps=10,
    save_steps=200,
    save_total_limit=2,
    save_strategy="steps",
    bf16=BF16_OK,
    fp16=(USE_CUDA and not BF16_OK),
    optim="paged_adamw_8bit" if USE_QLORA else "adamw_torch",
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.0,
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=lm_ds,
    data_collator=collator,
)

trainer.train(resume_from_checkpoint=True)

# Save adapter + tokenizer, and run a tiny inference sanity check
from peft import PeftModel

# Save
trainer.model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Saved PEFT adapter and tokenizer to {OUTPUT_DIR}")

# Hosted inference via Hugging Face Inference API
print("Running inference via Hugging Face Inference API...")
from huggingface_hub import InferenceClient

hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
client = InferenceClient("meta-llama/Llama-3.1-8B-Instruct", token=hf_token)

resp = client.text_generation(
    "Write a haiku about GPUs",
    max_new_tokens=128,
    temperature=0.7,
)
print(resp)


