import json
import logging
import os
from datetime import datetime, timezone

from orchestrator.config import OrchestratorConfig
from orchestrator.signals import Signal

logger = logging.getLogger(__name__)


class LLMRunner:
    def __init__(self, config: OrchestratorConfig):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        trading_cfg = config.trading_agents_config if config.trading_agents_config else None
        self.graph = TradingAgentsGraph(config=trading_cfg)
        self.cache_dir = config.cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_signal(self, ticker: str, date: str) -> Signal:
        """获取指定股票在指定日期的 LLM 信号，带缓存。"""
        cache_path = os.path.join(self.cache_dir, f"{ticker}_{date}.json")

        if os.path.exists(cache_path):
            logger.info("LLMRunner: cache hit for %s %s", ticker, date)
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            direction, confidence = self._map_rating(data["rating"])
            return Signal(
                ticker=ticker,
                direction=direction,
                confidence=confidence,
                source="llm",
                timestamp=datetime.fromisoformat(data["timestamp"]),
                metadata=data,
            )

        try:
            _final_state, processed_signal = self.graph.propagate(ticker, date)
            rating = processed_signal if isinstance(processed_signal, str) else str(processed_signal)
            direction, confidence = self._map_rating(rating)
            now = datetime.now(timezone.utc)

            cache_data = {
                "rating": rating,
                "direction": direction,
                "confidence": confidence,
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "date": date,
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            return Signal(
                ticker=ticker,
                direction=direction,
                confidence=confidence,
                source="llm",
                timestamp=now,
                metadata=cache_data,
            )
        except Exception as e:
            logger.error("LLMRunner: propagate failed for %s %s: %s", ticker, date, e)
            return Signal(
                ticker=ticker,
                direction=0,
                confidence=0.0,
                source="llm",
                timestamp=datetime.now(timezone.utc),
                metadata={"error": str(e)},
            )

    def _map_rating(self, rating: str) -> tuple[int, float]:
        """将 5 级评级映射为 (direction, confidence)。"""
        mapping = {
            "BUY": (1, 0.9),
            "OVERWEIGHT": (1, 0.6),
            "HOLD": (0, 0.5),
            "UNDERWEIGHT": (-1, 0.6),
            "SELL": (-1, 0.9),
        }
        result = mapping.get(rating.upper() if rating else "", None)
        if result is None:
            logger.warning("LLMRunner: unknown rating %r, falling back to HOLD", rating)
            return (0, 0.5)
        return result
