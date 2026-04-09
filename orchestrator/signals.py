import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from orchestrator.config import OrchestratorConfig

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    ticker: str
    direction: int        # +1 买入, -1 卖出, 0 持有
    confidence: float     # 0.0 ~ 1.0
    source: str           # "quant" | "llm"
    timestamp: datetime
    metadata: dict = field(default_factory=dict)  # 原始输出，用于调试


@dataclass
class FinalSignal:
    ticker: str
    direction: int        # sign(quant_dir×quant_conf + llm_dir×llm_conf)，sign(0)→0(HOLD)
    confidence: float     # abs(weighted_sum) / total_conf
    quant_signal: Optional[Signal]
    llm_signal: Optional[Signal]
    timestamp: datetime


def _sign(x: float) -> int:
    """Return +1, -1, or 0."""
    if x > 0:
        return 1
    elif x < 0:
        return -1
    return 0


class SignalMerger:
    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config

    def merge(self, quant: Optional[Signal], llm: Optional[Signal]) -> FinalSignal:
        now = datetime.now(timezone.utc)

        # 两者均失败
        if quant is None and llm is None:
            raise ValueError("both quant and llm signals are None")

        ticker = (quant or llm).ticker  # type: ignore[union-attr]

        # 只有 LLM（quant 失败）
        if quant is None:
            return FinalSignal(
                ticker=ticker,
                direction=llm.direction,
                confidence=min(llm.confidence * self._config.llm_solo_penalty,
                               self._config.llm_weight_cap),
                quant_signal=None,
                llm_signal=llm,
                timestamp=now,
            )

        # 只有 Quant（llm 失败）
        if llm is None:
            return FinalSignal(
                ticker=ticker,
                direction=quant.direction,
                confidence=min(quant.confidence * self._config.quant_solo_penalty,
                               self._config.quant_weight_cap),
                quant_signal=quant,
                llm_signal=None,
                timestamp=now,
            )

        # 两者都有：加权合并
        weighted_sum = (
            quant.direction * quant.confidence
            + llm.direction * llm.confidence
        )
        final_direction = _sign(weighted_sum)
        if final_direction == 0:
            logger.info(
                "SignalMerger: weighted_sum=0 for %s — signals cancel out, HOLD",
                ticker,
            )
        total_conf = quant.confidence + llm.confidence
        raw_confidence = abs(weighted_sum) / total_conf if total_conf > 0 else 0.0
        final_confidence = min(raw_confidence, self._config.quant_weight_cap,
                               self._config.llm_weight_cap)

        return FinalSignal(
            ticker=ticker,
            direction=final_direction,
            confidence=final_confidence,
            quant_signal=quant,
            llm_signal=llm,
            timestamp=now,
        )
