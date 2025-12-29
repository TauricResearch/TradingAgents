from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime, timedelta
from tradingagents.agents.utils.agent_utils import get_news, get_global_news
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.news_parsers import parse_stock_news, parse_global_news
import sys
from typing import List, Dict, Any, Tuple, Optional

# Add external utilities path for confidence/relevance and LoRA scoring
CONF_UTILS_PATH = "Root Path"
if CONF_UTILS_PATH not in sys.path:
    sys.path.append(CONF_UTILS_PATH)

# Import confidence utilities
try:
    import confidence as conf  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
    print("[NEWS_ANALYST] Successfully imported confidence and sentence_transformers")
except Exception as _e:
    print(f"[NEWS_ANALYST] Failed to import confidence utilities: {_e}")
    conf = None  # type: ignore
    SentenceTransformer = None  # type: ignore


def create_news_analyst(llm):
    # Lazy singletons for model and embedder to avoid reloading every call
    lora_loaded: Dict[str, Any] = {"tokenizer": None, "model": None, "embedder": None}

    def _ensure_models():
        """Load SFT LoRA model and embedder only if use_sft_sentiment is enabled"""
        cfg = get_config()
        use_sft = cfg.get("use_sft_sentiment", False)  # Default to False for original behavior
        
        if not use_sft:
            # Skip loading SFT models if disabled
            print("[NEWS_ANALYST] SFT sentiment disabled - using fallback sentiment analysis")
            return False
            
        if conf is None:
            raise RuntimeError("confidence.py utilities not available on sys.path.")
        if lora_loaded["tokenizer"] is None or lora_loaded["model"] is None:
            # Use configured SFT adapter path
            adapters_path = cfg.get("sft_adapter_path", "PATH")
            base_model_id = "meta-llama/Llama-3.1-8B"
            print(f"[NEWS_ANALYST] Loading SFT LoRA model from: {adapters_path}")
            tok, mdl = conf.load_lora_causal_model(base_model_id, adapters_path)
            lora_loaded["tokenizer"] = tok
            lora_loaded["model"] = mdl
            print("[NEWS_ANALYST] SFT LoRA model loaded successfully")
        if lora_loaded["embedder"] is None:
            if SentenceTransformer is None:
                raise RuntimeError("sentence-transformers not available for relevance computation.")
            print("[NEWS_ANALYST] Loading sentence transformer embedder...")
            lora_loaded["embedder"] = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            print("[NEWS_ANALYST] Embedder loaded successfully")
        return True

    def _score_items(
        items: List[Dict[str, Any]],
        company: str,
        ticker: str,
        alpha: float,
        beta_relevance: float,
    ) -> Tuple[List[Dict[str, Any]], float, str]:
        """
        Score each item with sentiment (LoRA) + confidence and relevance, then compute
        net sentiment as sum(w_i * S_i) / sum(w_i), where w_i = alpha*confidence + (1-alpha)*relevance.
        S_i in {-1, 0, 1}.
        
        If SFT sentiment is disabled, returns empty scoring.
        """
        if not items:
            return [], 0.0, "Neutral"

        # Check if SFT models should be loaded
        sft_enabled = _ensure_models()
        if not sft_enabled:
            # SFT disabled - return items without sentiment scoring
            print("[NEWS_ANALYST] Returning items without SFT sentiment scores (disabled)")
            return items, 0.0, "Neutral"
            
        tokenizer = lora_loaded["tokenizer"]
        model = lora_loaded["model"]
        embedder = lora_loaded["embedder"]

        # Build prompts from item text
        texts: List[str] = []
        for it in items:
            # Priority: raw -> headline -> title -> summary
            text = it.get("raw") or it.get("headline") or it.get("title") or it.get("summary") or ""
            texts.append(text)
        prompts = [conf.build_instruction_prompt(t) for t in texts]

        # Sentiment via LoRA scoring (label, confidence)
        label_texts = ["Positive", "Neutral", "Negative"]
        sent_conf: List[Tuple[str, float]] = conf.score_labels_with_lora(tokenizer, model, prompts, label_texts)

        scored_items: List[Dict[str, Any]] = []
        weighted_sum = 0.0
        weight_total = 0.0

        for it, (lbl, conf_score), txt in zip(items, sent_conf, texts):
            # lbl already lowercased in confidence.py output path
            numeric = conf.label_to_numeric(lbl)
            # Relevance using embedder, company name (if available) and ticker
            relevance = conf.compute_relevance(embedder, txt if len(txt) <= 160 else (it.get("title") or txt[:160]), company or ticker, ticker, beta=beta_relevance)
            weight = float(alpha) * float(conf_score) + float(1.0 - alpha) * float(relevance)

            scored = dict(it)
            scored.update(
                {
                    "sentiment_label": lbl,
                    "sentiment_score": int(numeric),  # -1/0/1
                    "confidence": float(round(conf_score, 3)),
                    "relevance": float(round(relevance, 3)),
                    "weight": float(round(weight, 3)),
                }
            )
            scored_items.append(scored)
            weighted_sum += weight * numeric
            weight_total += weight

        net_score = 0.0 if weight_total == 0.0 else float(weighted_sum / weight_total)
        net_label = "Positive" if net_score > 0.2 else ("Negative" if net_score < -0.2 else "Neutral")
        return scored_items, net_score, net_label

    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # Compute 7-day lookback window
        try:
            end_dt = datetime.strptime(current_date, "%Y-%m-%d")
            start_dt = end_dt - timedelta(days=7)
            start_date = start_dt.strftime("%Y-%m-%d")
        except Exception:
            # Fallback: use the same day if parsing fails
            start_date = current_date

        # Fetch company-specific news and global macro news via tools
        company_news = ""
        global_news = ""
        try:
            company_news = get_news.invoke({"ticker": ticker, "start_date": start_date, "end_date": current_date}) or ""
        except Exception:
            company_news = ""
        try:
            global_news = get_global_news.invoke({"curr_date": current_date, "look_back_days": 7, "limit": 8}) or ""
        except Exception:
            global_news = ""

        # Build a data-grounded instruction and feed fetched data to the LLM
        # Use completion-style prompt that works better with causal LMs (DAPT model)
        system_instruction = (
            "You are a financial news analyst. Your task is to write a trading-relevant report "
            "based on the news data provided below.\n\n"
            "IMPORTANT: Do NOT repeat or echo any part of this prompt. Do NOT ask questions. "
            "Do NOT output task lists or checklists. Start writing the report directly.\n\n"
            f"Date: {current_date}\n"
            f"Company: {ticker}\n\n"
            f"=== Company News ({ticker}, {start_date} to {current_date}) ===\n{company_news}\n\n"
            f"=== Global/Macro News (last 7 days) ===\n{global_news}\n\n"
            "=== END OF NEWS DATA ===\n\n"
            "Now write a comprehensive analysis report with trading implications. "
            "End with a Markdown table summarizing key points."
        )

        # Use a single HumanMessage with a starter phrase to guide completion
        # This helps causal LMs continue naturally instead of echoing
        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=f"Write the {ticker} news analysis report now:"),
        ]
        result = llm.invoke(messages)

        report = ""

        # Use the generated content as the report
        raw_report = getattr(result, "content", "") or ""
        
        # Post-process: remove any echoed prompt fragments
        # Common echo patterns to filter out
        echo_patterns = [
            "Write the",
            "Produce the final report",
            "news analysis report now",
            "using the fetched data above",
        ]
        report = raw_report
        for pattern in echo_patterns:
            if report.strip().startswith(pattern):
                # Remove the echoed line
                lines = report.split('\n', 1)
                report = lines[1] if len(lines) > 1 else ""
        report = report.strip()

        # Now (after report generation), parse and compute net sentiment (keep logic intact)
        company_items = parse_stock_news(company_news) if company_news else []
        global_items = parse_global_news(global_news) if global_news else []

        cfg = get_config()
        alpha = float(cfg.get("sentiment_conf_alpha", 0.7))
        beta_relevance = float(cfg.get("relevance_beta", 0.8))

        all_items = []
        all_items.extend([dict(x, source="company") for x in company_items])
        all_items.extend([dict(x, source="global") for x in global_items])

        news_items_scored: List[Dict[str, Any]] = []
        news_net_sentiment_score: float = 0.0
        news_net_sentiment_label: str = "Neutral"

        if (company_items or global_items) and conf is not None:
            try:
                news_items_scored, news_net_sentiment_score, news_net_sentiment_label = _score_items(
                    all_items,
                    company=ticker,
                    ticker=ticker,
                    alpha=alpha,
                    beta_relevance=beta_relevance,
                )
            except Exception as e:
                print(f"[NEWS_ANALYST] Sentiment scoring failed: {e}")
                import traceback
                traceback.print_exc()
                news_items_scored = []
                news_net_sentiment_score = 0.0
                news_net_sentiment_label = "Neutral"
        else:
            if conf is None:
                print("[NEWS_ANALYST] conf module not loaded - sentiment scoring skipped")
            if not (company_items or global_items):
                print("[NEWS_ANALYST] No news items to score")

        return {
            "messages": [result],
            "news_report": report,
            # New outputs for FinLLama
            "news_items_scored": news_items_scored,
            "news_net_sentiment_score": news_net_sentiment_score,
            "news_net_sentiment_label": news_net_sentiment_label,
        }

    return news_analyst_node
