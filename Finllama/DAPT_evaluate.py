#!/usr/bin/env python3
"""
DAPT Model Evaluation Script

Evaluates a Domain-Adaptive Pretrained (DAPT) Llama 3.1 model against the baseline
Llama 3.1 model on stock earnings call transcripts dataset.

Computes perplexity scores to measure model performance on domain-specific data.
"""

import os
import sys
import time
import argparse
from typing import List, Optional

import numpy as np
import torch
from datasets import load_dataset
from peft import PeftModel
from tqdm import tqdm
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
)


class DAPTEvaluator:
    """Evaluator for DAPT model vs baseline perplexity comparison"""

    def __init__(
        self,
        model_id: str = "meta-llama/Llama-3.1-8B",
        dapt_model_path: str = "/u/v/d/vdhanuka/llama3_8b_dapt_transcripts_lora",
        dataset_path: str = "/u/v/d/vdhanuka/defeatbeta-api-main/stock_earning_call_transcripts.parquet",
        sample_size: Optional[int] = None,
        sample_percentage: Optional[float] = None,
        max_length: int = 1024,
        use_qlora: bool = True,
        device: Optional[str] = None,
    ):
        """
        Initialize the evaluator.

        Args:
            model_id: HuggingFace model ID for base model
            dapt_model_path: Path to trained DAPT LoRA adapters
            dataset_path: Path to evaluation dataset
            sample_size: Number of samples to evaluate (mutually exclusive with sample_percentage)
            sample_percentage: Percentage of dataset to evaluate (0.0-1.0, mutually exclusive with sample_size)
            max_length: Maximum sequence length for evaluation
            use_qlora: Whether to use QLoRA quantization
            device: Device to use (auto-detected if None)
        """
        self.model_id = model_id
        self.dapt_model_path = dapt_model_path
        self.dataset_path = dataset_path
        self.sample_size = sample_size
        self.sample_percentage = sample_percentage
        self.max_length = max_length
        self.use_qlora = use_qlora

        # Auto-detect device
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Hugging Face token from environment
        self.hf_token = (
            os.getenv("HUGGING_FACE_HUB_TOKEN")
            or os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        )

        # Initialize models and tokenizer
        self.tokenizer = None
        self.baseline_model = None
        self.dapt_model = None
        self.eval_texts: Optional[List[str]] = None

        print("🚀 Initializing DAPT Evaluator")
        print(f"   Model: {model_id}")
        print(f"   DAPT Path: {dapt_model_path}")
        print(f"   Dataset: {dataset_path}")
        print(f"   Device: {self.device}")
        if self.hf_token:
            print(f"   HF token: detected in environment")
        else:
            print(f"   HF token: not found (anonymous access)")
        if sample_percentage is not None:
            print(f"   Sample Percentage: {sample_percentage*100:.1f}%")
        else:
            print(f"   Sample Size: {sample_size}")
        print(f"   Use QLoRA: {use_qlora}")

    def setup_tokenizer(self):
        """Load and configure tokenizer"""
        print("\n🔧 Loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            use_fast=True,
            token=self.hf_token,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        print(f"   Vocab size: {self.tokenizer.vocab_size}")
        return self.tokenizer

    def load_dataset(self):
        """Load and preprocess evaluation dataset"""
        print("\n📊 Loading evaluation dataset...")
        try:
            ds = load_dataset("parquet", data_files={"eval": self.dataset_path})["eval"]
            print(f"   Dataset loaded: {len(ds)} examples")
            print(f"   Columns: {ds.column_names}")

            # Flatten transcripts if needed (same logic as training)
            if "transcripts" in ds.column_names:
                print("   Flattening transcript data...")

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
                    example["text"] = "\n".join(lines)
                    return example

                ds = ds.map(flatten_segments, desc="Flattening transcripts")
                text_column = "text"
            else:
                # Auto-detect text column
                preferred = ["text", "transcript", "content", "body", "cleaned_text"]
                text_column = None
                for p in preferred:
                    if p in ds.column_names:
                        text_column = p
                        break
                if text_column is None:
                    text_column = ds.column_names[0]

            print(f"   Using text column: {text_column}")

            # Determine sample size
            total_samples = len(ds)
            if self.sample_percentage is not None:
                # Use percentage of dataset
                sample_size = int(total_samples * self.sample_percentage)
                sample_size = max(1, sample_size)
                print(f"   Using {self.sample_percentage*100:.1f}% of dataset = {sample_size} samples")
            else:
                # Use fixed sample size
                sample_size = min(self.sample_size, total_samples)
                if sample_size is None:
                    sample_size = min(1000, total_samples)
            if sample_size < 1:
                sample_size = 1

            # Get random sample for more representative evaluation
            indices = np.random.choice(total_samples, sample_size, replace=False)
            sample_ds = ds.select(indices)

            # Filter out empty or very short texts
            def is_valid_text(example):
                text = example.get(text_column, "")
                return text is not None and len(str(text).strip()) > 50

            sample_ds = sample_ds.filter(is_valid_text)
            self.eval_texts = [ex[text_column] for ex in sample_ds]

            print(f"   Sampled {len(self.eval_texts)} valid texts for evaluation")
            avg_chars = float(np.mean([len(t) for t in self.eval_texts])) if len(self.eval_texts) > 0 else 0.0
            print(f"   Average text length: {avg_chars:.0f} characters")

            return self.eval_texts

        except Exception as e:
            print(f"❌ Error loading dataset: {e}")
            raise

    def setup_quantization(self):
        """Setup quantization configuration"""
        if not self.use_qlora or not torch.cuda.is_available():
            return None

        try:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            print("   Using 4-bit quantization (QLoRA)")
            return bnb_config
        except Exception:
            print("   BitsAndBytes not available, using standard precision")
            return None

    def load_baseline_model(self):
        """Load the baseline Llama 3.1 model"""
        print("\n🏗️ Loading baseline model...")
        bnb_config = self.setup_quantization()

        torch_dtype = (
            torch.bfloat16
            if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
            else torch.float16 if torch.cuda.is_available() else torch.float32
        )

        self.baseline_model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            device_map="auto" if torch.cuda.is_available() else None,
            torch_dtype=torch_dtype,
            quantization_config=bnb_config,
            low_cpu_mem_usage=True,
            token=self.hf_token,
        )
        self.baseline_model.eval()
        print("   Baseline model loaded successfully")
        return self.baseline_model

    def load_dapt_model(self):
        """Load the DAPT model with LoRA adapters"""
        print("\n🎯 Loading DAPT model...")
        if not os.path.exists(self.dapt_model_path):
            print(f"❌ DAPT model path not found: {self.dapt_model_path}")
            return None

        try:
            bnb_config = self.setup_quantization()
            torch_dtype = (
                torch.bfloat16
                if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
                else torch.float16 if torch.cuda.is_available() else torch.float32
            )

            # Load base model
            dapt_base_model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                device_map="auto" if torch.cuda.is_available() else None,
                torch_dtype=torch_dtype,
                quantization_config=bnb_config,
                low_cpu_mem_usage=True,
                token=self.hf_token,
            )

            # Load LoRA adapters
            self.dapt_model = PeftModel.from_pretrained(dapt_base_model, self.dapt_model_path)
            self.dapt_model.eval()
            print("   DAPT model loaded successfully")
            return self.dapt_model

        except Exception as e:
            print(f"❌ Error loading DAPT model: {e}")
            return None

    def compute_perplexity(self, model, texts: List[str]) -> float:
        """
        Compute perplexity for a model on given texts.

        Args:
            model: The language model to evaluate
            texts: List of text strings

        Returns:
            Perplexity score
        """
        model.eval()
        total_loss = 0.0
        total_tokens = 0

        with torch.no_grad():
            for text in tqdm(texts, desc="Computing perplexity", unit="text"):
                # Tokenize
                encodings = self.tokenizer(
                    text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=self.max_length,
                    padding=False,
                )

                input_ids = encodings.input_ids.to(self.device)

                if len(input_ids[0]) <= 1:
                    continue

                # Create labels (same as input_ids for causal LM)
                labels = input_ids.clone()

                # Forward pass
                outputs = model(input_ids=input_ids, labels=labels)
                loss = outputs.loss

                # Accumulate loss weighted by sequence length
                seq_len = len(input_ids[0])
                total_loss += loss.item() * seq_len
                total_tokens += seq_len

        if total_tokens == 0:
            return float("inf")

        # Compute average loss and perplexity
        avg_loss = total_loss / total_tokens
        perplexity = float(np.exp(avg_loss))

        return perplexity

    def evaluate_models(self):
        """Evaluate both baseline and DAPT models"""
        if self.eval_texts is None:
            raise ValueError("Evaluation texts not loaded. Call load_dataset() first.")

        results = {}

        # Evaluate baseline model
        if self.baseline_model is None:
            self.load_baseline_model()

        print("\n📈 Evaluating BASELINE model...")
        start_time = time.time()
        baseline_ppl = self.compute_perplexity(self.baseline_model, self.eval_texts)
        baseline_time = time.time() - start_time
        results["baseline"] = {
            "perplexity": baseline_ppl,
            "eval_time": baseline_time,
        }
        print(f"   Perplexity: {baseline_ppl:.4f}")
        print(f"   Evaluation time: {baseline_time:.2f} seconds")

        # Evaluate DAPT model
        if self.dapt_model is None:
            self.dapt_model = self.load_dapt_model()

        if self.dapt_model is not None:
            print("\n📈 Evaluating DAPT model...")
            start_time = time.time()
            dapt_ppl = self.compute_perplexity(self.dapt_model, self.eval_texts)
            dapt_time = time.time() - start_time
            results["dapt"] = {
                "perplexity": dapt_ppl,
                "eval_time": dapt_time,
            }
            print(f"   Perplexity: {dapt_ppl:.4f}")
            print(f"   Evaluation time: {dapt_time:.2f} seconds")
        else:
            print("\n⚠️ DAPT model not available for evaluation")
            results["dapt"] = None

        return results

    def print_results(self, results):
        """Print formatted evaluation results"""
        print("\n" + "=" * 70)
        print("🎯 EVALUATION RESULTS")
        print("=" * 70)

        print(f"Dataset: {self.dataset_path}")
        print(f"Samples evaluated: {len(self.eval_texts)}")
        print(f"Max sequence length: {self.max_length}")
        print()

        if "baseline" in results and results["baseline"]:
            baseline_ppl = results["baseline"]["perplexity"]
            baseline_time = results["baseline"]["eval_time"]
            print("BASELINE LLAMA 3.1:")
            print(f"   Perplexity: {baseline_ppl:.4f}")
            print(f"   Evaluation time: {baseline_time:.2f} seconds")
        if "dapt" in results and results["dapt"]:
            dapt_ppl = results["dapt"]["perplexity"]
            dapt_time = results["dapt"]["eval_time"]
            print("\nDAPT MODEL:")
            print(f"   Perplexity: {dapt_ppl:.4f}")
            print(f"   Evaluation time: {dapt_time:.2f} seconds")
            # Comparison
            if "baseline" in results and results["baseline"]:
                baseline_ppl = results["baseline"]["perplexity"]
                improvement = ((baseline_ppl - dapt_ppl) / baseline_ppl) * 100.0
                print("\nCOMPARISON:")
                print(f"   Baseline PPL: {baseline_ppl:.4f}")
                print(f"   DAPT PPL:     {dapt_ppl:.4f}")
                print(f"   Improvement:  {improvement:.2f}%")
                if dapt_ppl < baseline_ppl:
                    print("✅ SUCCESS: DAPT model outperforms baseline!")
                    print("   The domain-adaptive pretraining improved performance on earnings call data.")
                else:
                    print("⚠️  NOTE: DAPT model does not outperform baseline")
                    print("   Consider adjusting training parameters or dataset.")
        else:
            print("\n❌ DAPT model evaluation failed or not available")

        print("\n" + "-" * 70)
        print("📝 INTERPRETATION")
        print("-" * 70)
        print("Perplexity measures how well the model predicts the next token in sequences.")
        print("Lower perplexity = better predictive performance on the domain.")
        print("Typical perplexity ranges: 10-100+ (lower is better)")
        print()
        print("Earnings call transcripts contain specialized financial language,")
        print("so domain adaptation should ideally reduce perplexity compared to baseline.")

    def run_evaluation(self):
        """Run the complete evaluation pipeline"""
        try:
            # Setup
            self.setup_tokenizer()
            self.load_dataset()
            self.load_baseline_model()
            self.load_dapt_model()

            # Evaluate
            results = self.evaluate_models()

            # Display results
            self.print_results(results)

            return results

        except Exception as e:
            print(f"❌ Evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description="Evaluate DAPT model vs baseline perplexity")
    parser.add_argument("--model-id", default="meta-llama/Llama-3.1-8B", help="Base model ID")
    parser.add_argument(
        "--dapt-path",
        default="/u/v/d/vdhanuka/llama3_8b_dapt_transcripts_lora",
        help="Path to DAPT LoRA adapters",
    )
    parser.add_argument(
        "--dataset",
        default="/u/v/d/vdhanuka/defeatbeta-api-main/stock_earning_call_transcripts.parquet",
        help="Path to evaluation dataset",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Number of samples to evaluate (mutually exclusive with --sample-percentage)",
    )
    parser.add_argument(
        "--sample-percentage",
        type=float,
        default=None,
        help="Percentage of dataset to evaluate (0.0-1.0, mutually exclusive with --sample-size)",
    )
    parser.add_argument("--max-length", type=int, default=1024, help="Maximum sequence length")
    parser.add_argument("--no-qlora", action="store_true", help="Disable QLoRA quantization")
    parser.add_argument("--device", default=None, help="Device to use (cuda/cpu)")

    args = parser.parse_args()

    # Validate mutually exclusive arguments
    if args.sample_size is not None and args.sample_percentage is not None:
        parser.error("--sample-size and --sample-percentage are mutually exclusive")
    if args.sample_size is None and args.sample_percentage is None:
        args.sample_size = 1000  # Default to 500 samples

    # Create evaluator
    evaluator = DAPTEvaluator(
        model_id=args.model_id,
        dapt_model_path=args.dapt_path,
        dataset_path=args.dataset,
        sample_size=args.sample_size,
        sample_percentage=args.sample_percentage,
        max_length=args.max_length,
        use_qlora=not args.no_qlora,
        device=args.device,
    )

    # Run evaluation
    results = evaluator.run_evaluation()
    return results


if __name__ == "__main__":
    # Set random seed for reproducible sampling
    np.random.seed(42)
    torch.manual_seed(42)

    main()
