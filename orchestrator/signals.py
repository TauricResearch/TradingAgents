import logging
from datetime import datetime, timezone
from typing import Optional

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.result_contract import FinalSignal, Signal

logger = logging.getLogger(__name__)


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

    def merge(
        self,
        quant: Optional[Signal],
        llm: Optional[Signal],
        degradation_reasons: Optional[list[str]] = None,
    ) -> FinalSignal:
        now = datetime.now(timezone.utc)
        reasons = tuple(dict.fromkeys(code for code in (degradation_reasons or []) if code))

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
                degrade_reason_codes=reasons,
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
                degrade_reason_codes=reasons,
            )

        # 两者都有：加权合并
        # Cap each signal's contribution before merging
        quant_conf = min(quant.confidence, self._config.quant_weight_cap)
        llm_conf = min(llm.confidence, self._config.llm_weight_cap)
        weighted_sum = (
            quant.direction * quant_conf
            + llm.direction * llm_conf
        )
        final_direction = _sign(weighted_sum)
        if final_direction == 0:
            logger.info(
                "SignalMerger: weighted_sum=0 for %s — signals cancel out, HOLD",
                ticker,
            )
        total_conf = quant_conf + llm_conf
        final_confidence = abs(weighted_sum) / total_conf if total_conf > 0 else 0.0

        return FinalSignal(
            ticker=ticker,
            direction=final_direction,
            confidence=final_confidence,
            quant_signal=quant,
            llm_signal=llm,
            timestamp=now,
            degrade_reason_codes=reasons,
        )
