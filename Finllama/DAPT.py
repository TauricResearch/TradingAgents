

# %%
from huggingface_hub import InferenceClient

client = InferenceClient("meta-llama/Llama-3.1-8B", token="hf_xxx")  # replace with your HF token
resp = client.text_generation(
    "Write a haiku about GPUs",
    max_new_tokens=128,
    temperature=0.7,
)
print(resp)

# %%
# Minimize on-disk writes (avoid "No space left on device")
import os, tempfile, datasets, transformers

# Use a small temp dir for caches or disable dataset cache writes
TMP_DIR = tempfile.mkdtemp(prefix="hf_tmp_")
os.environ["HF_HOME"] = TMP_DIR
os.environ["HF_DATASETS_CACHE"] = os.path.join(TMP_DIR, "datasets_cache")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

os.environ["HF_TOKEN"] = "hf_xxx"  # replace with your HF token
os.environ["HUGGINGFACE_HUB_TOKEN"] = os.environ["HF_TOKEN"]
# Keep map results in memory to avoid materializing to disk
datasets.disable_caching()
print({
    "HF_HOME": os.environ.get("HF_HOME"),
    "HF_DATASETS_CACHE": os.environ.get("HF_DATASETS_CACHE"),
    "caching_disabled": True,
    "PYTORCH_CUDA_ALLOC_CONF": os.environ.get("PYTORCH_CUDA_ALLOC_CONF"),
})

# %%
# If needed, install dependencies. Uncomment the next cell to run once.
# %pip -q install -U transformers datasets accelerate peft
# For CUDA QLoRA only (Linux/NVIDIA):
# %pip -q install bitsandbytes

import os
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

# %%
from datasets import load_dataset
from typing import Optional
import getpass

# Paths and config
# Get current username dynamically
current_user = getpass.getuser()
PARQUET_PATH = f"/u/v/d/{current_user}/defeatbeta-api-main/stock_earning_call_transcripts.parquet"
TEXT_COLUMN: Optional[str] = None  # override to force a column, else auto

raw_ds = load_dataset("parquet", data_files={"train": PARQUET_PATH})["train"]
SAMPLE_FRACTION = 0.2  # use 20% random subset for faster DAPT
SAMPLE_SEED = int(os.environ.get("SAMPLE_SEED", "42"))
if SAMPLE_FRACTION < 1.0:
    split = raw_ds.train_test_split(test_size=1.0 - SAMPLE_FRACTION, seed=SAMPLE_SEED, shuffle=True)
    raw_ds = split["train"]
    try:
        print(f"Randomly sampled {int(SAMPLE_FRACTION*100)}% subset; size: {len(raw_ds)}")
    except Exception:
        pass
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
    preferred = ["__flattened_text","text","transcript","content","body","cleaned_text","utterance","raw_text"]
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

# %%
from transformers import AutoTokenizer

MODEL_ID = "meta-llama/Llama-3.1-8B"
BLOCK_SIZE = 512  # lowered to reduce activation memory on 10–12 GB GPUs

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
tok_ds = ds.map(tokenize_examples, batched=True, remove_columns=[c for c in ds.column_names if c != TEXT_COLUMN])

# Pack tokens into fixed blocks
def group_texts(examples):
    concatenated = []
    for ids in examples["input_ids"]:
        concatenated.extend(ids + [tokenizer.eos_token_id])
    total_length = (len(concatenated) // BLOCK_SIZE) * BLOCK_SIZE
    if total_length == 0:
        return {"input_ids": [], "labels": []}
    input_ids = [concatenated[i:i+BLOCK_SIZE] for i in range(0, total_length, BLOCK_SIZE)]
    return {"input_ids": input_ids, "labels": [x.copy() for x in input_ids]}

lm_ds = tok_ds.map(group_texts, batched=True, remove_columns=tok_ds.column_names)
print(lm_ds)

# %%
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# Use the current username (already defined above)
OUTPUT_DIR = f"/u/v/d/{current_user}/llama3_8b_dapt_transcripts_lora"
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

# Prefer FlashAttention-2 on CUDA if available; else fall back to SDPA
attn_impl = "sdpa"
if USE_CUDA:
    try:
        import flash_attn  # noqa: F401
        attn_impl = "flash_attention_2"
    except Exception:
        pass

# Constrain loading to GPU memory to avoid CPU/disk offload with 4-bit
load_kwargs = {}
if USE_CUDA:
    try:
        total_bytes = torch.cuda.get_device_properties(0).total_memory
        total_gib = max(1, int(total_bytes / (1024 ** 3)))
        reserve_gib = 1
        max_gib = max(1, total_gib - reserve_gib)
        load_kwargs["device_map"] = "auto"
        load_kwargs["max_memory"] = {0: f"{max_gib}GiB"}
    except Exception:
        load_kwargs["device_map"] = "auto"

print("Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=torch.bfloat16 if BF16_OK else (torch.float16 if USE_CUDA else torch.float32),
    quantization_config=bnb_config if USE_QLORA else None,
    attn_implementation=attn_impl,
    low_cpu_mem_usage=True,
    **load_kwargs,
)

if USE_QLORA:
    model = prepare_model_for_kbit_training(model)

lora_cfg = LoraConfig(
    task_type="CAUSAL_LM",
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
)
model = get_peft_model(model, lora_cfg)

# Reduce training memory footprint
model.config.use_cache = False
try:
    model.enable_input_require_grads()
except Exception:
    pass
try:
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
except Exception:
    model.gradient_checkpointing_enable()

print(model)
try:
    print("Device map:", getattr(model, "hf_device_map", None))
except Exception:
    pass

# %%
from transformers import Trainer, TrainingArguments, DataCollatorForLanguageModeling

collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False, pad_to_multiple_of=8)

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
    tf32=True,
    gradient_checkpointing=True,
    remove_unused_columns=False,
    dataloader_num_workers=2,
    optim="paged_adamw_8bit" if USE_QLORA else "adamw_torch",
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.0,
    save_safetensors=True,
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=lm_ds,
    data_collator=collator,
)

# Free any stale allocations before training
import gc, torch; gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()

from pathlib import Path

def _latest_checkpoint_dir(base_dir: str):
    try:
        dirs = [p for p in Path(base_dir).glob("checkpoint-*") if p.is_dir()]
        if not dirs:
            return None
        def step_num(p: Path):
            try:
                return int(p.name.split("-")[-1])
            except Exception:
                return -1
        latest = max(dirs, key=step_num)
        return str(latest)
    except Exception:
        return None

latest_ckpt = _latest_checkpoint_dir(OUTPUT_DIR)
print("Resume checkpoint:", latest_ckpt or "<none; starting fresh>")
trainer.train(resume_from_checkpoint=latest_ckpt if latest_ckpt else None)

# %%
# Save adapter + tokenizer, then run a quick inference via HF Inference API
from peft import PeftModel

# Save
trainer.model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Saved PEFT adapter and tokenizer to {OUTPUT_DIR}")

# Hosted inference via Hugging Face Inference API (no GPU weights needed here)
print("Running inference via Hugging Face Inference API...")
from huggingface_hub import InferenceClient

hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
client = InferenceClient("meta-llama/Llama-3.1-8B", token=hf_token)

resp = client.text_generation(
    "Write a haiku about GPUs",
    max_new_tokens=128,
    temperature=0.7,
)
print(resp)


