import importlib
import sys
import threading
import time
import types

import pytest


@pytest.fixture()
def cli_main_module(monkeypatch):
    questionary_mod = types.ModuleType("questionary")
    questionary_mod.Choice = lambda *args, **kwargs: None
    questionary_mod.Style = lambda *args, **kwargs: None
    questionary_mod.select = lambda *args, **kwargs: None
    questionary_mod.text = lambda *args, **kwargs: None
    questionary_mod.checkbox = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "questionary", questionary_mod)

    stats_handler_mod = types.ModuleType("cli.stats_handler")

    class DummyStatsCallbackHandler:
        pass

    stats_handler_mod.StatsCallbackHandler = DummyStatsCallbackHandler
    monkeypatch.setitem(sys.modules, "cli.stats_handler", stats_handler_mod)

    fake_graph_module = types.ModuleType("tradingagents.graph.trading_graph")

    class PlaceholderGraph:
        def __init__(self, *args, **kwargs):
            pass

        def propagate(self, ticker, date):
            return {}, "HOLD"

    fake_graph_module.TradingAgentsGraph = PlaceholderGraph
    monkeypatch.setitem(sys.modules, "tradingagents.graph.trading_graph", fake_graph_module)

    module = importlib.import_module("cli.main")
    return importlib.reload(module)


@pytest.mark.unit
def test_portfolio_uses_bounded_concurrency(cli_main_module, monkeypatch):
    started = []
    lock = threading.Lock()
    active = 0
    max_seen = 0

    def fake_process_portfolio_ticker(
        ticker,
        date,
        selected_analysts,
        provider,
        checkpoint,
        standalone,
        run_id,
    ):
        nonlocal active, max_seen
        with lock:
            started.append((ticker, run_id))
            active += 1
            max_seen = max(max_seen, active)
        time.sleep(0.15)
        with lock:
            active -= 1
        return {"ticker": ticker, "decision": "BUY", "final_state": {}}

    monkeypatch.setattr(cli_main_module, "_process_portfolio_ticker", fake_process_portfolio_ticker)
    monkeypatch.setattr(cli_main_module.console, "print", lambda *args, **kwargs: None)

    cli_main_module.portfolio(
        tickers="AAPL,MSFT,NVDA",
        date="2026-05-15",
        provider=None,
        checkpoint=False,
        max_concurrency=3,
        analysts=None,
        standalone=False,
        run_id="run-123",
    )

    assert sorted(ticker for ticker, _ in started) == ["AAPL", "MSFT", "NVDA"]
    assert all(run_id == "run-123" for _, run_id in started)
    assert max_seen >= 2
