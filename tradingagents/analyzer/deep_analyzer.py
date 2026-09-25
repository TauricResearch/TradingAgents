"""Rule-based crypto analyzer used before optional LLM review.

This module is deliberately deterministic so it can be backtested. It combines
scanner output with the global lesson memory and emits a structured signal that
can be sent to Telegram or stored in raw memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from tradingagents.memory.trade_memory import TradeMemory
from tradingagents.scanner import ScanSignal


class DeepCryptoAnalyzer:
    """Turn a scanner signal into a trade-support signal."""

    def __init__(self, memory: Optional[TradeMemory] = None, mode_id: str = "td1"):
        self.memory = memory
        self.mode_id = mode_id

    def analyze(self, signal: ScanSignal, mode: str = "training") -> Dict:
        global_context = self.memory.get_global_context(signal.symbol) if self.memory else ""
        action = signal.action
        confidence = signal.strength
        risk_flags = []

        if signal.market_regime == "sideway" and signal.strategy == "breakout":
            confidence -= 0.10
            risk_flags.append("breakout_in_sideway_market")
        if signal.volume_spike < 1.2 and signal.strategy == "breakout":
            confidence -= 0.15
            risk_flags.append("weak_volume_confirmation")
        if action == "SELL":
            risk_flags.append("spot_sell_signal_should_be_reduce_or_skip_unless_shorting_enabled")

        confidence = max(0.0, min(1.0, round(confidence, 4)))
        approved_for_trade = mode == "trade" and confidence >= 0.75 and not global_context.startswith("No validated")

        return {
            "trade_id": f"{signal.symbol.replace('/', '')}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "mode_id": self.mode_id,
            "strategy": signal.strategy,
            "timeframe": signal.timeframe,
            "coin": signal.symbol,
            "signal": action,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "confidence": confidence,
            "approved_for_trade": approved_for_trade,
            "market_context": {
                "rsi": signal.rsi,
                "atr": signal.atr,
                "volume_spike": signal.volume_spike,
                "market_regime": signal.market_regime,
            },
            "risk_flags": risk_flags,
            "reasoning": signal.reason,
            "global_lesson_context": global_context,
            "memory_tier": "raw",
        }