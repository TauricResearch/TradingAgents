from datetime import datetime, timezone

import pytest

import orchestrator.orchestrator as orchestrator_module
from orchestrator.config import OrchestratorConfig
from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.contracts.result_contract import CombinedSignalFailure
from orchestrator.signals import Signal


def _signal(
    source: str,
    *,
    direction: int,
    confidence: float,
    metadata: dict | None = None,
    reason_code: str | None = None,
) -> Signal:
    return Signal(
        ticker="AAPL",
        direction=direction,
        confidence=confidence,
        source=source,
        timestamp=datetime.now(timezone.utc),
        metadata=metadata or {},
        reason_code=reason_code,
    )


def test_trading_orchestrator_degrades_to_llm_only_when_quant_has_error(monkeypatch):
    class FakeQuantRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal("quant", direction=1, confidence=0.8, metadata={"error": "db unavailable"})

    class FakeLLMRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal("llm", direction=-1, confidence=0.9)

    monkeypatch.setattr(orchestrator_module, "QuantRunner", FakeQuantRunner)
    monkeypatch.setattr(orchestrator_module, "LLMRunner", FakeLLMRunner)

    result = orchestrator_module.TradingOrchestrator(
        OrchestratorConfig(quant_backtest_path="/tmp/quant")
    ).get_combined_signal("AAPL", "2026-04-11")

    assert result.direction == -1
    assert result.quant_signal is None
    assert result.llm_signal is not None
    assert result.llm_signal.source == "llm"


def test_trading_orchestrator_degrades_to_quant_only_when_llm_has_error(monkeypatch):
    class FakeQuantRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal("quant", direction=1, confidence=0.8)

    class FakeLLMRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal("llm", direction=0, confidence=0.0, metadata={"error": "timeout"})

    monkeypatch.setattr(orchestrator_module, "QuantRunner", FakeQuantRunner)
    monkeypatch.setattr(orchestrator_module, "LLMRunner", FakeLLMRunner)

    result = orchestrator_module.TradingOrchestrator(
        OrchestratorConfig(quant_backtest_path="/tmp/quant")
    ).get_combined_signal("AAPL", "2026-04-11")

    assert result.direction == 1
    assert result.quant_signal is not None
    assert result.quant_signal.source == "quant"
    assert result.llm_signal is None


def test_trading_orchestrator_raises_when_both_sources_degrade(monkeypatch):
    class FakeQuantRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal(
                "quant",
                direction=0,
                confidence=0.0,
                metadata={"error": "no data"},
                reason_code=ReasonCode.QUANT_NO_DATA.value,
            )

    class FakeLLMRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal("llm", direction=0, confidence=0.0, metadata={"error": "timeout"})

    monkeypatch.setattr(orchestrator_module, "QuantRunner", FakeQuantRunner)
    monkeypatch.setattr(orchestrator_module, "LLMRunner", FakeLLMRunner)

    with pytest.raises(CombinedSignalFailure) as exc_info:
        orchestrator_module.TradingOrchestrator(
            OrchestratorConfig(quant_backtest_path="/tmp/quant")
        ).get_combined_signal("AAPL", "2026-04-11")

    assert str(exc_info.value) == "both quant and llm signals are None"
    assert exc_info.value.reason_codes[0] == ReasonCode.QUANT_NO_DATA.value
    assert exc_info.value.reason_codes[-1] == ReasonCode.BOTH_SIGNALS_UNAVAILABLE.value
    assert exc_info.value.source_diagnostics["quant"]["reason_code"] == ReasonCode.QUANT_NO_DATA.value


def test_trading_orchestrator_surfaces_provider_mismatch_summary_when_llm_degrades(monkeypatch):
    class FakeQuantRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal("quant", direction=1, confidence=0.8)

    class FakeLLMRunner:
        def __init__(self, _config):
            pass

        def get_signal(self, _ticker, _date):
            return _signal(
                "llm",
                direction=0,
                confidence=0.0,
                metadata={
                    "error": "provider mismatch",
                    "data_quality": {
                        "state": "provider_mismatch",
                        "provider": "anthropic",
                        "backend_url": "https://api.openai.com/v1",
                    },
                },
                reason_code=ReasonCode.PROVIDER_MISMATCH.value,
            )

    monkeypatch.setattr(orchestrator_module, "QuantRunner", FakeQuantRunner)
    monkeypatch.setattr(orchestrator_module, "LLMRunner", FakeLLMRunner)

    result = orchestrator_module.TradingOrchestrator(
        OrchestratorConfig(quant_backtest_path="/tmp/quant")
    ).get_combined_signal("AAPL", "2026-04-11")

    assert result.direction == 1
    assert result.quant_signal is not None
    assert result.llm_signal is None
    assert result.degrade_reason_codes == (ReasonCode.PROVIDER_MISMATCH.value,)
    assert result.metadata["data_quality"]["state"] == "provider_mismatch"
    assert result.metadata["data_quality"]["source"] == "llm"
    assert result.metadata["data_quality"]["issues"] == [
        {
            "source": "llm",
            "state": "provider_mismatch",
            "provider": "anthropic",
            "backend_url": "https://api.openai.com/v1",
        }
    ]
