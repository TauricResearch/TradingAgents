import logging
from datetime import datetime, timezone
from typing import Optional

from orchestrator.config import OrchestratorConfig
from orchestrator.signals import Signal, FinalSignal, SignalMerger
from orchestrator.quant_runner import QuantRunner
from orchestrator.llm_runner import LLMRunner

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    def __init__(self, config: OrchestratorConfig):
        self._config = config
        self._merger = SignalMerger(config)
        self._quant: Optional[QuantRunner] = None
        self._llm: Optional[LLMRunner] = None

        # Initialize runners (quant requires quant_backtest_path)
        if config.quant_backtest_path:
            try:
                self._quant = QuantRunner(config)
            except Exception as e:
                logger.warning("TradingOrchestrator: QuantRunner init failed: %s", e)

        self._llm = LLMRunner(config)

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

        # Get quant signal
        if self._quant is not None:
            try:
                quant_sig = self._quant.get_signal(ticker, date)
                # Treat error signals (confidence=0, direction=0 with error metadata) as None
                if quant_sig.metadata.get("error") or quant_sig.metadata.get("reason") == "no_data":
                    logger.warning("TradingOrchestrator: quant signal degraded for %s %s", ticker, date)
                    quant_sig = None
            except Exception as e:
                logger.error("TradingOrchestrator: quant get_signal failed: %s", e)
                quant_sig = None

        # Get llm signal
        try:
            llm_sig = self._llm.get_signal(ticker, date)
            if llm_sig.metadata.get("error"):
                logger.warning("TradingOrchestrator: llm signal degraded for %s %s", ticker, date)
                llm_sig = None
        except Exception as e:
            logger.error("TradingOrchestrator: llm get_signal failed: %s", e)
            llm_sig = None

        # merge raises ValueError if both None
        return self._merger.merge(quant_sig, llm_sig)
