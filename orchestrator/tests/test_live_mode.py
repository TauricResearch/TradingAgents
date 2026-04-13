import asyncio
from datetime import datetime, timezone

from orchestrator.contracts.error_taxonomy import ReasonCode
from orchestrator.contracts.result_contract import CombinedSignalFailure, FinalSignal, Signal
from orchestrator.live_mode import LiveMode


def _signal(*, source: str, direction: int, confidence: float) -> Signal:
    return Signal(
        ticker="AAPL",
        direction=direction,
        confidence=confidence,
        source=source,
        timestamp=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
    )


class _StubOrchestrator:
    def __init__(self, responses):
        self._responses = responses

    def get_combined_signal(self, ticker: str, date: str):
        response = self._responses[(ticker, date)]
        if isinstance(response, Exception):
            raise response
        return response


def test_live_mode_serializes_degraded_contract_shape():
    live_mode = LiveMode(
        _StubOrchestrator(
            {
                ("AAPL", "2026-04-11"): FinalSignal(
                    ticker="AAPL",
                    direction=-1,
                    confidence=0.42,
                    quant_signal=None,
                    llm_signal=_signal(source="llm", direction=-1, confidence=0.6),
                    timestamp=datetime(2026, 4, 11, 12, 1, tzinfo=timezone.utc),
                    degrade_reason_codes=(ReasonCode.QUANT_SIGNAL_FAILED.value,),
                    metadata={
                        "contract_version": "v1alpha1",
                        "data_quality": {"state": "stale_data", "source": "quant"},
                        "research": {
                            "research_status": "degraded",
                            "research_mode": "degraded_synthesis",
                            "timed_out_nodes": ["Bull Researcher"],
                            "degraded_reason": "bull_researcher_timeout",
                            "covered_dimensions": ["market"],
                            "manager_confidence": None,
                        },
                        "source_diagnostics": {
                            "quant": {"reason_code": ReasonCode.STALE_DATA.value}
                        },
                    },
                )
            }
        )
    )

    results = asyncio.run(live_mode.run_once(["AAPL"], "2026-04-11"))

    assert results == [
        {
            "contract_version": "v1alpha1",
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "degraded_success",
            "result": {
                "direction": -1,
                "confidence": 0.42,
                "quant_direction": None,
                "llm_direction": -1,
                "timestamp": "2026-04-11T12:01:00+00:00",
            },
            "error": None,
            "degradation": {
                "degraded": True,
                "reason_codes": [ReasonCode.QUANT_SIGNAL_FAILED.value],
                "source_diagnostics": {
                    "quant": {"reason_code": ReasonCode.STALE_DATA.value}
                },
            },
            "data_quality": {"state": "stale_data", "source": "quant"},
            "research": {
                "research_status": "degraded",
                "research_mode": "degraded_synthesis",
                "timed_out_nodes": ["Bull Researcher"],
                "degraded_reason": "bull_researcher_timeout",
                "covered_dimensions": ["market"],
                "manager_confidence": None,
            },
        }
    ]


def test_live_mode_serializes_failure_contract_shape():
    live_mode = LiveMode(
        _StubOrchestrator(
            {
                ("AAPL", "2026-04-11"): CombinedSignalFailure(
                    "both quant and llm signals are None",
                    reason_codes=(ReasonCode.BOTH_SIGNALS_UNAVAILABLE.value, ReasonCode.PROVIDER_MISMATCH.value),
                    source_diagnostics={
                        "llm": {
                            "reason_code": ReasonCode.PROVIDER_MISMATCH.value,
                            "research": {
                                "research_status": "failed",
                                "research_mode": "degraded_synthesis",
                                "timed_out_nodes": ["Bull Researcher"],
                                "degraded_reason": "bull_researcher_connectionerror",
                                "covered_dimensions": ["market"],
                                "manager_confidence": None,
                            },
                        }
                    },
                    data_quality={"state": "provider_mismatch", "source": "llm"},
                )
            }
        )
    )

    results = asyncio.run(live_mode.run_once(["AAPL"], "2026-04-11"))

    assert results == [
        {
            "contract_version": "v1alpha1",
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "failed",
            "result": None,
            "error": {
                "code": "live_signal_failed",
                "message": "both quant and llm signals are None",
                "retryable": False,
            },
            "degradation": {
                "degraded": True,
                "reason_codes": [
                    ReasonCode.BOTH_SIGNALS_UNAVAILABLE.value,
                    ReasonCode.PROVIDER_MISMATCH.value,
                ],
                "source_diagnostics": {
                    "llm": {
                        "reason_code": ReasonCode.PROVIDER_MISMATCH.value,
                        "research": {
                            "research_status": "failed",
                            "research_mode": "degraded_synthesis",
                            "timed_out_nodes": ["Bull Researcher"],
                            "degraded_reason": "bull_researcher_connectionerror",
                            "covered_dimensions": ["market"],
                            "manager_confidence": None,
                        },
                    },
                },
            },
            "data_quality": {"state": "provider_mismatch", "source": "llm"},
            "research": {
                "research_status": "failed",
                "research_mode": "degraded_synthesis",
                "timed_out_nodes": ["Bull Researcher"],
                "degraded_reason": "bull_researcher_connectionerror",
                "covered_dimensions": ["market"],
                "manager_confidence": None,
            },
        }
    ]
