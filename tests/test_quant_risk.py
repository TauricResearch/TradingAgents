"""Quantitative risk metrics: the arithmetic checked by hand, point-in-time prices, and the graph wiring."""

import copy
import math
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.risk_metrics import metrics as rm, service

AS_OF = "2024-03-14"


def _series(values, end="2024-03-13"):
    return pd.Series(values, index=pd.bdate_range(end=end, periods=len(values)), dtype=float)


# ---------------------------------------------------------------- arithmetic


@pytest.mark.unit
def test_max_drawdown_is_the_deepest_fall_from_a_running_peak():
    closes = _series([100, 120, 90, 110, 80, 130])
    depth, peak, trough = rm.max_drawdown(closes)
    assert depth == pytest.approx(1 / 3)                       # 120 -> 80
    assert peak == f"{closes.index[1]:%Y-%m-%d}" and trough == f"{closes.index[4]:%Y-%m-%d}"


@pytest.mark.unit
def test_historical_var_and_cvar_on_a_known_distribution():
    returns = pd.Series(np.arange(-50, 50) / 1000)             # -5.0% .. +4.9%, 100 days
    # 5% quantile sits at position 4.95: -4.6% + 0.95 x 0.1% = -4.505%
    assert rm.var_historical(returns, 0.95) == pytest.approx(0.04505)
    # the five days at or below it average -4.8%
    assert rm.cvar_historical(returns, 0.95) == pytest.approx(0.048)


@pytest.mark.unit
def test_parametric_var_and_cvar_use_the_normal_formulas():
    returns = pd.Series(np.random.default_rng(3).normal(0.0005, 0.012, 500))
    mu, sigma = returns.mean(), returns.std(ddof=1)
    assert rm.var_parametric(returns, 0.95) == pytest.approx(1.6448536 * sigma - mu, rel=1e-6)
    assert rm.cvar_parametric(returns, 0.95) == pytest.approx(sigma * 0.1031356 / 0.05 - mu, rel=1e-5)
    assert rm.cvar_parametric(returns) > rm.var_parametric(returns)


@pytest.mark.unit
def test_volatility_is_daily_sigma_scaled_by_the_square_root_of_the_year():
    returns = pd.Series([0.01, -0.02, 0.015, 0.0, -0.005])
    assert rm.annualized_volatility(returns, 252) == pytest.approx(returns.std(ddof=1) * math.sqrt(252))
    assert rm.annualized_volatility(returns, 365) > rm.annualized_volatility(returns, 252)


@pytest.mark.unit
def test_sortino_against_a_hand_worked_example():
    # returns 2%, -1%, 3%, -2%; target 0; 4 periods a year so sqrt(4) = 2.
    # mean 0.5%; downside deviation = sqrt((0 + 1e-4 + 0 + 4e-4) / 4) = 1.118%; 0.5 / 1.118 x 2 = 0.8944
    returns = pd.Series([0.02, -0.01, 0.03, -0.02])
    assert rm.sortino_ratio(returns, 0.0, 4) == pytest.approx(2 / math.sqrt(5))


@pytest.mark.unit
def test_sharpe_subtracts_the_daily_risk_free_rate():
    returns = pd.Series(np.random.default_rng(5).normal(0.001, 0.01, 250))
    excess = returns - 0.05 / 252
    expected = excess.mean() / excess.std(ddof=1) * math.sqrt(252)
    assert rm.sharpe_ratio(returns, 0.05, 252) == pytest.approx(expected)


@pytest.mark.unit
def test_ratios_that_would_divide_by_zero_are_reported_not_invented():
    with pytest.raises(rm.RiskMetricsError, match="Sharpe"):
        rm.sharpe_ratio(pd.Series([0.01] * 10), 0.0, 252)
    with pytest.raises(rm.RiskMetricsError, match="Sortino"):
        rm.sortino_ratio(pd.Series([0.01, 0.02, 0.03]), 0.0, 252)


@pytest.mark.unit
def test_atr_is_wilders_smoothed_true_range():
    bars = pd.DataFrame({"High": [11, 12, 13, 12, 14], "Low": [9, 10, 11, 10, 12], "Close": [10, 11, 12, 11, 13]},
                        index=pd.bdate_range("2024-03-04", periods=5), dtype=float)
    # true ranges: 2, 2, 2, 3. ATR(3) = mean(2, 2, 2) = 2; then (2 x 2 + 3) / 3 = 7/3
    assert rm.atr(bars, 3) == pytest.approx(7 / 3)
    with pytest.raises(rm.RiskMetricsError, match="needs 14"):
        rm.atr(bars, 14)


@pytest.mark.unit
def test_true_range_uses_the_gap_from_the_previous_close():
    bars = pd.DataFrame({"High": [10, 16], "Low": [9, 15], "Close": [9.5, 15.5]},
                        index=pd.bdate_range("2024-03-04", periods=2))
    assert rm.true_range(bars).iloc[0] == pytest.approx(6.5)   # |16 - 9.5|, not High - Low = 1


@pytest.mark.unit
def test_beta_is_two_for_a_stock_that_moves_twice_the_benchmark():
    bench = pd.Series(np.random.default_rng(9).normal(0, 0.01, 200))
    value, n = rm.beta(2 * bench, bench)
    assert value == pytest.approx(2.0) and n == 200


@pytest.mark.unit
def test_position_size_spends_the_risk_budget_at_the_atr_stop():
    # price 100, ATR 2, 2 x ATR stop = 4% away; 1% of the book at risk -> 25% of the book.
    size = rm.position_size(100, 2.0, 2.0, 0.01, 1.0)
    assert size.stop_distance_pct == pytest.approx(0.04)
    assert size.size_pct == pytest.approx(0.25) and not size.capped
    assert size.book_risk_pct == pytest.approx(0.01)


@pytest.mark.unit
def test_position_size_is_capped_and_the_book_risk_then_falls_below_budget():
    size = rm.position_size(100, 2.0, 2.0, 0.01, 0.20)
    assert size.size_pct == 0.20 and size.uncapped_pct == pytest.approx(0.25) and size.capped
    assert size.book_risk_pct == pytest.approx(0.008)


# ---------------------------------------------------------------- the block


def _bars(n=300, seed=11):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2024-03-13", periods=n)
    close = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    return pd.DataFrame({"High": close * 1.01, "Low": close * 0.99, "Close": close}, index=dates)


def _bench(n=300, seed=12):
    dates = pd.bdate_range(end="2024-03-13", periods=n)
    return pd.Series(400 * np.cumprod(1 + np.random.default_rng(seed).normal(0.0003, 0.008, n)), index=dates)


@pytest.fixture
def prices():
    with mock.patch.object(service, "get_final_bars", side_effect=lambda *a: _bars()), \
            mock.patch.object(service, "get_final_closes", side_effect=lambda *a: _bench()), \
            mock.patch.object(service, "get_latest_observation", return_value=(5.0, "2024-03-13")) as fred:
        yield fred


@pytest.mark.unit
def test_the_block_reports_every_metric_with_the_numbers_the_maths_gives(prices):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    block = service.risk_block("ACME", AS_OF, "stock", cfg)

    expected = rm.compute(_bars(), _bench(), risk_free=0.05, periods=252, confidence=0.95, atr_window=14,
                          atr_multiple=2.0, risk_per_position=0.01, max_position=1.0)
    assert f"| Annualized volatility | {expected.volatility * 100:.2f}% |" in block
    assert f"| Beta vs benchmark | {expected.beta:.2f} |" in block
    assert f"| Max drawdown | {expected.max_drawdown * 100:.2f}% |" in block
    assert f"| 1-day VaR 95%, historical | {expected.var_hist * 100:.2f}% |" in block
    assert f"| 1-day CVaR 95%, parametric | {expected.cvar_param * 100:.2f}% |" in block
    assert f"| Volatility-scaled position size | {expected.sizing.size_pct:.1%} of the book |" in block
    assert f"| Stop, long (2 x ATR below) | {expected.stop_long:,.2f} |" in block
    for label in ("Sharpe ratio", "Sortino ratio", "ATR(14)", "Risk per position", "Book loss if the stop is hit"):
        assert label in block
    assert "FRED DTB3 5.00% on 2024-03-13" in block and "benchmark: SPY" in block


@pytest.mark.unit
def test_risk_per_position_and_atr_multiple_are_configurable(prices):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(risk_metrics_risk_per_position=0.005, risk_metrics_atr_multiple=3.0)
    block = service.risk_block("ACME", AS_OF, "stock", cfg)
    expected = rm.compute(_bars(), _bench(), risk_free=0.05, periods=252, confidence=0.95, atr_window=14,
                          atr_multiple=3.0, risk_per_position=0.005, max_position=1.0)
    assert f"{expected.sizing.size_pct:.1%} of the book" in block
    assert "Stop, long (3 x ATR below)" in block and "| Risk per position | 0.50% |" in block


@pytest.mark.unit
def test_crypto_is_annualised_over_365_days(prices):
    stock = service.risk_block("ACME", AS_OF, "stock", copy.deepcopy(DEFAULT_CONFIG))
    crypto = service.risk_block("BTC-USD", AS_OF, "crypto", copy.deepcopy(DEFAULT_CONFIG))
    vol = lambda text: float(text.split("| Annualized volatility | ")[1].split("%")[0])  # noqa: E731
    assert vol(crypto) / vol(stock) == pytest.approx(math.sqrt(365 / 252), rel=1e-3)


@pytest.mark.unit
def test_the_risk_free_rate_falls_back_to_the_config_default_without_fred(prices):
    prices.side_effect = OSError("no key")
    block = service.risk_block("ACME", AS_OF, "stock", copy.deepcopy(DEFAULT_CONFIG))
    assert "config default 4.00%" in block and "FRED not used" in block


@pytest.mark.unit
def test_a_missing_benchmark_leaves_beta_unavailable_but_keeps_the_rest(prices):
    with mock.patch.object(service, "get_final_closes", return_value=pd.Series(dtype=float)):
        block = service.risk_block("ACME", AS_OF, "stock", copy.deepcopy(DEFAULT_CONFIG))
    assert "| Beta vs benchmark | n/a |" in block and "beta unavailable: no benchmark prices" in block
    assert "Annualized volatility" in block


@pytest.mark.unit
@pytest.mark.parametrize("bars, text", [
    (pd.DataFrame(columns=["High", "Low", "Close"], dtype=float), "no daily prices"),
    (_bars(30), "only 29 daily returns"),
    (_bars().iloc[:-30], "stale"),
])
def test_unusable_prices_make_the_block_unavailable_and_say_why(prices, bars, text):
    with mock.patch.object(service, "get_final_bars", return_value=bars):
        block = service.risk_block("ACME", AS_OF, "stock", copy.deepcopy(DEFAULT_CONFIG))
    assert "UNAVAILABLE" in block and text in block and "estimated" in block


@pytest.mark.unit
def test_a_vendor_failure_does_not_end_the_run(prices):
    with mock.patch.object(service, "get_final_bars", side_effect=RuntimeError("boom")):
        block = service.risk_block("ACME", AS_OF, "stock", copy.deepcopy(DEFAULT_CONFIG))
    assert "UNAVAILABLE" in block and "boom" in block


# ---------------------------------------------------------------- point in time


@pytest.mark.unit
def test_bars_never_include_a_day_after_the_run_date_or_a_session_still_trading():
    from tradingagents.dataflows.vendors.yahoo import market

    today = pd.Timestamp.now().normalize()
    index = pd.DatetimeIndex([today - pd.Timedelta(days=2), today - pd.Timedelta(days=1), today])
    history = pd.DataFrame({"High": [11, 12, 13], "Low": [9, 10, 11], "Close": [10, 11, 12]}, index=index, dtype=float)
    asked = {}

    def fake_retry(func):
        class Ticker:
            def history(self, **kwargs):
                asked.update(kwargs)
                return history
        with mock.patch.object(market.yf, "Ticker", return_value=Ticker()):
            return func()

    with mock.patch.object(market, "yf_retry", side_effect=fake_retry):
        bars = market.get_final_bars("AAPL", f"{today:%Y-%m-%d}", 30)

    assert list(bars["Close"]) == [10, 11]                       # today's live bar is dropped
    assert asked["end"] == f"{today + pd.Timedelta(days=1):%Y-%m-%d}"   # exclusive: nothing past the run date


# ---------------------------------------------------------------- graph wiring


@pytest.mark.unit
def test_the_risk_step_is_a_graph_node_only_when_given():
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.setup import GraphSetup
    from tradingagents.risk_metrics.node import create_quant_risk_node

    setup = GraphSetup(mock.MagicMock(), mock.MagicMock(), ConditionalLogic(1, 1), 5)
    with_node = setup.setup_graph(["market"], quant_risk_node=create_quant_risk_node())
    without = setup.setup_graph(["market"])
    assert "Quant Risk" in with_node.nodes and "Quant Risk" not in without.nodes


@pytest.mark.unit
def test_the_risk_step_can_be_switched_off_in_config(tmp_path):
    from tradingagents.graph import trading_graph

    def build(**config):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg.update(results_dir=str(tmp_path / "r"), data_cache_dir=str(tmp_path / "c"),
                   memory_log_path=str(tmp_path / "m.md"), **config)
        with mock.patch.object(trading_graph, "create_tier_client", return_value=mock.Mock()):
            return trading_graph.TradingAgentsGraph(selected_analysts=["market"], config=cfg)

    on, off = build(), build(risk_metrics_enabled=False)
    assert "Quant Risk" in on.workflow.nodes and "Quant Risk" not in off.workflow.nodes
    assert "quant_risk=parallel" in on._run_signature("stock")
    assert "quant_risk" not in off._run_signature("stock").split("settings=")[0]


@pytest.mark.unit
def test_the_block_reaches_the_trader_the_three_debators_and_the_portfolio_manager():
    from tests.test_valuation_service import _prompt_of, _state
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
    from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
    from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
    from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
    from tradingagents.agents.trader.trader import create_trader

    block = "## Quantitative Risk Metrics\n| ATR stop | 91.20 |"
    for factory in (create_aggressive_debator, create_conservative_debator, create_neutral_debator,
                    create_portfolio_manager):
        without = _prompt_of(factory, _state())
        with_block = _prompt_of(factory, _state(quant_risk_metrics=block))
        assert "ATR stop | 91.20" in with_block and "Anchor every position-size" in with_block
        assert "Quantitative Risk" not in without, factory.__name__

    def trader_prompt(state):
        llm = mock.MagicMock()
        with mock.patch("tradingagents.agents.trader.trader.bind_structured", return_value=None), \
                mock.patch("tradingagents.agents.trader.trader.invoke_structured_or_freetext",
                           return_value="plan") as call:
            create_trader(llm)(state)
        return str(call.call_args.args[2])

    assert "ATR stop | 91.20" in trader_prompt(_state(quant_risk_metrics=block))
    assert "Quantitative Risk" not in trader_prompt(_state())


@pytest.mark.unit
def test_the_block_is_in_the_saved_markdown_and_html_report(tmp_path):
    from tradingagents.reporting import write_report_tree

    state = {"trade_date": AS_OF, "quant_risk_metrics": "## Quantitative Risk Metrics\nstop 91.20"}
    path = write_report_tree(state, "ACME", tmp_path)

    assert (tmp_path / "4_risk" / "quant_risk.md").read_text(encoding="utf-8").endswith("stop 91.20")
    assert "### Quantitative Risk Metrics" in path.read_text(encoding="utf-8")
    assert "stop 91.20" in (tmp_path / "complete_report.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_a_whole_run_computes_the_block_and_hands_it_to_the_risk_team(tmp_path, monkeypatch):
    """The scripted graph, with prices mocked: the block lands in state and in the debators' prompts."""
    from tests import test_graph_end_to_end as e2e

    class Recording(e2e.ScriptedModel):
        prompts: list = e2e.Field(default_factory=list)

        def _generate(self, messages, *args, **kwargs):
            self.prompts.append(str(messages))
            return super()._generate(messages, *args, **kwargs)

    dates = pd.bdate_range(end=e2e.TRADE_DATE, periods=300)[:-1]
    bars = pd.DataFrame({"High": 101.0, "Low": 99.0, "Close": np.linspace(90, 100, len(dates))}, index=dates)
    monkeypatch.setattr(service, "get_final_bars", lambda *a: bars)
    monkeypatch.setattr(service, "get_final_closes", lambda *a: bars["Close"] * 4)
    monkeypatch.setattr(service, "get_latest_observation", mock.Mock(side_effect=OSError("no key")))
    from tradingagents.agents import context
    from tradingagents.agents.analysts import sentiment_analyst
    from tradingagents.dataflows import router
    from tradingagents.dataflows.vendors.yahoo import market as yahoo_market, snapshot

    for method, vendors in router.VENDOR_METHODS.items():
        for vendor in vendors:
            monkeypatch.setitem(vendors, vendor, lambda *a, _m=method, **k: f"{_m} data")
    frame = pd.DataFrame({"Date": pd.bdate_range(end=e2e.TRADE_DATE, periods=60), "Open": 100.0, "High": 101.0,
                          "Low": 99.0, "Close": 100.5, "Volume": 1_000_000})
    monkeypatch.setattr(snapshot, "load_ohlcv", lambda *a, **k: frame.copy())
    monkeypatch.setattr(sentiment_analyst, "fetch_stocktwits_messages", lambda *a, **k: "no posts")
    monkeypatch.setattr(sentiment_analyst, "fetch_reddit_posts", lambda *a, **k: "no posts")
    monkeypatch.setattr(yahoo_market.yf, "Ticker", lambda s: type("T", (), {"info": {"longName": "NVIDIA"}})())
    context._identity.cache_clear()

    model = Recording()
    graph = e2e._graph(tmp_path, monkeypatch, model)
    state, _ = graph.propagate("NVDA", e2e.TRADE_DATE)

    assert "## Quantitative Risk Metrics for NVDA" in state["quant_risk_metrics"]
    assert "Volatility-scaled position size" in state["quant_risk_metrics"]
    seen = [p for p in model.prompts if "Risk Analyst" in p or "Portfolio Manager" in p]
    assert seen and all("Volatility-scaled position size" in p for p in seen)
