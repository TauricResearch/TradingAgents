#!/usr/bin/env python3
import os
import argparse
from typing import Optional, Dict, Any, List, Tuple

import torch
from datasets import load_dataset, Dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)
from peft import PeftModel


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
    # Decoder-only models should use left padding for generation
    try:
        tokenizer.padding_side = "left"
    except Exception:
        pass
    return tokenizer


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


def load_raw_dataset(path: str) -> Dataset:
    return load_dataset("json", data_files={"train": path})["train"]


def split_train_val_test(ds_all: Dataset, seed: int = 42) -> DatasetDict:
    # 60/20/20 split matching finetune_dapt.py
    first_split = ds_all.train_test_split(test_size=0.4, seed=seed)
    train_ds = first_split["train"]  # 60%
    remaining = first_split["test"]  # 40%
    second_split = remaining.train_test_split(test_size=0.5, seed=seed)
    val_ds = second_split["train"]   # 20%
    test_ds = second_split["test"]   # 20%
    return DatasetDict(train=train_ds, validation=val_ds, test=test_ds)


def detect_text_key(ds: Dataset) -> str:
    preferred = ["text", "content", "body", "cleaned_text", "instruction", "prompt"]
    for k in preferred:
        if k in ds.column_names:
            return k
    return ds.column_names[0]


def map_label_val_to_text(val: Any) -> str:
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


def build_eval_prompts(ds: Dataset, text_key: Optional[str] = None) -> Tuple[List[str], Optional[List[int]]]:
    """
    Build prompts WITHOUT labels. Returns:
      - prompts: list of prompt strings
      - y_true: optional list of integer labels mapped as {-1,0,1}
    """
    if text_key is None:
        text_key = detect_text_key(ds)

    label_to_id = {"Negative": -1, "Neutral": 0, "Positive": 1}

    prompts: List[str] = []
    y_true: Optional[List[int]] = None

    has_label = "label" in ds.column_names
    if has_label:
        y_true = []

    instr_prefix = "### Instruction:\nClassify the sentiment of the following financial text.\n\n"
    for e in ds:
        text_val = str(e.get(text_key) or "")
        prompt = (
            f"{instr_prefix}"
            f"### Text:\n{text_val}\n\n"
            f"### Response:\n"
        )
        prompts.append(prompt)
        if has_label:
            label_text = map_label_val_to_text(e.get("label", 0))
            y_true.append(label_to_id[label_text])

    return prompts, y_true


def tokenize_prompts(prompts: List[str], tokenizer: AutoTokenizer, max_length: int) -> Dataset:
    ds = Dataset.from_dict({"prompt": prompts})

    def tok_fn(batch: Dict[str, List[str]]):
        enc = tokenizer(
            batch["prompt"],
            truncation=True,
            max_length=max_length,
            padding=False,
        )
        return enc

    cols = list(ds.column_names)
    tokenized = ds.map(tok_fn, batched=True, remove_columns=cols)
    return tokenized


def build_model_with_lora_for_eval(base_model_id: str, adapters_path: str, hf_token: Optional[str]):
    # Choose dtype
    torch_dtype = (
        torch.bfloat16
        if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        else (torch.float16 if torch.cuda.is_available() else torch.float32)
    )
    quant_config = get_bnb_config()
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        device_map="auto" if torch.cuda.is_available() else None,
        quantization_config=quant_config,
        low_cpu_mem_usage=True,
        token=hf_token,
        dtype=torch_dtype if "dtype" in AutoModelForCausalLM.from_pretrained.__code__.co_varnames else None,
        torch_dtype=None if "dtype" in AutoModelForCausalLM.from_pretrained.__code__.co_varnames else torch_dtype,
    )
    try:
        base_model.config.use_cache = True
    except Exception:
        pass
    model = PeftModel.from_pretrained(base_model, adapters_path)
    return model


def extract_prediction_label(text: str) -> Optional[int]:
    label_to_id = {"Negative": -1, "Neutral": 0, "Positive": 1}
    low = text.lower()
    if "positive" in low:
        return label_to_id["Positive"]
    if "neutral" in low:
        return label_to_id["Neutral"]
    if "negative" in low:
        return label_to_id["Negative"]
    return None


def evaluate_generation(model, tokenizer, tokenized_ds: Dataset, y_true_eval: Optional[List[int]], batch_size: int, max_new_tokens: int):
    from torch.utils.data import DataLoader

    def collate_fn(features: List[Dict[str, Any]]):
        # Use tokenizer.pad to handle left padding and attention masks correctly
        batch = tokenizer.pad(features, padding=True, return_tensors="pt")
        # Ensure pad_token_id is set on generation config
        if getattr(model, "generation_config", None) is not None and getattr(model.generation_config, "pad_token_id", None) is None:
            model.generation_config.pad_token_id = tokenizer.pad_token_id
        return batch

    if y_true_eval is None:
        print("No labels available for evaluation; skipping accuracy/F1.")
        return

    dl = DataLoader(tokenized_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)
    model.eval()
    preds_all: List[int] = []
    with torch.no_grad():
        for batch in dl:
            # When using device_map='auto', move inputs to the embedding device
            try:
                embed_device = model.base_model.get_input_embeddings().weight.device  # PEFT wraps base model
            except Exception:
                try:
                    embed_device = model.get_input_embeddings().weight.device
                except Exception:
                    embed_device = next(model.parameters()).device
            input_ids = batch["input_ids"].to(embed_device)
            attention_mask = batch["attention_mask"].to(embed_device)
            prompt_lengths = attention_mask.sum(dim=1)
            gen = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
            # Slice off the prompt per-sample using its true length
            for i in range(gen.size(0)):
                start = int(prompt_lengths[i].item())
                gen_only = gen[i, start:]
                txt = tokenizer.decode(gen_only, skip_special_tokens=True)
                pred = extract_prediction_label(txt)
                preds_all.append(pred if pred is not None else 0)  # default Neutral

    # Align lengths
    n = min(len(preds_all), len(y_true_eval))
    y_pred = preds_all[:n]
    y_true = y_true_eval[:n]

    correct = sum(int(p == t) for p, t in zip(y_pred, y_true))
    acc = correct / max(1, len(y_pred))

    class_ids = [-1, 0, 1]
    f1s: List[float] = []
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


def main():
    parser = argparse.ArgumentParser(description="Evaluate SFT LoRA adapters via generation without label leakage")
    parser.add_argument("--model-id", default="meta-llama/Llama-3.1-8B", help="Base model ID")
    parser.add_argument("--adapters-path", required=True, help="Path to LoRA adapters (output dir from finetune)")
    parser.add_argument("--data", required=True, help="Path to JSON dataset used for training")
    parser.add_argument("--max-length", type=int, default=1024, help="Max input sequence length")
    parser.add_argument("--batch-size", type=int, default=2, help="Eval batch size")
    parser.add_argument("--max-new-tokens", type=int, default=8, help="Max new tokens to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed used for split")
    args = parser.parse_args()

    device = detect_device()
    hf_token = (
        os.getenv("HUGGING_FACE_HUB_TOKEN")
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    )

    tokenizer = build_tokenizer(args.model_id, hf_token)

    # Load and split to ensure the same test set as training (seed-matched)
    ds_all = load_raw_dataset(args.data)
    dsd = split_train_val_test(ds_all, seed=args.seed)
    test_raw = dsd["test"]

    # Build prompts without labels and ground truth
    prompts, y_true = build_eval_prompts(test_raw)
    tokenized = tokenize_prompts(prompts, tokenizer, max_length=args.max_length)

    # Load model with LoRA adapters
    model = build_model_with_lora_for_eval(args.model_id, args.adapters_path, hf_token)
    model = model.to(device)

    evaluate_generation(
        model=model,
        tokenizer=tokenizer,
        tokenized_ds=tokenized,
        y_true_eval=y_true,
        batch_size=max(1, args.batch_size),
        max_new_tokens=args.max_new_tokens,
    )


if __name__ == "__main__":
    main()


