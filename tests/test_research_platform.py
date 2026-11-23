"""The research platform: store, watchlist runner, scorecard and paper portfolio, all offline."""

from types import SimpleNamespace

import pandas as pd
import pytest

from research_platform import config as pconfig, paper, scorecard
from research_platform.store import Signal, SignalStore
from research_platform.watchlist import parse_watchlist, run_watchlist

pytestmark = pytest.mark.unit

IDX = pd.bdate_range("2026-01-05", periods=80)   # Mon 5 Jan 2026 onwards


def series(values):
    return pd.Series(values, index=IDX[: len(values)], dtype=float)


def lookup_from(data):
    def lookup(symbol, start, end):
        s = data[symbol]
        return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    return lookup


# ------------------------------------------------------------------ config


def test_platform_config_defaults_to_anthropic_when_no_provider_is_set(monkeypatch):
    for name in ("TRADINGAGENTS_LLM_PROVIDER", "TRADINGAGENTS_DEEP_THINK_LLM", "TRADINGAGENTS_QUICK_THINK_LLM"):
        monkeypatch.delenv(name, raising=False)
    cfg = pconfig.platform_config()
    assert (cfg["llm_provider"], cfg["deep_think_llm"], cfg["quick_think_llm"]) == (
        "anthropic", "claude-opus-5-5", "claude-sonnet-5-5")


def test_platform_config_leaves_a_chosen_provider_alone(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    cfg = pconfig.platform_config({"llm_provider": "openai", "deep_think_llm": "gpt-6-sol"})
    assert cfg["llm_provider"] == "openai" and cfg["deep_think_llm"] == "gpt-6-sol"


def test_key_status_reports_the_name_never_the_value(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert pconfig.provider_key_status({"llm_provider": "anthropic"}) == ("ANTHROPIC_API_KEY", True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    assert pconfig.provider_key_status({"llm_provider": "anthropic"}) == ("ANTHROPIC_API_KEY", False)


# ------------------------------------------------------------------ store


def test_store_round_trip_and_replace(tmp_path):
    store = SignalStore(tmp_path / "p.db")
    store.save(Signal("AAPL", "2026-01-05", rating="Buy", size_pct=0.1))
    store.save(Signal("AAPL", "2026-01-05", rating="Sell"))          # same cell replaces
    store.save(Signal("MSFT", "2026-01-02", status="failed", error="boom"))
    rows = store.all()
    assert [(s.ticker, s.rating) for s in rows] == [("MSFT", None), ("AAPL", "Sell")]
    assert [s.ticker for s in store.all(only_ok=True)] == ["AAPL"]
    assert store.get("AAPL", "2026-01-05").recorded_at


def test_a_review_rating_is_not_a_usable_signal():
    assert not Signal("X", "2026-01-05", rating="REVIEW").ok


# ------------------------------------------------------------------ watchlist


def test_parse_watchlist_normalises_dedupes_and_skips_comments():
    text = "aapl, msft\n# a comment\n2222.sr ; AAPL  # again\n"
    assert parse_watchlist(text) == ["AAPL", "MSFT", "2222.SR"]


def test_parse_watchlist_refuses_garbage():
    with pytest.raises(ValueError):
        parse_watchlist("AAPL, not a ticker!!")


def _metrics(price=100.0):
    return SimpleNamespace(price=price, stop_long=94.0, atr=2.0, volatility=0.25,
                           sizing=SimpleNamespace(size_pct=0.08))


def test_run_watchlist_records_runs_failures_and_sizing(tmp_path):
    store = SignalStore(tmp_path / "p.db")
    calls = []

    def runner(ticker, date, asset_type, analysts, cfg):
        calls.append(ticker)
        if ticker == "MSFT":
            raise RuntimeError("vendor down")
        return "Buy", "FINAL TRANSACTION PROPOSAL: **BUY**", None

    cfg = {"llm_provider": "anthropic", "deep_think_llm": "d", "quick_think_llm": "q"}
    result = run_watchlist(["AAPL", "MSFT"], "2026-01-05", cfg, ("market",), store=store,
                           runner=runner, metrics=lambda *a: _metrics())
    assert result.ran == ["AAPL"] and result.failed[0][0] == "MSFT"
    aapl = store.get("AAPL", "2026-01-05")
    assert (aapl.rating, aapl.size_pct, aapl.stop_long, aapl.quick_model) == ("Buy", 0.08, 94.0, "q")
    assert store.get("MSFT", "2026-01-05").error == "RuntimeError: vendor down"

    # A second sweep skips the done ticker and retries the failed one.
    again = run_watchlist(["AAPL", "MSFT"], "2026-01-05", cfg, ("market",), store=store,
                          runner=runner, metrics=lambda *a: _metrics())
    assert again.skipped == ["AAPL"] and calls == ["AAPL", "MSFT", "MSFT"]


def test_missing_risk_metrics_leave_the_size_empty_not_guessed(tmp_path):
    store = SignalStore(tmp_path / "p.db")

    def no_prices(*_):
        raise ValueError("no daily prices")

    run_watchlist(["AAPL"], "2026-01-05", {}, ("market",), store=store,
                  runner=lambda *a: ("Hold", "hold", None), metrics=no_prices)
    s = store.get("AAPL", "2026-01-05")
    assert s.ok and s.size_pct is None and "risk metrics unavailable" in s.error


# ------------------------------------------------------------------ scorecard


def test_outcome_enters_on_the_first_close_after_the_analysis_date():
    closes = series([100, 110, 121, 133.1])
    bench = series([50, 50, 55, 55])
    o = scorecard.outcome(Signal("A", "2026-01-05", rating="Buy"), 2, closes, bench, "SPY")
    # Entry is 6 Jan at 110 (not 5 Jan, the analysis date); exit two trading days later at 133.1.
    assert (o.entry_date, o.exit_date) == ("2026-01-06", "2026-01-08")
    assert o.ret == pytest.approx(0.21) and o.benchmark_ret == pytest.approx(0.10)
    assert o.alpha == pytest.approx(0.11) and o.hit is True


def test_an_unfinished_horizon_is_pending():
    o = scorecard.outcome(Signal("A", "2026-01-05", rating="Sell"), 5, series([100, 101, 102]), None, None)
    # Entry is the 6 Jan close; only 7 Jan has traded since, so 1 of the 5 days.
    assert not o.settled and o.ret is None and "1 of 5" in o.note


def test_hold_has_no_hit_and_sell_hits_on_negative_alpha():
    hold = scorecard.Outcome("A", "d", "Hold", 5, ret=0.05, benchmark_ret=0.0)
    sell = scorecard.Outcome("A", "d", "Sell", 5, ret=-0.02, benchmark_ret=0.01)
    assert hold.hit is None and sell.hit is True


def test_score_aggregates_by_rating_and_reports_the_spread():
    data = {"UP": series([100 + 2 * i for i in range(30)]), "DOWN": series([100 - i for i in range(30)]),
            "SPY": series([100] * 30)}
    signals = [Signal("UP", "2026-01-05", rating="Buy"), Signal("DOWN", "2026-01-05", rating="Sell"),
               Signal("UP", "2026-01-05", status="failed")]
    card = scorecard.score(signals, lookup_from(data), horizons=(5,), benchmark_of=lambda t: "SPY",
                           end="2026-02-27")
    buy = next(b for b in card.buckets if b.rating == "Buy")
    sell = next(b for b in card.buckets if b.rating == "Sell")
    assert buy.mean_return == pytest.approx(112 / 102 - 1) and buy.hit_rate == 1.0
    assert sell.mean_return == pytest.approx(94 / 99 - 1) and sell.hit_rate == 1.0
    assert card.spread[5] == pytest.approx(buy.mean_alpha - sell.mean_alpha)
    assert len(card.outcomes) == 2          # the failed run is not scored


# ------------------------------------------------------------------ paper portfolio


NO_COSTS = {"commission_bps": 0.0, "slippage_bps": 0.0}


def test_a_buy_fills_at_the_next_close_at_its_risk_size():
    data = {"A": series([100, 110, 121]), "SPY": series([10, 10, 10])}
    r = paper.simulate([Signal("A", "2026-01-05", rating="Buy", size_pct=0.2)], lookup_from(data),
                       NO_COSTS, end="2026-01-07")
    t = r.trades[0]
    assert (t.date, t.price, t.value) == ("2026-01-06", 110.0, 20_000.0)
    # 20,000 at 110 grows 10% to 22,000 by the last close; cash stays 80,000.
    assert r.equity.iloc[-1] == pytest.approx(102_000.0)
    assert r.stats["total_return"] == pytest.approx(0.02)
    assert r.stats["benchmark_return"] == pytest.approx(0.0)


def test_costs_are_charged_in_basis_points_of_traded_value():
    data = {"A": series([100, 100])}
    r = paper.simulate([Signal("A", "2026-01-05", rating="Buy", size_pct=0.5)], lookup_from(data),
                       {"commission_bps": 5.0, "slippage_bps": 5.0}, end="2026-01-06", benchmark=None)
    assert r.trades[0].cost == pytest.approx(50_000 * 0.001)
    assert r.equity.iloc[-1] == pytest.approx(100_000 - 50.0)


def test_overweight_underweight_sell_and_hold_rules():
    data = {"A": series([100] * 10)}
    sigs = [Signal("A", "2026-01-05", rating="Overweight", size_pct=0.2),   # -> 10%
            Signal("A", "2026-01-07", rating="Hold", size_pct=0.2),         # no trade
            Signal("A", "2026-01-08", rating="Underweight"),                # -> 5%
            Signal("A", "2026-01-12", rating="Sell")]                        # -> 0
    r = paper.simulate(sigs, lookup_from(data), NO_COSTS, end="2026-01-16", benchmark=None)
    assert [(t.reason, t.action, round(t.value)) for t in r.trades] == [
        ("Overweight", "buy", 10_000), ("Underweight", "sell", 5_000), ("Sell", "sell", 5_000)]
    assert r.positions == {}


def test_a_buy_without_a_recorded_size_uses_the_fallback_and_says_so():
    data = {"A": series([100, 100])}
    r = paper.simulate([Signal("A", "2026-01-05", rating="Buy")], lookup_from(data), NO_COSTS,
                       end="2026-01-06", benchmark=None)
    assert r.trades[0].value == pytest.approx(5_000) and "fallback" in r.trades[0].note


def test_the_stop_sells_at_the_first_close_below_it():
    data = {"A": series([100, 100, 97, 93, 90])}
    r = paper.simulate([Signal("A", "2026-01-05", rating="Buy", size_pct=0.5, stop_long=95)],
                       lookup_from(data), NO_COSTS, end="2026-01-09", benchmark=None)
    stop = r.trades[-1]
    assert (stop.reason, stop.date, stop.price) == ("stop", "2026-01-08", 93.0)
    assert r.equity.iloc[-1] == pytest.approx(50_000 + 50_000 * 0.93)
    off = paper.simulate([Signal("A", "2026-01-05", rating="Buy", size_pct=0.5, stop_long=95)],
                         lookup_from(data), {**NO_COSTS, "use_stops": False}, end="2026-01-09", benchmark=None)
    assert all(t.reason != "stop" for t in off.trades)


def test_buys_never_spend_more_than_the_free_cash():
    data = {"A": series([100, 100]), "B": series([50, 50])}
    sigs = [Signal("A", "2026-01-05", rating="Buy", size_pct=0.8),
            Signal("B", "2026-01-05", rating="Buy", size_pct=0.8)]
    r = paper.simulate(sigs, lookup_from(data), NO_COSTS, end="2026-01-06", benchmark=None)
    assert r.trades[1].value == pytest.approx(20_000) and "free cash" in r.trades[1].note
    assert r.cash.iloc[-1] == pytest.approx(0.0)


def test_a_signal_with_no_later_close_is_not_acted_on():
    data = {"A": series([100, 100, 100])}
    r = paper.simulate([Signal("A", "2026-01-07", rating="Buy", size_pct=0.1)], lookup_from(data),
                       NO_COSTS, end="2026-01-07", benchmark=None)
    assert not r.trades and not r.stats


def test_mixed_markets_are_flagged():
    data = {"A": series([100, 100]), "2222.SR": series([25, 25])}
    sigs = [Signal("A", "2026-01-05", rating="Buy", size_pct=0.1),
            Signal("2222.SR", "2026-01-05", rating="Buy", size_pct=0.1)]
    r = paper.simulate(sigs, lookup_from(data), NO_COSTS, end="2026-01-06", benchmark=None)
    assert any("without currency conversion" in n for n in r.notes)


# ------------------------------------------------------------------ dashboard


def test_dashboard_pages_render_without_errors(tmp_path, monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    import _socket
    import socket

    from tradingagents.default_config import DEFAULT_CONFIG

    # Streamlit's event loop needs a loopback socket pair on Windows; everything else stays refused.
    real_connect = _socket.socket.connect

    def loopback_only(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return real_connect(sock, address)
        raise OSError(f"test tried to reach the network: {address}")

    monkeypatch.setattr(socket.socket, "connect", loopback_only)

    monkeypatch.setitem(DEFAULT_CONFIG, "results_dir", str(tmp_path))
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pathlib import Path

    import research_platform

    script = Path(research_platform.__file__).with_name("dashboard.py")
    pages = ("Run analyses", "Signals and reports", "Scorecard", "Paper portfolio")
    app = testing.AppTest.from_file(str(script), default_timeout=30).run()
    assert not app.exception
    for page in pages:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page

    # With recorded signals and no reachable prices, every page still renders and says why.
    store = SignalStore(tmp_path / "platform" / "platform.db")
    store.save(Signal("AAPL", "2026-01-05", rating="Buy", size_pct=0.1, decision="buy"))
    store.save(Signal("MSFT", "2026-01-05", status="failed", error="RuntimeError: down"))
    app = testing.AppTest.from_file(str(script), default_timeout=30).run()
    assert not app.exception
    for page in pages:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
    assert any("prices unavailable" in w.value for w in app.warning)
