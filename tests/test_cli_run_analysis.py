from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class _DummyLive:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.integration
def test_run_analysis_routes_through_propagate(monkeypatch, tmp_path):
    import cli.main as m

    fake_graph = MagicMock()
    fake_graph.graph.stream = MagicMock()
    fake_graph.propagate.return_value = (
        {
            "market_report": "market done",
            "investment_plan": "research done",
            "trader_investment_plan": "trader done",
            "final_trade_decision": "BUY",
        },
        "BUY",
    )

    monkeypatch.setattr(m, "TradingAgentsGraph", lambda *a, **k: fake_graph)
    monkeypatch.setattr(m, "Live", _DummyLive)
    monkeypatch.setattr(m, "create_layout", lambda: object())
    monkeypatch.setattr(m, "update_display", lambda *a, **k: None)
    monkeypatch.setattr(m.typer, "prompt", lambda *a, **k: "N")
    monkeypatch.setitem(m.DEFAULT_CONFIG, "results_dir", str(tmp_path / "results"))
    monkeypatch.setitem(m.DEFAULT_CONFIG, "data_cache_dir", str(tmp_path / "cache"))

    monkeypatch.setattr(
        m,
        "get_user_selections",
        lambda: {
            "ticker": "AAPL",
            "asset_type": "stock",
            "analysis_date": "2024-01-02",
            "analysts": [m.AnalystType.MARKET],
            "research_depth": 1,
            "llm_provider": "openai",
            "backend_url": "",
            "shallow_thinker": "gpt-5.4-mini",
            "deep_thinker": "gpt-5.5",
            "google_thinking_level": None,
            "openai_reasoning_effort": None,
            "anthropic_effort": None,
            "output_language": "English",
        },
    )

    m.run_analysis(checkpoint=True)

    fake_graph.propagate.assert_called_once()
    _, kwargs = fake_graph.propagate.call_args
    assert kwargs["asset_type"] == "stock"
    assert callable(kwargs["on_chunk"])
    assert fake_graph.graph.stream.called is False
