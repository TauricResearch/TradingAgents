"""Portfolio review: metrics for the whole book, and a reviewer that reads them.

A single run sees one ticker. The review computes what only the combination
shows, keeps a holding it cannot price visible rather than dropping it, and
hands the reviewer both the metrics and each holding's decision.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from tradingagents.agents.schemas import (
    PortfolioAssessment,
    PositionAction,
    PositionRecommendation,
    render_portfolio_assessment,
)
from tradingagents.portfolio import PortfolioContext
from tradingagents.portfolio_review import compute_metrics

DATES = pd.bdate_range("2025-01-01", periods=120)


def _series(daily_returns, start=100.0):
    return pd.Series(start * np.cumprod(1 + np.asarray(daily_returns)), index=DATES)


def _book(positions, cash=0.0):
    return PortfolioContext.model_validate({"cash": cash, "currency": "USD", "positions": positions})


RNG = np.random.default_rng(7)
BASE = RNG.normal(0.0005, 0.01, len(DATES))


@pytest.mark.unit
def test_weights_are_over_total_value_including_cash():
    closes = {"AAA": _series(np.zeros(len(DATES)), 100.0), "BBB": _series(np.zeros(len(DATES)), 50.0)}
    m = compute_metrics(_book([{"ticker": "AAA", "quantity": 10}, {"ticker": "BBB", "quantity": 20}],
                              cash=2000.0), closes, "2025-06-13")
    assert m.total_value == pytest.approx(4000.0)
    assert {h.ticker: h.weight for h in m.holdings} == {"AAA": pytest.approx(0.25), "BBB": pytest.approx(0.25)}
    assert m.gross_exposure == pytest.approx(0.5)
    assert m.effective_positions == pytest.approx(2.0)


@pytest.mark.unit
def test_unrealized_pnl_uses_average_price():
    closes = {"AAA": _series(np.zeros(len(DATES)), 120.0)}
    m = compute_metrics(_book([{"ticker": "aaa", "quantity": 10, "average_price": 100.0}]), closes, "2025-06-13")
    h = m.holdings[0]
    assert h.unrealized_pnl == pytest.approx(200.0)
    assert h.unrealized_return == pytest.approx(0.2)


@pytest.mark.unit
def test_identical_holdings_are_flagged_as_correlated_and_beta_is_one():
    closes = {"AAA": _series(BASE), "BBB": _series(BASE, 40.0)}
    bench = _series(BASE, 500.0)
    m = compute_metrics(_book([{"ticker": "AAA", "quantity": 10}, {"ticker": "BBB", "quantity": 25}]),
                        closes, "2025-06-13", benchmark_closes=bench)
    assert [(a, b) for a, b, _ in m.high_correlations] == [("AAA", "BBB")]
    assert m.beta == pytest.approx(1.0)
    assert m.annual_volatility == pytest.approx(np.std(BASE[1:], ddof=1) * math.sqrt(252), rel=1e-6)


@pytest.mark.unit
def test_a_short_hedges_the_long():
    closes = {"AAA": _series(BASE), "BBB": _series(BASE)}
    m = compute_metrics(_book([{"ticker": "AAA", "quantity": 10}, {"ticker": "BBB", "quantity": -10}],
                              cash=1000.0), closes, "2025-06-13")
    assert m.net_exposure == pytest.approx(0.0, abs=1e-9)
    assert m.annual_volatility == pytest.approx(0.0, abs=1e-9)


@pytest.mark.unit
def test_drawdown_of_a_falling_then_rising_holding():
    returns = np.zeros(len(DATES))
    returns[10] = -0.5
    returns[20] = 0.5
    m = compute_metrics(_book([{"ticker": "AAA", "quantity": 1}]), {"AAA": _series(returns)}, "2025-06-13")
    assert m.holdings[0].max_drawdown == pytest.approx(-0.5)


@pytest.mark.unit
def test_an_unpriced_holding_is_reported_not_dropped_silently():
    m = compute_metrics(_book([{"ticker": "AAA", "quantity": 1}, {"ticker": "GONE", "quantity": 5}]),
                        {"AAA": _series(BASE)}, "2025-06-13")
    assert [h.ticker for h in m.holdings] == ["AAA"]
    assert m.unpriced == [("GONE", "no price data")]
    assert "GONE" in m.render()


@pytest.mark.unit
def test_missing_cash_is_stated():
    book = PortfolioContext.model_validate({"positions": [{"ticker": "AAA", "quantity": 1}]})
    m = compute_metrics(book, {"AAA": _series(BASE)}, "2025-06-13")
    assert any("cash was not provided" in w for w in m.warnings)


@pytest.mark.unit
def test_sector_weights_sum_positions():
    closes = {"AAA": _series(BASE), "BBB": _series(BASE), "CCC": _series(BASE)}
    m = compute_metrics(
        _book([{"ticker": t, "quantity": 1} for t in closes]), closes, "2025-06-13",
        sectors={"AAA": "Technology", "BBB": "Technology"},
    )
    assert m.sector_weights["Technology"] == pytest.approx(2 / 3)
    assert m.sector_weights["Unknown"] == pytest.approx(1 / 3)


@pytest.mark.unit
def test_render_names_every_holding_and_the_metrics():
    closes = {"AAA": _series(BASE), "BBB": _series(BASE[::-1])}
    text = compute_metrics(_book([{"ticker": "AAA", "quantity": 3}, {"ticker": "BBB", "quantity": 2}],
                                 cash=100.0), closes, "2025-06-13").render()
    for needle in ("AAA", "BBB", "Annualized volatility", "VaR", "Max drawdown", "effective number"):
        assert needle in text


@pytest.mark.unit
def test_assessment_renders_a_row_per_holding():
    text = render_portfolio_assessment(PortfolioAssessment(
        overall_assessment="Concentrated.",
        key_risks=["AAA is 60% of the book"],
        position_actions=[
            PositionRecommendation(ticker="AAA", action=PositionAction.TRIM, rationale="Too large | cut"),
            PositionRecommendation(ticker="BBB", action=PositionAction.HOLD, rationale="Fine"),
        ],
        rebalancing_plan="Trim AAA to 40%.",
    ))
    assert "| AAA | Trim | Too large / cut |" in text
    assert "| BBB | Hold |" in text and "Trim AAA to 40%." in text


class _FakeGraph:
    def __init__(self, selected_analysts=None, config=None, **kw):
        self.deep_thinking_llm = _FakeLLM()
        self.calls = []

    def propagate(self, ticker, trade_date, asset_type="stock", portfolio=None):
        if ticker == "BAD":
            raise RuntimeError("vendor exploded")
        assert portfolio is not None
        return {"final_trade_decision": f"Rating: Buy\n\n{ticker} looks good"}, "Buy"

    def save_reports(self, state, ticker, save_path):
        return save_path


class _FakeLLM:
    prompts: list = []

    def with_structured_output(self, schema):
        raise NotImplementedError

    def invoke(self, prompt):
        _FakeLLM.prompts.append(prompt)
        return type("R", (), {"content": "Book looks fine."})()


@pytest.mark.unit
def test_review_runs_each_holding_and_feeds_the_reviewer(monkeypatch, tmp_path):
    import tradingagents.portfolio_review as pr

    monkeypatch.setattr(pr, "TradingAgentsGraph", _FakeGraph)
    monkeypatch.setattr(pr, "_closes", lambda symbol, as_of: _series(BASE))
    monkeypatch.setattr(pr, "resolve_instrument_identity", lambda symbol: {"sector": "Technology"})
    _FakeLLM.prompts = []

    book = _book([{"ticker": "AAA", "quantity": 3}, {"ticker": "BAD", "quantity": 2}], cash=100.0)
    config = {"results_dir": str(tmp_path), "benchmark_map": {"": "SPY"}}
    result = pr.review_portfolio(book, "2025-06-13", config, run_id="t1")

    assert [(d.ticker, d.rating) for d in result.decisions] == [("AAA", "Buy"), ("BAD", None)]
    prompt = _FakeLLM.prompts[0]
    assert "AAA: Buy" in prompt and "Not analyzed: vendor exploded" in prompt
    assert "Annualized volatility" in prompt
    saved = result.report_path.read_text(encoding="utf-8")
    assert result.report_path == tmp_path / "portfolio_review" / "t1" / "portfolio_review.md"
    assert "Book looks fine." in saved and "not financial advice" in saved


@pytest.mark.unit
def test_metrics_only_skips_the_pipeline(monkeypatch, tmp_path):
    import tradingagents.portfolio_review as pr

    def refuse(*a, **k):
        raise AssertionError("pipeline must not run")

    monkeypatch.setattr(pr, "TradingAgentsGraph", _FakeGraph)
    monkeypatch.setattr(_FakeGraph, "propagate", refuse)
    monkeypatch.setattr(pr, "_closes", lambda symbol, as_of: _series(BASE))
    monkeypatch.setattr(pr, "resolve_instrument_identity", lambda symbol: {})
    _FakeLLM.prompts = []

    result = pr.review_portfolio(_book([{"ticker": "AAA", "quantity": 3}]), "2025-06-13",
                                 {"results_dir": str(tmp_path)}, analyze_holdings=False, run_id="t2")
    assert result.decisions == []
    assert "was not run" in _FakeLLM.prompts[0]


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["2025-6-13", "2999-01-01"])
def test_review_rejects_a_bad_date(bad, tmp_path):
    from tradingagents.portfolio_review import review_portfolio

    with pytest.raises(ValueError):
        review_portfolio(_book([{"ticker": "AAA", "quantity": 1}]), bad, {"results_dir": str(tmp_path)})


@pytest.mark.unit
def test_review_rejects_an_empty_book(tmp_path):
    from tradingagents.portfolio_review import review_portfolio

    with pytest.raises(ValueError, match="no positions"):
        review_portfolio(_book([]), "2025-06-13", {"results_dir": str(tmp_path)})


# --- Options -----------------------------------------------------------------

from tradingagents.option_pricing import black_scholes, implied_volatility  # noqa: E402


@pytest.mark.unit
def test_black_scholes_matches_a_textbook_value_and_put_call_parity():
    call = black_scholes("call", 100, 100, 1.0, 0.05, 0.2)
    put = black_scholes("put", 100, 100, 1.0, 0.05, 0.2)
    assert call.price == pytest.approx(10.4506, abs=1e-3)
    assert call.price - put.price == pytest.approx(100 - 100 * math.exp(-0.05), abs=1e-9)
    assert call.delta - put.delta == pytest.approx(1.0)


@pytest.mark.unit
def test_implied_volatility_recovers_the_input():
    price = black_scholes("call", 700, 800, 2.2, 0.04, 0.18).price
    assert implied_volatility("call", price, 700, 800, 2.2, 0.04) == pytest.approx(0.18, abs=1e-4)
    assert implied_volatility("call", 0.0001, 700, 100, 2.2, 0.04) is None


def _option(**kw):
    base = {"underlying": "SPY", "option_type": "call", "strike": 100.0, "expiry": "2026-06-13",
            "quantity": 2, "average_price": 5.0}
    return {**base, **kw}


@pytest.mark.unit
def test_an_option_is_looked_through_to_its_underlying_at_delta():
    book = PortfolioContext.model_validate({"cash": 0, "options": [_option()]})
    m = compute_metrics(book, {"SPY": _series(BASE)}, "2025-06-13")
    o = m.options[0]
    assert 0 < o.delta < 1 and o.price_source == "model"
    assert o.market_value == pytest.approx(200 * o.price)
    assert o.unrealized_pnl == pytest.approx(o.market_value - 200 * 5.0)
    assert m.exposures[0].option_delta_value == pytest.approx(200 * o.delta * o.spot)
    assert m.gross_exposure > 1  # leverage: delta exposure exceeds the premium held
    assert o.theta_per_day < 0


@pytest.mark.unit
def test_a_mark_dated_the_review_day_is_used_and_its_implied_vol_sets_delta():
    spot = float(_series(BASE).iloc[-1])
    mark = black_scholes("call", spot, 100.0, 365 / 365, 0.04, 0.3).price
    book = PortfolioContext.model_validate(
        {"cash": 0, "options": [_option(mark=mark, mark_date="2025-06-13")]})
    o = compute_metrics(book, {"SPY": _series(BASE)}, "2025-06-13").options[0]
    assert o.price_source == "mark" and o.price == pytest.approx(mark)
    assert o.volatility == pytest.approx(0.3, abs=1e-3)


@pytest.mark.unit
def test_a_mark_from_another_day_is_not_used():
    book = PortfolioContext.model_validate(
        {"cash": 0, "options": [_option(mark=50.0, mark_date="2025-01-02")]})
    m = compute_metrics(book, {"SPY": _series(BASE)}, "2025-06-13")
    assert m.options[0].price_source == "model"
    assert any("not the review date" in w for w in m.warnings)


@pytest.mark.unit
def test_shares_and_options_on_one_underlying_combine():
    book = PortfolioContext.model_validate({
        "cash": 0, "positions": [{"ticker": "SPY", "quantity": 10}], "options": [_option()]})
    m = compute_metrics(book, {"SPY": _series(BASE)}, "2025-06-13")
    assert len(m.exposures) == 1
    e = m.exposures[0]
    assert e.exposure == pytest.approx(e.share_value + e.option_delta_value)
    assert "Exposure by underlying" in m.render()


@pytest.mark.unit
def test_an_expired_option_is_intrinsic_with_no_delta():
    book = PortfolioContext.model_validate({"cash": 0, "options": [_option(expiry="2025-06-01")]})
    m = compute_metrics(book, {"SPY": _series(BASE)}, "2025-06-13")
    o = m.options[0]
    assert o.delta == 0 and o.price == pytest.approx(max(o.spot - 100.0, 0))
    assert any("expired" in w for w in m.warnings)


@pytest.mark.unit
def test_an_option_on_an_unpriced_underlying_is_reported():
    book = PortfolioContext.model_validate({"cash": 0, "options": [_option(underlying="GONE")]})
    m = compute_metrics(book, {}, "2025-06-13")
    assert m.options == [] and "GONE" in m.unpriced[0][1]


@pytest.mark.unit
def test_the_agents_see_options_on_the_analyzed_ticker():
    book = PortfolioContext.model_validate({"cash": 0, "options": [_option()]})
    text = book.render("SPY")
    assert "No current position in SPY" in text and "Option on SPY" in text
    assert "Other options" in book.render("AAPL")
    assert book.underlyings() == ["SPY"]
