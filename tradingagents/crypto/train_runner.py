"""15-minute crypto training runner for Binance/Gemini mode."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from tradingagents.agents.utils.crypto_memory import CryptoTrainingMemory
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.crypto_data import get_crypto_indicator, get_crypto_ohlcv
from tradingagents.dataflows.crypto_news import get_crypto_news, get_global_crypto_news
from tradingagents.dataflows.crypto_sentiment import get_crypto_fear_greed, get_crypto_reddit_sentiment
from tradingagents.default_config import CRYPTO_TRAIN_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.google_key_rotator import parse_google_api_keys

logger = logging.getLogger(__name__)


class CryptoTrainRunner:
    """Run the crypto-focused TradingAgents graph over a watchlist."""

    def __init__(
        self,
        watchlist: Iterable[str],
        config: Optional[Dict] = None,
        debug: bool = False,
        profile: str = "compact",
    ):
        self.config = CRYPTO_TRAIN_CONFIG.copy()
        if config:
            self.config.update(config)
        # Freshen google_api_keys from env in case dotenv was loaded after default_config import.
        if not self.config.get("google_api_keys"):
            self.config["google_api_keys"] = os.getenv("GOOGLE_API_KEYS", "")
        self.watchlist = list(watchlist or self.config.get("crypto_watchlist", []))
        if not self.watchlist:
            raise ValueError("CryptoTrainRunner requires at least one symbol, e.g. BTC/USDT")
        self.debug = debug
        if profile not in {"compact", "full"}:
            raise ValueError("profile must be 'compact' or 'full'")
        self.profile = profile

    def run_once(self) -> Dict[str, str]:
        """Run one training pass for every symbol in the watchlist."""
        if self.profile == "compact":
            return self._run_compact_once()
        return self._run_full_graph_once()

    def _run_full_graph_once(self) -> Dict[str, str]:
        """Run the original multi-agent graph. Requires materially more Gemini quota."""
        trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        selected_analysts: List[str] = list(self.config.get("selected_analysts", ["market", "news", "social"]))
        memory = CryptoTrainingMemory(self.config)
        results: Dict[str, str] = {}

        for symbol in self.watchlist:
            logger.info("Running crypto train analysis for %s", symbol)
            graph = TradingAgentsGraph(
                selected_analysts=selected_analysts,
                debug=self.debug,
                config=self.config.copy(),
            )
            final_state, decision = graph.propagate(symbol, trade_date)
            memory.store_run(symbol, trade_date, final_state if isinstance(final_state, dict) else {"final_trade_decision": decision})
            results[symbol] = decision
        return results

    def _run_compact_once(self) -> Dict[str, str]:
        """Run a quota-friendly crypto analysis: data tools + one LLM call per symbol."""
        trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        set_config(self.config)
        llm = self._create_compact_llm()
        memory = CryptoTrainingMemory(self.config)
        results: Dict[str, str] = {}

        for symbol in self.watchlist:
            logger.info("Running compact crypto analysis for %s", symbol)
            market = get_crypto_ohlcv(symbol, "", "")
            indicators = "\n\n".join(
                get_crypto_indicator(symbol, indicator, trade_date, look_back_days=7)
                for indicator in ("rsi", "macd", "atr")
            )
            news = get_crypto_news(symbol, "", "")
            global_news = get_global_crypto_news(trade_date, limit=5)
            sentiment = "\n\n".join(
                [get_crypto_fear_greed(days=7), get_crypto_reddit_sentiment(symbol, days=3)]
            )
            lessons = memory.get_past_context(symbol)
            prompt = self._compact_prompt(symbol, trade_date, market, indicators, news, global_news, sentiment, lessons)
            response = llm.invoke(prompt)
            decision = getattr(response, "content", str(response))
            final_state = {
                "final_trade_decision": decision,
                "market_report": f"{market}\n\n{indicators}",
                "news_report": f"{news}\n\n{global_news}",
                "sentiment_report": sentiment,
                "fundamentals_report": "",
                "investment_plan": decision,
                "trader_investment_plan": decision,
            }
            memory.store_run(symbol, trade_date, final_state)
            results[symbol] = decision
        return results

    def _create_compact_llm(self):
        provider = self.config.get("llm_provider", "google")
        kwargs: Dict = {}
        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level
            google_api_keys = parse_google_api_keys(self.config.get("google_api_keys"))
            if google_api_keys:
                kwargs["api_keys"] = google_api_keys
                kwargs["rotation_state_path"] = self.config.get(
                    "google_key_rotation_state_path",
                    os.path.join(self.config["data_cache_dir"], "google_key_rotation.json"),
                )
                kwargs["role"] = "compact"

        return create_llm_client(
            provider=provider,
            model=self.config.get("quick_think_llm"),
            base_url=self.config.get("backend_url"),
            **kwargs,
        ).get_llm()

    @staticmethod
    def _compact_prompt(
        symbol: str,
        trade_date: str,
        market: str,
        indicators: str,
        news: str,
        global_news: str,
        sentiment: str,
        lessons: str,
    ) -> str:
        return f"""Bạn là trợ lý giao dịch crypto cho Binance spot. Phân tích nhanh nhưng thực dụng cho {symbol} vào {trade_date}.

Yêu cầu:
- Trả lời bằng tiếng Việt.
- Không đưa lời khuyên tài chính chắc chắn; đây là phân tích hỗ trợ quyết định.
- Tập trung timeframe 15m, xu hướng ngắn hạn, momentum, volatility, volume, rủi ro tin tức.
- Kết luận phải có đúng các mục: Rating, Confidence, Action, Entry Zone, Stop Loss, Take Profit, Invalidation, Reasoning.
- Action chỉ dùng một trong: BUY, HOLD, SELL, REDUCE, WAIT.
- Nếu tín hiệu không rõ hoặc risk/reward xấu, ưu tiên WAIT/HOLD.

=== MARKET DATA ===
{market}

=== INDICATORS ===
{indicators}

=== SYMBOL NEWS ===
{news}

=== GLOBAL CRYPTO NEWS ===
{global_news}

=== SENTIMENT ===
{sentiment}

=== REVIEWED LESSONS ONLY ===
{lessons or "No reviewed lessons yet."}
"""

    def run_forever(self, interval_minutes: Optional[int] = None) -> None:
        """Run continuously. Default interval is 15 minutes."""
        interval = int(interval_minutes or self.config.get("train_trigger_minutes", 15))
        while True:
            started = time.monotonic()
            try:
                self.run_once()
            except Exception:
                logger.exception("Crypto training pass failed")
            elapsed = time.monotonic() - started
            time.sleep(max(0, interval * 60 - elapsed))

    # ── batch-LLM helpers used by crypto_dashboard.paper_scan_trade_payload ──

    def _signal_context(self, signal, trade_date: str, memory) -> Dict:
        """Collect market data + indicators + news + lessons for one ScanSignal."""
        symbol = signal.symbol
        tf = getattr(signal, "timeframe", self.config.get("crypto_timeframe", "15m"))
        market = get_crypto_ohlcv(symbol, "", "", timeframe=tf)
        indicators = "\n\n".join(
            get_crypto_indicator(symbol, ind, trade_date, look_back_days=7, timeframe=tf) or ""
            for ind in ("rsi", "macd", "atr")
        )
        news = get_crypto_news(symbol, "", "")
        lessons = memory.get_past_context(symbol) if memory else ""
        return {
            "symbol": symbol,
            "timeframe": tf,
            "signal": signal.to_dict(),
            "market": str(market or ""),
            "indicators": str(indicators or ""),
            "news": str(news or ""),
            "lessons": str(lessons or ""),
        }

    def _compact_batch_prompt(
        self,
        trade_date: str,
        signal_contexts: List[Dict],
        global_news: str,
        fear_greed: str,
    ) -> str:
        """Build a single prompt asking the LLM to decide on every signal at once."""
        signals_json = []
        for ctx in signal_contexts:
            sig = ctx.get("signal", {})
            signals_json.append({
                "symbol": ctx["symbol"],
                "timeframe": ctx.get("timeframe", "?"),
                "scanner_strategy": sig.get("strategy"),
                "scanner_action": sig.get("action"),
                "scanner_strength": sig.get("strength"),
                "scanner_rsi": sig.get("rsi"),
                "scanner_market_regime": sig.get("market_regime"),
                "entry": sig.get("entry"),
                "stop_loss": sig.get("stop_loss"),
                "take_profit": sig.get("take_profit"),
                "scanner_reason": sig.get("reason"),
                "market_data": ctx.get("market", "")[:800],
                "indicators": ctx.get("indicators", "")[:600],
                "symbol_news": ctx.get("news", "")[:400],
                "reviewed_lessons": ctx.get("lessons", "")[:500],
            })

        import json as _json
        return f"""Bạn là trợ lý giao dịch crypto spot trên Binance. Phân tích {len(signals_json)} tín hiệu scanner cùng lúc.

Ngày: {trade_date}

=== GLOBAL NEWS ===
{global_news}

=== FEAR & GREED ===
{fear_greed}

=== SCANNER SIGNALS (JSON) ===
{_json.dumps(signals_json, ensure_ascii=False, indent=2)}

Yêu cầu:
- Trả lời bằng JSON object với key "decisions" là array, mỗi phần tử có: symbol, action, confidence, reasoning.
- Action chỉ dùng: BUY, SELL, WAIT, HOLD.
- Nếu tín hiệu không đủ mạnh hoặc risk/reward xấu → action=WAIT, confidence < 0.5.
- Chỉ action=BUY khi scanner strength ≥ 0.55, setup rõ ràng, và không có news tiêu cực.
- Reasoning bằng tiếng Việt, ngắn gọn (1-2 câu).
- Trả về JSON thuần, không markdown.

JSON:"""
