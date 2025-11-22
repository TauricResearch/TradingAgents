#!/usr/bin/env python3
import os
import argparse
from typing import Optional, Dict, Any

import torch
import inspect
from datasets import load_dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
)
from peft import PeftModel, prepare_model_for_kbit_training


def detect_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def build_tokenizer(model_id: str, hf_token: Optional[str]) -> AutoTokenizer:
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        use_fast=True,
        token=hf_token,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def load_text_dataset(path: str, text_key: Optional[str] = None, sample_pct: Optional[float] = None):
    """
    Loads a JSON dataset and returns a DatasetDict with train/validation.
    If 'label' and 'text' columns are present, formats samples into instruction-style SFT examples.
    Otherwise, falls back to plain text selection.
    """
    ds_all = load_dataset("json", data_files={"train": path})["train"]

    if "label" in ds_all.column_names and ("text" in ds_all.column_names or text_key is not None):
        # Use provided or default text key
        if text_key is None:
            text_key = "text"

        def format_example(e):
            # Map labels to Positive/Neutral/Negative as per instruction template
            label_val = e.get("label", 0)
            try:
                label_val = int(label_val)
            except Exception:
                label_val = 0
            if label_val == 1:
               label_text = "Positive"
            elif label_val == -1:
               label_text = "Negative"
            else:
               label_text = "Neutral"

            instruction = (
                "### Instruction:\n"
                "Classify the sentiment of the following financial text.\n\n"
                f"### Text:\n{str(e.get(text_key) or '')}\n\n"
                "### Response:\n"
                f"{label_text}"
            )
            e["_text"] = instruction
            return e

        ds_all = ds_all.map(format_example)
        # keep columns; tokenizer will remove unused ones
    else:
        # Auto-detect text column if not provided
        if text_key is None:
            preferred = ["text", "content", "body", "cleaned_text", "instruction", "prompt"]
            for k in preferred:
                if k in ds_all.column_names:
                    text_key = k
                    break
            # fallback to first column
            if text_key is None:
                text_key = ds_all.column_names[0]

        # If pairs like ("instruction","output") exist, join them; else just use text_key
        join_output = None
        for cand in ["output", "completion", "response"]:
            if cand in ds_all.column_names:
                join_output = cand
                break

        def to_text(example):
            if join_output is not None and text_key in example and example.get(join_output) is not None:
                inp = str(example.get(text_key) or "")
                out = str(example.get(join_output) or "")
                example["_text"] = f"{inp}\n\n{out}".strip()
            else:
                example["_text"] = str(example.get(text_key) or "")
            return example

        ds_all = ds_all.map(to_text, remove_columns=[c for c in ds_all.column_names if c != "_text"])

    # Optionally subsample
    if sample_pct is not None and 0 < sample_pct < 1:
        n = len(ds_all)
        keep = max(1, int(n * sample_pct))
        ds_all = ds_all.select(range(keep))

    # 60/20/20 train/validation/test split
    first_split = ds_all.train_test_split(test_size=0.4, seed=42)
    train_ds = first_split["train"]  # 60%
    remaining = first_split["test"]  # 40%
    second_split = remaining.train_test_split(test_size=0.5, seed=42)
    val_ds = second_split["train"]   # 20%
    test_ds = second_split["test"]   # 20%
    return DatasetDict(train=train_ds, validation=val_ds, test=test_ds)


def tokenize_dataset(dataset, tokenizer: AutoTokenizer, max_length: int):
    def tok_fn(examples: Dict[str, Any]):
        enc = tokenizer(
            examples["_text"],
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        return enc

    cols = list(dataset["train"].column_names)
    tokenized = {}
    for split in dataset.keys():
        tokenized[split] = dataset[split].map(tok_fn, batched=True, remove_columns=cols)
    return tokenized


def get_bnb_config():
    if not torch.cuda.is_available():
        return None
    try:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        return bnb_config
    except Exception:
        return None


def build_model_with_lora(base_model_id: str, dapt_path: str, device: torch.device, hf_token: Optional[str]):
    # Choose dtype
    torch_dtype = (
        torch.bfloat16
        if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        else (torch.float16 if torch.cuda.is_available() else torch.float32)
    )

    # 4-bit quantization (QLoRA) if available
    quant_config = get_bnb_config()

    # Transformers >=5.0.0 deprecates 'torch_dtype' in favor of 'dtype'
    base_from_pretrained_sig = inspect.signature(AutoModelForCausalLM.from_pretrained)
    dtype_kw = {"dtype": torch_dtype} if "dtype" in base_from_pretrained_sig.parameters else {"torch_dtype": torch_dtype}
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        device_map="auto" if torch.cuda.is_available() else None,
        quantization_config=quant_config,
        low_cpu_mem_usage=True,
        token=hf_token,
        **dtype_kw,
    )
    base_model.config.use_cache = False  # needed for gradient checkpointing

    if quant_config is not None:
        base_model = prepare_model_for_kbit_training(base_model)

    # Load existing DAPT LoRA adapters on top of the base model (continue training this adapter)
    # Newer PEFT supports is_trainable=True to mark LoRA params trainable on load
    peft_from_pretrained_sig = inspect.signature(PeftModel.from_pretrained)
    peft_kwargs = {"is_trainable": True} if "is_trainable" in peft_from_pretrained_sig.parameters else {}
    model = PeftModel.from_pretrained(base_model, dapt_path, **peft_kwargs)

    # Ensure only LoRA parameters are set as trainable (fallback for older PEFT versions)
    try:
        from peft.tuners.lora import mark_only_lora_as_trainable  # type: ignore
        mark_only_lora_as_trainable(model)
    except Exception:
        for name, param in model.named_parameters():
            if "lora_" in name:
                param.requires_grad = True

    model.print_trainable_parameters()
    return model


def main():
    parser = argparse.ArgumentParser(description="SFT fine-tune existing DAPT LoRA using QLoRA")
    parser.add_argument("--model-id", default="meta-llama/Llama-3.1-8B", help="Base model ID")
    parser.add_argument(
        "--dapt-path",
        default="/u/v/d/vdhanuka/llama3_8b_dapt_transcripts_lora",
        help="Path to existing DAPT LoRA adapters",
    )
    parser.add_argument(
        "--data",
        default="/u/v/d/vdhanuka/defeatbeta-api-main/combined_training_data.json",
        help="Path to JSON training data",
    )
    parser.add_argument("--output-dir", default="./dapt_sft_adapters_2", help="Where to save new adapters")
    parser.add_argument("--max-length", type=int, default=1024, help="Max sequence length")
    parser.add_argument("--epochs", type=int, default=4, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=1, help="Per-device train batch size")
    parser.add_argument("--grad-accum", type=int, default=16, help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps")
    parser.add_argument("--weight-decay", type=float, default=0.0, help="Weight decay")
    parser.add_argument("--sample-pct", type=float, default=None, help="Optional fraction of data to use (0-1)")
    parser.add_argument("--save-steps", type=int, default=1000, help="Save checkpoint every N steps")
    parser.add_argument("--logging-steps", type=int, default=20, help="Log every N steps")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    device = detect_device()
    hf_token = (
        os.getenv("HUGGING_FACE_HUB_TOKEN")
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    )

    tokenizer = build_tokenizer(args.model_id, hf_token)

    # Dataset
    raw = load_text_dataset(args.data, text_key=None, sample_pct=args.sample_pct)
    tokenized = tokenize_dataset(raw, tokenizer, max_length=args.max_length)

    # Build ground-truth labels for evaluation (order aligned with tokenized["test"])
    # Map label text to your dataset's numeric scheme: -1 (Negative), 0 (Neutral), 1 (Positive)
    label_to_id = {"Negative": -1, "Neutral": 0, "Positive": 1}
    def map_label_val(val: int) -> str:
        try:
            v = int(val)
        except Exception:
            v = 0
        if v == 1:
            return "Positive"
        elif v == 0:
            return "Neutral"
        else:
            return "Negative"
    if "label" in raw["test"].column_names:
        y_true_eval_text = [map_label_val(v) for v in raw["test"]["label"]]
        y_true_eval = [label_to_id[t] for t in y_true_eval_text]
    else:
        y_true_eval_text = None
        y_true_eval = None

    # Model with existing DAPT LoRA + QLoRA prep for SFT
    model = build_model_with_lora(args.model_id, args.dapt_path, device, hf_token)
    model.gradient_checkpointing_enable()

    # Collator for causal LM (labels = input_ids)
    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    # Generation-based evaluation utilities (run after training to avoid version issues)
    def extract_prediction_label(text: str) -> Optional[int]:
        low = text.lower()
        if "positive" in low:
            return label_to_id["Positive"]
        if "neutral" in low:
            return label_to_id["Neutral"]
        if "negative" in low:
            return label_to_id["Negative"]
        return None

    def evaluate_generation(model, tokenizer, dataset, batch_size: int = 2, max_new_tokens: int = 8):
        if y_true_eval is None:
            print("No labels available for evaluation; skipping accuracy/F1.")
            return
        from torch.utils.data import DataLoader
        dl = DataLoader(dataset, batch_size=batch_size, shuffle=False, collate_fn=collator)
        model.eval()
        preds_all = []
        with torch.no_grad():
            for batch in dl:
                input_ids = batch["input_ids"].to(model.device)
                attention_mask = batch.get("attention_mask", None)
                if attention_mask is not None:
                    attention_mask = attention_mask.to(model.device)
                gen = model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                )
                decoded = tokenizer.batch_decode(gen, skip_special_tokens=True)
                for txt in decoded:
                    pred = extract_prediction_label(txt)
                    preds_all.append(pred if pred is not None else label_to_id["Neutral"])
        # Align to length of eval labels
        n = min(len(preds_all), len(y_true_eval))
        y_pred = preds_all[:n]
        y_true = y_true_eval[:n]
        # Accuracy
        correct = sum(int(p == t) for p, t in zip(y_pred, y_true))
        acc = correct / max(1, len(y_pred))
        # Macro F1 over classes [-1, 0, 1]
        class_ids = [-1, 0, 1]
        f1s = []
        for c in class_ids:
            tp = sum(int((p == c) and (t == c)) for p, t in zip(y_pred, y_true))
            fp = sum(int((p == c) and (t != c)) for p, t in zip(y_pred, y_true))
            fn = sum(int((p != c) and (t == c)) for p, t in zip(y_pred, y_true))
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
            f1s.append(f1)
        macro_f1 = sum(f1s) / len(class_ids)
        print(f"Eval (generation): accuracy={acc:.4f}, macro_f1={macro_f1:.4f}")

    # Training args
    steps_per_epoch = max(1, len(tokenized["train"]) // max(1, args.batch_size))
    save_steps = max(args.save_steps, steps_per_epoch)  # avoid saving too often on tiny sets
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=max(1, args.batch_size),
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        weight_decay=args.weight_decay,
        warmup_steps=args.warmup_steps,
        logging_steps=args.logging_steps,
        save_steps=save_steps,
        save_total_limit=3,
        # Older transformers may not support evaluation_strategy; run eval manually after training
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        gradient_checkpointing=True,
        torch_compile=False,
        report_to=["none"],
        seed=args.seed,
    )

    # Transformers >=5.0.0 deprecates 'tokenizer' in Trainer in favor of 'processing_class'
    trainer_init_sig = inspect.signature(Trainer.__init__)
    trainer_common = dict(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        data_collator=collator,
    )
    if "processing_class" in trainer_init_sig.parameters:
        trainer = Trainer(**trainer_common, processing_class=tokenizer)
    else:
        trainer = Trainer(**trainer_common, tokenizer=tokenizer)

    trainer.train()

    # Save only the updated adapters
    os.makedirs(args.output_dir, exist_ok=True)
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"✅ Saved SFT LoRA adapters to: {args.output_dir}")

    # Manual evaluation via generation (accuracy / macro-F1)
    try:
        evaluate_generation(model, tokenizer, tokenized["test"], batch_size=max(1, args.batch_size))
    except Exception as e:
        print(f"Evaluation (generation) failed: {e}")


if __name__ == "__main__":
    main()


