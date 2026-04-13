import logging
from typing import Optional

from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.contracts.result_contract import CombinedSignalFailure, FinalSignal, Signal, signal_reason_code
from orchestrator.signals import SignalMerger
from orchestrator.quant_runner import QuantRunner
from orchestrator.llm_runner import LLMRunner

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    def __init__(self, config: OrchestratorConfig):
        self._config = config
        self._merger = SignalMerger(config)
        self._quant: Optional[QuantRunner] = None
        self._llm: Optional[LLMRunner] = None
        self._quant_unavailable_reason: Optional[str] = None
        self._llm_unavailable_reason: Optional[str] = None

        # Initialize runners (quant requires quant_backtest_path)
        if config.quant_backtest_path:
            try:
                self._quant = QuantRunner(config)
            except Exception as e:
                logger.warning("TradingOrchestrator: QuantRunner init failed: %s", e)
                self._quant_unavailable_reason = ReasonCode.QUANT_INIT_FAILED.value
        else:
            self._quant_unavailable_reason = ReasonCode.QUANT_NOT_CONFIGURED.value

        try:
            self._llm = LLMRunner(config)
        except Exception as e:
            logger.warning("TradingOrchestrator: LLMRunner init failed: %s", e)
            self._llm_unavailable_reason = ReasonCode.LLM_INIT_FAILED.value

    def get_combined_signal(self, ticker: str, date: str) -> FinalSignal:
        """
        Get merged signal for ticker on date.
        Degradation:
          - quant fails (error signal): use llm only with llm_solo_penalty
          - llm fails (error signal): use quant only with quant_solo_penalty
          - both fail: raises ValueError
        """
        quant_sig: Optional[Signal] = None
        llm_sig: Optional[Signal] = None
        degradation_reasons: list[str] = []
        source_diagnostics: dict[str, dict] = {}

        if self._quant is None and self._quant_unavailable_reason:
            degradation_reasons.append(self._quant_unavailable_reason)
            source_diagnostics["quant"] = {"reason_code": self._quant_unavailable_reason}
        if self._llm is None and self._llm_unavailable_reason:
            degradation_reasons.append(self._llm_unavailable_reason)
            source_diagnostics["llm"] = {"reason_code": self._llm_unavailable_reason}

        # Get quant signal
        if self._quant is not None:
            try:
                quant_sig = self._quant.get_signal(ticker, date)
                if quant_sig.degraded:
                    reason_code = signal_reason_code(quant_sig) or ReasonCode.QUANT_SIGNAL_FAILED.value
                    degradation_reasons.append(
                        reason_code
                    )
                    source_diagnostics["quant"] = self._build_source_diagnostic(quant_sig, reason_code)
                    logger.warning("TradingOrchestrator: quant signal degraded for %s %s", ticker, date)
                    quant_sig = None
            except Exception as e:
                logger.error("TradingOrchestrator: quant get_signal failed: %s", e)
                degradation_reasons.append(ReasonCode.QUANT_SIGNAL_FAILED.value)
                source_diagnostics["quant"] = {"reason_code": ReasonCode.QUANT_SIGNAL_FAILED.value}
                quant_sig = None

        # Get llm signal
        if self._llm is not None:
            try:
                llm_sig = self._llm.get_signal(ticker, date)
                if llm_sig.degraded:
                    reason_code = signal_reason_code(llm_sig) or ReasonCode.LLM_SIGNAL_FAILED.value
                    degradation_reasons.append(
                        reason_code
                    )
                    source_diagnostics["llm"] = self._build_source_diagnostic(llm_sig, reason_code)
                    logger.warning("TradingOrchestrator: llm signal degraded for %s %s", ticker, date)
                    llm_sig = None
            except Exception as e:
                logger.error("TradingOrchestrator: llm get_signal failed: %s", e)
                degradation_reasons.append(ReasonCode.LLM_SIGNAL_FAILED.value)
                source_diagnostics["llm"] = {"reason_code": ReasonCode.LLM_SIGNAL_FAILED.value}
                llm_sig = None

        # Preserve diagnostics even when both lanes degrade and no FinalSignal can be produced.
        if quant_sig is None and llm_sig is None:
            degradation_reasons.append(ReasonCode.BOTH_SIGNALS_UNAVAILABLE.value)
            raise CombinedSignalFailure(
                "both quant and llm signals are None",
                reason_codes=tuple(dict.fromkeys(degradation_reasons)),
                source_diagnostics=source_diagnostics,
                data_quality=self._summarize_data_quality(source_diagnostics),
            )

        final_signal = self._merger.merge(
            quant_sig,
            llm_sig,
            degradation_reasons=degradation_reasons,
        )
        data_quality = self._summarize_data_quality(source_diagnostics)
        metadata = dict(final_signal.metadata)
        if source_diagnostics:
            metadata["source_diagnostics"] = source_diagnostics
        if data_quality:
            metadata["data_quality"] = data_quality
        final_signal.metadata = metadata
        return final_signal

    @staticmethod
    def _build_source_diagnostic(signal: Signal, reason_code: str) -> dict:
        diagnostic = {"reason_code": reason_code}
        data_quality = signal.metadata.get("data_quality")
        if data_quality is not None:
            diagnostic["data_quality"] = data_quality
        error = signal.metadata.get("error")
        if error:
            diagnostic["error"] = error
        return diagnostic

    @staticmethod
    def _summarize_data_quality(source_diagnostics: dict[str, dict]) -> Optional[dict]:
        states: list[tuple[str, dict]] = []
        for source, diagnostic in source_diagnostics.items():
            data_quality = diagnostic.get("data_quality")
            if isinstance(data_quality, dict) and data_quality.get("state"):
                states.append((source, data_quality))

        if not states:
            return None

        priority = {
            "provider_mismatch": 0,
            "non_trading_day": 1,
            "stale_data": 2,
            "partial_data": 3,
        }
        source, selected = sorted(
            states,
            key=lambda item: priority.get(item[1].get("state"), 999),
        )[0]
        summary = dict(selected)
        summary["source"] = source
        summary["issues"] = [
            {"source": issue_source, **issue_quality}
            for issue_source, issue_quality in states
        ]
        return summary
