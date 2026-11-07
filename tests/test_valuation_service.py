"""The valuation reports end to end with mocked data, and how the analyst plugs into the graph."""

import re
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.config import get_config
from tradingagents.valuation import dcf, service, wacc

AS_OF = "2024-03-14"


def _closes(scale: float, beta: float = 1.0, seed: int = 7) -> pd.Series:
    """About two years of business-day closes ending the day before AS_OF; the stock is ``beta`` x the benchmark."""
    dates = pd.bdate_range(end="2024-03-13", periods=560)
    bench = np.random.default_rng(seed).normal(0.0004, 0.01, len(dates))
    returns = bench * beta + np.random.default_rng(seed + 1).normal(0, 0.002, len(dates))
    series = pd.Series(np.cumprod(1 + returns), index=dates)
    return series * (scale / series.iloc[-1])


def _benchmark() -> pd.Series:
    dates = pd.bdate_range(end="2024-03-13", periods=560)
    returns = np.random.default_rng(7).normal(0.0004, 0.01, len(dates))
    return pd.Series(100 * np.cumprod(1 + returns), index=dates)


def _fake_closes(symbol, end_date, lookback_days):
    return _benchmark() if symbol == "SPY" else _closes(50.0, beta=1.2)


def _company(**over) -> dict:
    data = {
        "source": "sec_edgar", "as_of": AS_OF, "currency": "USD",
        "periods": [{"end": f"{y}-12-31", "cfo": cfo * 1e6, "capex": cx * 1e6}
                    for y, cfo, cx in ((2020, 90, 20), (2021, 100, 22), (2022, 110, 25), (2023, 125, 25))],
        "interest_expense": 20e6, "income_tax": 18e6, "pretax_income": 90e6, "net_income": 72e6,
        "revenue": 800e6, "total_debt": 400e6, "cash": 150e6, "equity": 500e6, "shares": 20e6,
        "is_financial": False, "financial_reason": "", "industry": None, "notes": ["filed data"],
    }
    data.update(over)
    return data


@pytest.fixture
def market():
    """No network: prices, FRED and the benchmark are mocked; the vendor serves ``vendor.data``."""
    vendor = mock.Mock(data=_company(), peers=None)

    def route(method, *args):
        return vendor.data if method == "get_valuation_inputs" else vendor.peers

    with mock.patch.object(service, "route_to_vendor", side_effect=route), \
            mock.patch.object(service, "get_final_closes", side_effect=_fake_closes), \
            mock.patch.object(service, "get_latest_observation", return_value=(4.25, "2024-03-13")):
        yield vendor


def _cell(report: str, label: str) -> str:
    match = re.search(rf"\| {re.escape(label)} \| ([^|]+) \|", report)
    assert match, f"{label!r} not in report"
    return match.group(1).strip()


@pytest.mark.unit
def test_dcf_report_reproduces_its_own_numbers_from_the_inputs(market):
    report = service.dcf_report("ACME", AS_OF)

    cfg = get_config()
    beta = wacc.beta_from_closes(_closes(50.0, beta=1.2), _benchmark()).beta
    ke = 0.0425 + beta * cfg["valuation_equity_risk_premium"]
    tax = 18 / 90
    kd = 20 / 400 * (1 - tax)
    w = wacc.wacc(50.0 * 20e6, 400e6, ke, kd).wacc
    fcfs = [70e6, 78e6, 85e6, 100e6]
    g0, _ = dcf.historical_growth(fcfs, cfg["valuation_growth_floor"], cfg["valuation_growth_cap"])
    expected = dcf.run_dcf(100e6, dcf.fade_growth(g0, cfg["valuation_terminal_growth"], 5), w,
                           cfg["valuation_terminal_growth"], 400e6, 150e6, 20e6)

    assert _cell(report, "Value per share") == f"{expected.value_per_share:,.2f} USD"
    assert _cell(report, "WACC") == f"{w * 100:.2f}%"
    assert _cell(report, "Beta") == f"{beta:.2f}"
    assert _cell(report, "Upside vs price") == f"{expected.value_per_share / 50 - 1:+.1%}"
    assert "FRED 10y Treasury (DGS10) 4.25% on 2024-03-13" in report
    assert "## Sensitivity" in report and report.count("| ") > 40
    assert report.index("## Assumptions") < report.index("## Valuation")


@pytest.mark.unit
def test_dcf_report_uses_the_configured_risk_free_rate_when_fred_is_unavailable(market):
    with mock.patch.object(service, "get_latest_observation", side_effect=OSError("no key")):
        report = service.dcf_report("ACME", AS_OF)
    assert "config default 4.00%" in report and "FRED not used" in report


@pytest.mark.unit
def test_negative_free_cash_flow_is_reported_not_forced_through(market):
    market.data = _company(periods=[{"end": "2023-12-31", "cfo": 10e6, "capex": 40e6}])
    report = service.dcf_report("ACME", AS_OF)
    assert "UNAVAILABLE" in report and "not positive" in report and "do not substitute" in report


@pytest.mark.unit
@pytest.mark.parametrize("missing, text", [("total_debt", "no total debt"), ("cash", "no cash"),
                                           ("shares", "no share count")])
def test_a_missing_input_makes_the_value_unavailable_and_says_which(market, missing, text):
    market.data = _company(**{missing: None})
    report = service.dcf_report("ACME", AS_OF)
    assert "UNAVAILABLE" in report and text in report


@pytest.mark.unit
def test_a_currency_mismatch_is_refused_not_converted(market):
    market.data = _company(source="yfinance", currency="TWD", quote_currency="USD")
    report = service.dcf_report("TSM", AS_OF)
    assert "UNAVAILABLE" in report and "TWD" in report and "no FX" in report


@pytest.mark.unit
def test_vendor_sentinel_text_becomes_the_reason(market):
    market.data = "NO_DATA_AVAILABLE: SAP.DE statements are withheld for 2024-03-14"
    report = service.dcf_report("SAP.DE", AS_OF)
    assert "UNAVAILABLE" in report and "withheld for 2024-03-14" in report


@pytest.mark.unit
def test_a_vendor_that_raises_does_not_end_the_run(market):
    with mock.patch.object(service, "route_to_vendor", side_effect=RuntimeError("boom")):
        report = service.dcf_report("ACME", AS_OF)
    assert "UNAVAILABLE" in report and "boom" in report


@pytest.mark.unit
def test_stale_prices_are_refused(market):
    old = _closes(50.0).iloc[:-30]
    with mock.patch.object(service, "get_final_closes", return_value=old):
        report = service.dcf_report("ACME", AS_OF)
    assert "UNAVAILABLE" in report and "stale" in report


@pytest.mark.unit
def test_a_bank_gets_pb_pe_roe_instead_of_a_dcf(market):
    market.data = _company(is_financial=True, financial_reason="the filer reports bank line items")
    report = service.dcf_report("BANK", AS_OF)

    assert "DCF does not apply" in report and "Enterprise value" not in report
    assert _cell(report, "ROE") == "14.4%"                       # 72 / 500
    assert _cell(report, "Book value per share") == "25.00 USD"  # 500 / 20
    assert _cell(report, "P/B") == "2.00x"
    assert "Justified P/B" in report


@pytest.mark.unit
def test_pence_quoted_prices_are_converted_to_pounds(market):
    market.data = _company(source="yfinance", currency="GBP", quote_currency="GBp")
    report = service.dcf_report("AZN.L", AS_OF)
    assert "divided by 100 to GBP" in report
    assert "Price: 0.50 GBP" in report


def _peers(**over) -> dict:
    data = {
        "source": "yfinance", "as_of": AS_OF, "sector": "Technology", "industry": "Software",
        "is_financial": False, "peer_source": "configured peer list", "notes": [],
        "target": {"name": "Acme", "quote_currency": "USD", "reporting_currency": "USD", "eps": 5.0,
                   "ebitda": 200e6, "revenue": 800e6, "book_value_per_share": 25.0, "total_debt": 400e6,
                   "total_cash": 150e6, "shares": 20e6, "roe": 0.144},
        "peers": [{"symbol": f"P{i}", "name": f"Peer {i}", "pe": pe, "ev_ebitda": ev, "ps": ps, "pb": pb, "roe": 0.1}
                  for i, (pe, ev, ps, pb) in enumerate([(10, 8, 1, 1.5), (20, 12, 3, 2.5), (30, 10, 2, 2.0)])],
    }
    data.update(over)
    return data


@pytest.mark.unit
def test_peer_report_gives_medians_and_implied_prices(market):
    market.peers = _peers()
    report = service.peer_report("ACME", AS_OF)

    assert "| P/E | 10.00x | 20.00x | 3 | 100.00 USD |" in report         # 50 / 5 EPS; 20 x 5
    assert "| P/B | 2.00x | 2.00x | 3 | 50.00 USD |" in report            # 50 / 25; 2 x 25
    assert "| EV/EBITDA | 6.25x | 10.00x | 3 |" in report                  # (50 x 20M + 400M - 150M) / 200M
    assert "Average of the 4 implied prices" in report


@pytest.mark.unit
def test_peer_report_skips_enterprise_multiples_across_currencies(market):
    peers = _peers()
    peers["target"]["reporting_currency"] = "TWD"
    market.peers = peers
    report = service.peer_report("TSM", AS_OF)
    assert "no FX applied" in report and "Warning" in report


@pytest.mark.unit
def test_peer_report_for_a_bank_uses_only_pe_pb_and_roe(market):
    market.peers = _peers(is_financial=True)
    report = service.peer_report("BANK", AS_OF)
    assert "| P/E |" in report and "| P/B |" in report
    assert "| EV/EBITDA |" not in report.split("## Peers")[0]
    assert "only P/B and P/E apply" in report


@pytest.mark.unit
def test_peer_report_unavailable_without_peers_or_data(market):
    market.peers = _peers(peers=[])
    assert "UNAVAILABLE" in service.peer_report("ACME", AS_OF)
    market.peers = "NO_DATA_AVAILABLE: peer multiples withheld for 2024-03-14"
    report = service.peer_report("ACME", AS_OF)
    assert "UNAVAILABLE" in report and "withheld for 2024-03-14" in report


@pytest.mark.unit
def test_configured_peers_are_matched_case_insensitively():
    cfg = {"valuation_peer_map": {"2222.sr": ["1120.SR", "2010.SR"]}}
    assert service._configured_peers("2222.SR", cfg) == ["1120.SR", "2010.SR"]
    assert service._configured_peers("AAPL", cfg) is None


# ---------------------------------------------------------------- graph wiring


@pytest.mark.unit
def test_valuation_analyst_is_registered_and_runs_beside_the_others():
    from tradingagents.graph.analyst_execution import (
        ANALYST_NODE_SPECS,
        build_analyst_execution_plan,
    )

    spec = ANALYST_NODE_SPECS["valuation"]
    assert (spec.agent_node, spec.report_key) == ("Valuation Analyst", "valuation_report")
    assert {t.name for t in spec.tools} == {"get_dcf_valuation", "get_peer_multiples"}
    plan = build_analyst_execution_plan(["market", "valuation"])
    assert [s.key for s in plan.specs] == ["market", "valuation"]


@pytest.mark.unit
def test_valuation_tools_are_clamped_to_the_run_date_and_use_the_ticker_in_state():
    from tradingagents.agents import tools

    with mock.patch("tradingagents.valuation.service.dcf_report", return_value="report") as dcf_report:
        out = tools.get_dcf_valuation.func("ACME", curr_date="2030-01-01", trade_date=AS_OF)
    assert out == "report"
    assert dcf_report.call_args.args == ("ACME", AS_OF)


@pytest.mark.unit
def test_selecting_valuation_with_it_disabled_in_config_is_refused():
    import copy

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["valuation_enabled"] = False
    with pytest.raises(ValueError, match="valuation_enabled"):
        TradingAgentsGraph(selected_analysts=["market", "valuation"], config=config)


@pytest.mark.unit
def test_downstream_prompts_carry_the_valuation_report_only_when_there_is_one():
    from tradingagents.agents.context import valuation_block

    assert valuation_block({}) == "" and valuation_block({"valuation_report": "  "}) == ""
    assert "DCF says 62" in valuation_block({"valuation_report": "DCF says 62"})


def _state(**over):
    state = {
        "company_of_interest": "ACME", "trade_date": AS_OF, "asset_type": "stock",
        "market_report": "m", "sentiment_report": "s", "news_report": "n", "fundamentals_report": "f",
        "valuation_report": "", "past_context": "", "portfolio_context": "",
        "investment_debate_state": {"history": "h", "bull_history": "", "bear_history": "", "current_response": "",
                                    "count": 0},
        "investment_plan": "plan", "trader_investment_plan": "trade",
        "risk_debate_state": {"history": "h", "aggressive_history": "", "conservative_history": "",
                              "neutral_history": "", "latest_speaker": "", "current_aggressive_response": "",
                              "current_conservative_response": "", "current_neutral_response": "", "count": 0},
    }
    state.update(over)
    return state


def _prompt_of(factory, state):
    llm = mock.MagicMock()
    llm.invoke.return_value.content = "ok"
    # No structured output, so the manager nodes send their prompt as free text.
    with mock.patch("tradingagents.agents.managers.research_manager.bind_structured", return_value=None), \
            mock.patch("tradingagents.agents.managers.portfolio_manager.bind_structured", return_value=None):
        factory(llm)(state)
    return str(llm.invoke.call_args.args[0])


@pytest.mark.unit
@pytest.mark.parametrize("module, factory", [
    ("researchers.bull_researcher", "create_bull_researcher"),
    ("researchers.bear_researcher", "create_bear_researcher"),
    ("managers.research_manager", "create_research_manager"),
    ("managers.portfolio_manager", "create_portfolio_manager"),
])
def test_researchers_and_managers_receive_the_valuation_report(module, factory):
    import importlib

    create = getattr(importlib.import_module(f"tradingagents.agents.{module}"), factory)
    without = _prompt_of(create, _state())
    with_report = _prompt_of(create, _state(valuation_report="DCF says 62 per share"))

    assert "DCF says 62 per share" in with_report
    assert "Valuation report" not in without and "valuation" not in without.lower().replace("devaluation", "")


@pytest.mark.unit
def test_the_report_tree_and_html_include_the_valuation_section(tmp_path):
    from tradingagents.reporting import write_report_tree

    state = {"trade_date": AS_OF, "market_report": "market text", "valuation_report": "## DCF\nvalue 62"}
    path = write_report_tree(state, "ACME", tmp_path)

    assert (tmp_path / "1_analysts" / "valuation.md").read_text(encoding="utf-8") == "## DCF\nvalue 62"
    assert "### Valuation Analyst" in path.read_text(encoding="utf-8")
    html = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    assert "Valuation Analyst" in html and "value 62" in html


@pytest.mark.unit
def test_a_run_without_valuation_writes_no_valuation_file(tmp_path):
    from tradingagents.reporting import write_report_tree

    write_report_tree({"trade_date": AS_OF, "market_report": "market text"}, "ACME", tmp_path)
    assert not (tmp_path / "1_analysts" / "valuation.md").exists()


@pytest.mark.unit
def test_cli_selects_valuation_by_name_but_never_by_default():
    from cli.models import AnalystType, AssetType
    from cli.prompts import filter_analysts_for_asset_type, parse_analysts

    assert parse_analysts("market,valuation", AssetType.STOCK) == [AnalystType.MARKET, AnalystType.VALUATION]
    with pytest.raises(ValueError, match="not available for crypto"):
        parse_analysts("valuation", AssetType.CRYPTO)
    assert AnalystType.VALUATION not in filter_analysts_for_asset_type(list(AnalystType), AssetType.CRYPTO)


@pytest.mark.unit
def test_valuation_data_is_routed_through_the_vendor_chain():
    from tradingagents.dataflows import router

    assert router.get_category_for_method("get_valuation_inputs") == "valuation_data"
    assert set(router.VENDOR_METHODS["get_valuation_inputs"]) == {"sec_edgar", "yfinance"}
    assert set(router.VENDOR_METHODS["get_peer_snapshot"]) == {"yfinance"}
