from dataclasses import dataclass


@dataclass
class Call:
    config: dict
    selected_analysts: list[str]


def test_run_default_analysis_uses_one_balanced_graph(monkeypatch):
    from tradingagents.secretary import analysis_runner

    calls = []

    class FakeGraph:
        def __init__(self, config, selected_analysts):
            calls.append(Call(config=config, selected_analysts=selected_analysts))
            self.run_id = "run-balanced"

        def propagate(self, ticker, trade_date):
            assert ticker == "NVDA"
            assert trade_date == "2026-06-01"

    monkeypatch.setattr(analysis_runner, "TradingAgentsGraph", FakeGraph)

    run_ids = analysis_runner.run_default_analysis(
        ticker="NVDA",
        trade_date="2026-06-01",
        config={"default_analysis_persona_id": "balanced"},
        event_context="event text",
        queue_job_id=7,
    )

    assert run_ids == ["run-balanced"]
    assert len(calls) == 1
    assert calls[0].config["persona_id"] == "balanced"
    assert calls[0].config["event_context"] == "event text"
    assert calls[0].config["queue_job_id"] == 7
    assert calls[0].selected_analysts == [
        "market", "news", "fundamentals", "derivatives", "social",
    ]


def test_run_committee_analysis_keeps_explicit_multi_persona_mode(monkeypatch):
    from tradingagents.secretary import analysis_runner

    calls = []

    class FakeGraph:
        def __init__(self, config, selected_analysts):
            calls.append(config["persona_id"])
            self.run_id = f"run-{config['persona_id']}"

        def propagate(self, ticker, trade_date):
            pass

    monkeypatch.setattr(analysis_runner, "TradingAgentsGraph", FakeGraph)

    run_ids = analysis_runner.run_committee_analysis(
        persona_ids=["value", "momentum"],
        ticker="AAPL",
        trade_date="2026-06-01",
        config={},
        parallel=False,
    )

    assert run_ids == ["run-value", "run-momentum"]
    assert calls == ["value", "momentum"]
