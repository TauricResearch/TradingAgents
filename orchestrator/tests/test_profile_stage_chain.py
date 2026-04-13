import json
from datetime import datetime as real_datetime, timezone
from pathlib import Path

import pytest

import orchestrator.profile_stage_chain as profile_stage_chain


class _FakeGraphStream:
    def __init__(self, events):
        self._events = events

    def stream(self, state, stream_mode, config):
        assert state["company_of_interest"] == "AAPL"
        assert state["trade_date"] == "2026-04-11"
        assert stream_mode == "updates"
        assert config == {"recursion_limit": 100, "max_concurrency": 1}
        for event in self._events:
            yield event


class _FakeTradingAgentsGraph:
    def __init__(self, *, selected_analysts, config):
        assert selected_analysts == ["market", "social"]
        assert config["selected_analysts"] == ["market", "social"]
        assert config["analysis_prompt_style"] == "balanced"
        self.graph = _FakeGraphStream(
            [
                {
                    "Bull Researcher": {
                        "investment_debate_state": {
                            "research_status": "degraded",
                            "degraded_reason": "bull_researcher_timeout",
                            "history": "Bull Analyst: case",
                            "current_response": "Bull Analyst: case",
                        }
                    }
                },
                {
                    "Research Manager": {
                        "investment_debate_state": {
                            "research_status": "degraded",
                            "degraded_reason": "research_manager_timeout",
                            "history": "Bull Analyst: case\nRecommendation: HOLD",
                            "current_response": "Recommendation: HOLD",
                        }
                    }
                },
            ]
        )


class _FakePropagator:
    def create_initial_state(self, ticker, date):
        return {
            "company_of_interest": ticker,
            "trade_date": date,
            "investment_debate_state": {},
        }


class _FixedDateTime:
    @staticmethod
    def now(tz=None):
        return real_datetime(2026, 4, 14, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({}, (None, None, 0, 0)),
        (
            {
                "Bull Researcher": {
                    "investment_debate_state": {
                        "research_status": "degraded",
                        "degraded_reason": "bull_researcher_timeout",
                        "history": "abc",
                        "current_response": "xy",
                    }
                }
            },
            ("degraded", "bull_researcher_timeout", 3, 2),
        ),
    ],
)
def test_extract_research_state_captures_trace_fields(event, expected):
    assert profile_stage_chain._extract_research_state(event) == expected


def test_main_writes_trace_payload_with_research_provenance(monkeypatch, tmp_path, capsys):
    monotonic_points = iter([100.0, 100.4, 101.0])

    monkeypatch.setattr(profile_stage_chain, "TradingAgentsGraph", _FakeTradingAgentsGraph)
    monkeypatch.setattr(profile_stage_chain, "Propagator", _FakePropagator)
    monkeypatch.setattr(profile_stage_chain.time, "monotonic", lambda: next(monotonic_points))
    monkeypatch.setattr(profile_stage_chain.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(profile_stage_chain.signal, "alarm", lambda *args, **kwargs: None)
    monkeypatch.setattr(profile_stage_chain, "datetime", _FixedDateTime)
    monkeypatch.setattr(
        "sys.argv",
        [
            "profile_stage_chain.py",
            "--ticker",
            "AAPL",
            "--date",
            "2026-04-11",
            "--selected-analysts",
            "market,social",
            "--analysis-prompt-style",
            "balanced",
            "--dump-dir",
            str(tmp_path),
        ],
    )

    profile_stage_chain.main()

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ok"
    assert output["ticker"] == "AAPL"
    assert output["date"] == "2026-04-11"
    assert output["selected_analysts"] == ["market", "social"]
    assert output["analysis_prompt_style"] == "balanced"
    assert output["phase_totals_seconds"] == {"research": 1.0}
    assert output["raw_events"] == []
    assert output["node_timings"] == [
        {
            "run_id": "20260414T000000Z",
            "nodes": ["Bull Researcher"],
            "phases": ["research"],
            "llm_kinds": ["quick"],
            "start_at": 0.0,
            "end_at": 0.4,
            "elapsed_ms": 400,
            "selected_analysts": ["market", "social"],
            "analysis_prompt_style": "balanced",
            "research_status": "degraded",
            "degraded_reason": "bull_researcher_timeout",
            "history_len": len("Bull Analyst: case"),
            "response_len": len("Bull Analyst: case"),
        },
        {
            "run_id": "20260414T000000Z",
            "nodes": ["Research Manager"],
            "phases": ["research"],
            "llm_kinds": ["deep"],
            "start_at": 0.4,
            "end_at": 1.0,
            "elapsed_ms": 600,
            "selected_analysts": ["market", "social"],
            "analysis_prompt_style": "balanced",
            "research_status": "degraded",
            "degraded_reason": "research_manager_timeout",
            "history_len": len("Bull Analyst: case\nRecommendation: HOLD"),
            "response_len": len("Recommendation: HOLD"),
        },
    ]

    dump_path = Path(output["dump_path"])
    assert dump_path.exists()
    assert json.loads(dump_path.read_text()) == output
