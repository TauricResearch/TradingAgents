#!/usr/bin/env python3
import argparse
import json
import os
import re
from typing import Dict, List, Tuple, Optional

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer
from peft import PeftModel


def load_sft_model(model_name_or_path: str):
	"""
	Load the fine-tuned (SFT) sequence classification model and tokenizer.
	"""
	tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, use_fast=True)
	model = AutoModelForSequenceClassification.from_pretrained(model_name_or_path)
	model.eval()
	return tokenizer, model


def classify_with_confidence(
	tokenizer: AutoTokenizer,
	model: AutoModelForSequenceClassification,
	texts: List[str],
) -> List[Tuple[str, float]]:
	"""
	Run sentiment classification and return (label, confidence) for each text.
	Confidence is defined as max softmax(logits).
	"""
	results: List[Tuple[str, float]] = []

	# Batch to speed up a bit
	batch_size = 16
	id2label = getattr(model.config, "id2label", None)
	if not id2label:
		# Align with finetune_dapt.py label set: Negative, Neutral, Positive
		id2label = {0: "Negative", 1: "Neutral", 2: "Positive"}

	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
	model = model.to(device)

	for start in range(0, len(texts), batch_size):
		chunk = texts[start : start + batch_size]
		enc = tokenizer(
			chunk,
			padding=True,
			truncation=True,
			max_length=256,
			return_tensors="pt",
		)
		enc = {k: v.to(device) for k, v in enc.items()}
		with torch.no_grad():
			out = model(**enc)
			logits = out.logits  # [batch, num_labels]
			probs = torch.softmax(logits, dim=-1)
			confidences, indices = torch.max(probs, dim=-1)
			for idx in range(len(chunk)):
				label_idx = indices[idx].item()
				label = id2label.get(label_idx, str(label_idx))
				# normalize label casing (positive/negative/neutral)
				label_norm = label.lower()
				results.append((label_norm, float(confidences[idx].item())))
	return results


def build_ticker_context(company: str, ticker: str) -> str:
	"""
	Build a short textual context for the ticker to be used for embeddings.
	"""
	# Very lightweight template; can be extended with sector/description if available
	return f"{company}, {ticker}, company, stock, shares"


def tokenize(text: str) -> List[str]:
	"""
	Simple alphanumeric tokenization, lowercased.
	"""
	return re.findall(r"[A-Za-z0-9]+", text.lower())


def keyword_boost(title: str, ticker_context: str, company: Optional[str] = None, ticker: Optional[str] = None) -> float:
	"""
	Simple, interpretable keyword/meta boost combining:
	- +0.4 if title explicitly mentions the company name or ticker
	- +0.2 if title mentions competitor/sector keywords
	- Base overlap from Jaccard(title_tokens, context_tokens)
	- Reduce base if the title is macro-level (economy/markets-wide)
	"""
	title_tokens = set(tokenize(title))
	context_tokens = set(tokenize(ticker_context))

	# Add a small set of generic market keywords to context to better capture overlap
	generic_keywords = {
		"stock", "stocks", "share", "shares", "price", "profit", "profits", "loss",
		"results", "earnings", "revenue", "deal", "merger", "acquisition", "jobs",
		"cut", "cuts", "dividend", "rises", "falls", "up", "down", "guidance",
		"forecast", "outlook", "sponsor", "sponsorship", "board", "turmoil",
	}
	context_tokens |= generic_keywords

	# Base overlap via Jaccard
	union = title_tokens | context_tokens
	inter = title_tokens & context_tokens
	base_overlap = float(len(inter) / len(union)) if union else 0.0

	# Company/ticker explicit mention (+0.4)
	title_lower = title.lower()
	company_mention = False
	if company:
		if company.lower() in title_lower:
			company_mention = True
	if ticker:
		# substring check to avoid tokenizer punctuation issues (e.g., BRK.B)
		if ticker.lower() in title_lower:
			company_mention = True

	# Competitor/sector keywords (+0.2) — keep set small and generic
	competitor_words = {
		"competitor", "competitors", "rival", "rivals", "peer", "peers", "competition",
	}
	sector_words = {
		"technology", "tech", "semiconductor", "chip", "software", "hardware",
		"bank", "banks", "finance", "financials", "insurance",
		"energy", "oil", "gas", "utilities",
		"retail", "consumer", "automotive", "auto",
		"healthcare", "pharma", "biotech",
		"telecom", "communications", "media",
		"aerospace", "defense", "industrial",
		"mining", "metals",
		"travel", "airline", "hospitality",
		"ecommerce", "cloud", "ai", "artificial", "intelligence",
	}
	competitor_or_sector = bool(title_tokens & (competitor_words | sector_words))

	# Macro-level hints → dampen base overlap
	macro_words = {
		"market", "markets", "economy", "economic", "macro", "inflation", "rates",
		"interest", "fed", "federal", "policy", "geopolitical", "tariff", "trade",
		"sector-wide", "industry-wide", "stocks", "equities",
	}
	is_macro = bool(title_tokens & macro_words)

	kb = base_overlap
	if is_macro:
		kb *= 0.6  # dampen base if distant/macro
	if company_mention:
		kb += 0.4
	if competitor_or_sector:
		kb += 0.2

	return float(np.clip(kb, 0.0, 1.0))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
	"""
	Cosine similarity for L2-normalized vectors is their dot product.
	Ensure inputs are 1D arrays.
	"""
	a = a.reshape(-1)
	b = b.reshape(-1)
	den = (np.linalg.norm(a) * np.linalg.norm(b))
	if den == 0.0:
		return 0.0
	return float(np.dot(a, b) / den)


def compute_relevance(
	embedder: SentenceTransformer,
	title: str,
	company: str,
	ticker: str,
	beta: float = 0.7,
) -> float:
	"""
	By default:
	relevance = 0.7 * cosine_sim(e_news, e_ticker) + 0.3 * keyword_boost
	where e_* are sentence embeddings and keyword_boost includes simple meta/keyword rules.
	"""
	beta = float(np.clip(beta, 0.0, 1.0))
	ticker_ctx = build_ticker_context(company, ticker)

	embs = embedder.encode([title, ticker_ctx], normalize_embeddings=True)
	e_news = embs[0]
	e_ticker = embs[1]

	cos_sim = cosine_similarity(np.asarray(e_news), np.asarray(e_ticker))
	kb = keyword_boost(title, ticker_ctx, company=company, ticker=ticker)
	relevance = beta * cos_sim + (1.0 - beta) * kb
	# Clip to [0, 1] for interpretability
	return float(np.clip(relevance, 0.0, 1.0))


def default_ticker_for_company(company: str) -> str:
	"""
	Approximate mapping from company names in the sample dataset to tickers.
	Falls back to an uppercase abbreviation if unknown.
	"""
	mapping: Dict[str, str] = {
		"Tesco": "TSCO",
		"CRH": "CRH",
		"Holcim Lafarge": "LHN",
		"Reed Elsevier": "RELX",
		"Kingfisher": "KGF",
		"Mr Bricolage": "MRB",
		"Glencore": "GLEN",
		"Diageo": "DGE",
		"Shell": "SHEL",
		"Shire": "SHP",
		"Baxalta": "BXLT",
		"BP": "BP",
		"HSBC": "HSBA",
		"Standard Chartered": "STAN",
	}
	if company in mapping:
		return mapping[company]
	# Fallback: uppercase initials (e.g., "Reed Elsevier" -> "RE")
	initials = "".join([w[0] for w in company.split() if w])
	return initials.upper() or company.upper()


def round_float(value: float, ndigits: int = 2) -> float:
	"""
	Round float safely; ensures standard Python rounding and float type.
	"""
	return float(round(value, ndigits))


def label_to_numeric(label: str) -> int:
	"""
	Map textual sentiment to numeric scheme: Negative=-1, Neutral=0, Positive=1.
	"""
	mapping = {"negative": -1, "neutral": 0, "positive": 1}
	return int(mapping.get(label.lower(), 0))


def build_instruction_prompt(text: str) -> str:
	"""
	Match the finetune_dapt.py instruction template for consistent scoring.
	"""
	return (
		"### Instruction:\n"
		"Classify the sentiment of the following financial text.\n\n"
		f"### Text:\n{text}\n\n"
		"### Response:\n"
	)


def load_lora_causal_model(base_model_id: str, adapters_path: str, hf_token: str = None):
	"""
	Load base causal LM and attach LoRA adapters for SFT scoring via prompting.
	"""
	# Keep simple, no quantization by default here
	model = AutoModelForCausalLM.from_pretrained(
		base_model_id,
		device_map="auto" if torch.cuda.is_available() else None,
		low_cpu_mem_usage=True,
		token=hf_token,
	)
	tokenizer = AutoTokenizer.from_pretrained(base_model_id, use_fast=True, token=hf_token)
	if tokenizer.pad_token is None:
		tokenizer.pad_token = tokenizer.eos_token
	try:
		tokenizer.padding_side = "left"
	except Exception:
		pass
	model = PeftModel.from_pretrained(model, adapters_path)
	model.eval()
	return tokenizer, model


def score_labels_with_lora(
	tokenizer: AutoTokenizer,
	model: AutoModelForCausalLM,
	prompts: List[str],
	label_texts: List[str],
) -> List[Tuple[str, float]]:
	"""
	Compute sentiment label and confidence using LoRA causal LM by scoring
	log-likelihood of label strings conditioned on the prompt.
	Returns (label_str_lowercase, confidence_softmax_over_labels).
	"""
	results: List[Tuple[str, float]] = []
	batch_size = 2

	# Pre-tokenize label targets
	label_ids_list = [tokenizer.encode(lbl, add_special_tokens=False) for lbl in label_texts]

	for start in range(0, len(prompts), batch_size):
		chunk = prompts[start : start + batch_size]
		enc = tokenizer(
			chunk,
			padding=True,
			truncation=True,
			max_length=512,
			return_tensors="pt",
		)
		# Determine embedding device similar to evaluation_sft.py to avoid full model move
		try:
			embed_device = model.base_model.get_input_embeddings().weight.device  # type: ignore
		except Exception:
			try:
				embed_device = model.get_input_embeddings().weight.device  # type: ignore
			except Exception:
				embed_device = next(model.parameters()).device
		input_ids = enc["input_ids"].to(embed_device)
		attention_mask = enc["attention_mask"].to(embed_device)

		# For each sample in batch, score each label by teacher-forcing the label tokens
		with torch.no_grad():
			for i in range(input_ids.size(0)):
				prompt_ids = input_ids[i]
				prompt_len = int(attention_mask[i].sum().item())
				# Store log-likelihood per label
				label_logps = []
				for label_ids in label_ids_list:
					# Concatenate prompt + label
					target_ids = torch.tensor(label_ids, dtype=torch.long, device=embed_device)
					concat_ids = torch.cat([prompt_ids[:prompt_len], target_ids], dim=0).unsqueeze(0)
					concat_mask = torch.ones_like(concat_ids, device=embed_device)
					out = model(input_ids=concat_ids, attention_mask=concat_mask)
					logits = out.logits  # [1, seq_len, vocab]
					log_probs = torch.log_softmax(logits, dim=-1)
					# Sum log-probs of each label token conditioned on preceding tokens
					lp_sum = 0.0
					for k, tok in enumerate(target_ids):
						# Position of token is prompt_len + k; use logits at previous position
						pos = prompt_len + k
						prev_pos = pos - 1
						if prev_pos < 0:
							continue
						lp = log_probs[0, prev_pos, tok.item()].item()
						lp_sum += lp
					label_logps.append(lp_sum)
				# Softmax over label log-likelihoods to get confidence
				logps_np = np.array(label_logps, dtype=np.float64)
				# numerical stability
				m = np.max(logps_np)
				exp = np.exp(logps_np - m)
				probs = exp / np.sum(exp)
				best_idx = int(np.argmax(probs))
				best_label = label_texts[best_idx].lower()
				best_conf = float(probs[best_idx])
				results.append((best_label, best_conf))
	return results


def lora_diagnostics(model: AutoModelForCausalLM) -> Dict[str, object]:
	"""
	Return basic diagnostics about LoRA adapter loading.
	"""
	diag: Dict[str, object] = {}
	try:
		adapter_names = getattr(model, "active_adapters", None)
		if adapter_names is None:
			# newer peft exposes 'peft_config' dict and 'active_adapter'
			peft_cfg = getattr(model, "peft_config", None)
			if isinstance(peft_cfg, dict):
				adapter_names = list(peft_cfg.keys())
		diag["adapter_names"] = adapter_names
	except Exception:
		diag["adapter_names"] = None

	# Count trainable LoRA parameters
	total_params = 0
	lora_trainable = 0
	lora_total = 0
	for name, p in model.named_parameters():
		num = p.numel()
		total_params += num
		if "lora_" in name:
			lora_total += num
			if p.requires_grad:
				lora_trainable += num
	diag["total_params"] = total_params
	diag["lora_total_params"] = lora_total
	diag["lora_trainable_params"] = lora_trainable
	diag["lora_trainable_pct"] = (float(lora_trainable) / float(total_params)) if total_params else 0.0
	return diag


def main():
	parser = argparse.ArgumentParser(description="Compute sentiment confidence and relevance for headlines.")
	parser.add_argument(
		"--dataset",
		type=str,
		default="/u/v/d/vdhanuka/defeatbeta-api-main/Headline_Trialdata.json",
		help="Path to Headline_Trialdata.json",
	)
	parser.add_argument(
		"--output",
		type=str,
		default="/u/v/d/vdhanuka/defeatbeta-api-main/headline_results1.json",
		help="Where to write the results JSON.",
	)
	parser.add_argument(
		"--sft_model",
		type=str,
		default=os.environ.get("SFT_MODEL_NAME", "distilbert-base-uncased-finetuned-sst-2-english"),
		help="Hugging Face model path/name for SFT classifier.",
	)
	parser.add_argument(
		"--use_lora_sft",
		action="store_true",
		help="Use LoRA SFT adapters on a causal LM (meta-llama) for scoring instead of a classifier.",
	)
	parser.add_argument(
		"--diagnose_lora",
		action="store_true",
		help="Print diagnostics about loaded LoRA adapters and run a quick probe.",
	)
	parser.add_argument(
		"--diagnose_only",
		action="store_true",
		help="If set with --use_lora_sft, run diagnostics/probe and exit without processing dataset.",
	)
	parser.add_argument(
		"--base_model_id",
		type=str,
		default=os.environ.get("BASE_MODEL_ID", "meta-llama/Llama-3.1-8B"),
		help="Base model ID for LoRA SFT mode.",
	)
	parser.add_argument(
		"--adapters_path",
		type=str,
		default=os.environ.get("ADAPTERS_PATH", "/u/v/d/vdhanuka/defeatbeta-api-main/dapt_sft_adapters_e4_60_20_20"),
		help="Path to LoRA adapters for LoRA SFT mode.",
	)
	parser.add_argument(
		"--embedding_model",
		type=str,
		default=os.environ.get("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
		help="Sentence-Transformers model for embeddings.",
	)
	parser.add_argument(
		"--beta",
		type=float,
		default=float(os.environ.get("RELEVANCE_BETA", 0.8)),
		help="Weight for semantic similarity in relevance calculation (0.7 - 0.9 recommended).",
	)
	parser.add_argument(
		"--max_items",
		type=int,
		default=0,
		help="If > 0, limit processing to first N items (useful for quick checks).",
	)
	args = parser.parse_args()

	# Load dataset
	with open(args.dataset, "r", encoding="utf-8") as f:
		data = json.load(f)
	if not isinstance(data, list):
		raise ValueError("Dataset must be a JSON list of headline objects.")

	if args.max_items and args.max_items > 0:
		data = data[: args.max_items]

	# Prepare models
	embedder = SentenceTransformer(args.embedding_model)

	# Sentiment path: classifier or LoRA SFT
	if args.use_lora_sft:
		hf_token = (
			os.getenv("HUGGING_FACE_HUB_TOKEN")
			or os.getenv("HF_TOKEN")
			or os.getenv("HUGGINGFACEHUB_API_TOKEN")
		)
		causal_tokenizer, causal_model = load_lora_causal_model(args.base_model_id, args.adapters_path, hf_token)
		if args.diagnose_lora:
			diag = lora_diagnostics(causal_model)
			print("[LoRA] Diagnostics:", json.dumps(diag, indent=2))
			# Quick probe
			probe_prompt = build_instruction_prompt("Stocks rose after strong earnings.")
			label_texts = ["Positive", "Neutral", "Negative"]
			probe = score_labels_with_lora(causal_tokenizer, causal_model, [probe_prompt], label_texts)
			if probe:
				lbl, conf = probe[0]
				print(f"[LoRA] Probe prediction: {lbl} (confidence={conf:.3f})")
			if args.diagnose_only:
				return
		prompts = [build_instruction_prompt(item.get("title", "")) for item in data]
		label_texts = ["Positive", "Neutral", "Negative"]
		sent_conf = score_labels_with_lora(causal_tokenizer, causal_model, prompts, label_texts)
	else:
		tokenizer, model = load_sft_model(args.sft_model)
		# Collect texts for batch classification
		texts = [item.get("title", "") for item in data]
		sent_conf = classify_with_confidence(tokenizer, model, texts)

	# Normalize mapping when using LoRA path (already lowercase strings returned)
	def to_numeric(lbl: str) -> int:
		return label_to_numeric(lbl)

	results = []
	for item, (label, conf) in zip(data, sent_conf):
		title = item.get("title", "")
		company = item.get("company", "")
		ticker = default_ticker_for_company(company)
		relevance = compute_relevance(embedder, title, company, ticker, beta=args.beta)
		results.append({
			"id": item.get("id"),
			"title": title,
			"company": company,
			"sentiment": label,
			"sentiment_score": to_numeric(label),
			"confidence": round_float(conf, 2),
			"relevance": round_float(relevance, 2),
			"ticker": ticker,
		})

	# Write output
	with open(args.output, "w", encoding="utf-8") as f:
		json.dump(results, f, ensure_ascii=False, indent=2)

	print(f"Wrote {len(results)} results to: {args.output}")


if __name__ == "__main__":
	main()


