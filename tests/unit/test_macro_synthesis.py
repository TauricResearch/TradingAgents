import json

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import tradingagents.agents.scanners.macro_synthesis as macro_synthesis_module
from tradingagents.agents.scanners.macro_synthesis import (
    _build_candidate_rankings,
    _extract_rankable_tickers,
    _format_horizon_label,
    _parse_gatekeeper_rows,
    _repair_macro_summary,
    create_macro_synthesis,
)
from tradingagents.dataflows.macro_regime import format_macro_report as real_format_macro_report


@pytest.fixture(autouse=True)
def _deterministic_macro_regime(monkeypatch):
    monkeypatch.setattr(
        macro_synthesis_module,
        "classify_macro_regime",
        lambda scan_date: {
            "regime": "risk-on",
            "score": 4,
            "confidence": "high",
            "summary": f"Risk-on regime for {scan_date}",
            "signals": [],
        },
        raising=False,
    )
    monkeypatch.setattr(
        macro_synthesis_module,
        "format_macro_report",
        lambda regime_data, *, report_date=None: (
            "# Macro Regime Classification\n\n"
            f"# Data retrieved on: {report_date or 'fixture-date'}\n\n"
            f"## Regime: {regime_data['regime'].upper()}\n\n"
            f"| Composite Score | {regime_data['score']:+d} / 6 |"
        ),
        raising=False,
    )


def test_format_horizon_label_supported_values():
    assert _format_horizon_label(30) == "1 month"
    assert _format_horizon_label(60) == "2 months"
    assert _format_horizon_label(90) == "3 months"


def test_format_horizon_label_unsupported_defaults_to_one_month():
    assert _format_horizon_label(45) == "1 month"


def test_extract_rankable_tickers_filters_noise():
    tickers = _extract_rankable_tickers(
        "NVDA and AAPL look strong; GDP and JSON are not tickers. MSFT also appears."
    )
    assert {"NVDA", "AAPL", "MSFT"} <= tickers
    assert "GDP" not in tickers
    assert "JSON" not in tickers


def test_build_candidate_rankings_rewards_overlap():
    state = {
        "gatekeeper_universe_report": "NVDA AAPL MSFT",
        "market_movers_report": "NVDA AAPL",
        "smart_money_report": "NVDA",
        "factor_alignment_report": "NVDA MSFT",
        "drift_opportunities_report": "NVDA AAPL",
        "industry_deep_dive_report": "MSFT",
    }
    ranked = _build_candidate_rankings(state)

    assert ranked[0]["ticker"] == "NVDA"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_build_candidate_rankings_excludes_names_outside_gatekeeper():
    state = {
        "gatekeeper_universe_report": "NVDA AAPL",
        "market_movers_report": "NVDA TSLA",
        "drift_opportunities_report": "TSLA",
    }

    ranked = _build_candidate_rankings(state)

    tickers = {row["ticker"] for row in ranked}
    assert "NVDA" in tickers
    assert "TSLA" not in tickers


def test_parse_gatekeeper_rows_extracts_symbol_and_name():
    rows = _parse_gatekeeper_rows(
        """
| Symbol | Name | Exchange | Price |
|--------|------|----------|-------|
| NVDA | NVIDIA Corporation | NMS | $100 |
| MSFT | Microsoft Corporation | NMS | $200 |
"""
    )

    assert rows == [
        {"ticker": "NVDA", "name": "NVIDIA Corporation"},
        {"ticker": "MSFT", "name": "Microsoft Corporation"},
    ]


def test_repair_macro_summary_filters_and_backfills_to_requested_count():
    state = {
        "gatekeeper_universe_report": """
| Symbol | Name | Exchange | Price |
|--------|------|----------|-------|
| NVDA | NVIDIA Corporation | NMS | $100 |
| AAPL | Apple Inc. | NMS | $200 |
| MSFT | Microsoft Corporation | NMS | $300 |
| AMZN | Amazon.com, Inc. | NMS | $400 |
""",
        "market_movers_report": "NVDA AAPL",
        "smart_money_report": "MSFT",
        "factor_alignment_report": "NVDA MSFT",
        "drift_opportunities_report": "AAPL",
        "industry_deep_dive_report": "AMZN",
    }
    parsed = {
        "executive_summary": "Summary",
        "stocks_to_investigate": [
            {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology"},
            {"ticker": "TSLA", "name": "Tesla, Inc.", "sector": "Auto"},
        ],
    }

    repaired = _repair_macro_summary(parsed, state, max_scan_tickers=4, horizon_label="1 month")

    tickers = [row["ticker"] for row in repaired["stocks_to_investigate"]]
    assert tickers == ["NVDA", "MSFT", "AAPL", "AMZN"]
    assert repaired["timeframe"] == "1 month"
    assert repaired["stocks_to_investigate"][2]["name"] == "Apple Inc."


def test_macro_synthesis_ignores_prior_message_history_when_prompting_llm(monkeypatch):
    captured_prompt = None

    def _invoke(prompt_value):
        nonlocal captured_prompt
        captured_prompt = prompt_value
        return AIMessage(
            content='{"timeframe":"1 month","executive_summary":"Summary","macro_context":{},'
            '"key_themes":[],"stocks_to_investigate":[],"risk_factors":[]}'
        )

    llm = RunnableLambda(_invoke)
    agent = create_macro_synthesis(llm, max_scan_tickers=3, scan_horizon_days=30)
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.save_node_report",
        lambda *_args, **_kwargs: None,
    )

    result = agent(
        {
            "scan_date": "2026-03-30",
            "run_id": "RUN1",
            "messages": [
                AIMessage(
                    content=[{"type": "text", "text": "provider-native block"}],
                    additional_kwargs={
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "legacy_tool",
                                    "arguments": '{"foo":"bar"}',
                                },
                            }
                        ]
                    },
                )
            ],
            "gatekeeper_universe_report": "NVDA AAPL MSFT",
            "geopolitical_report": "Geopolitical context",
            "market_movers_report": "Market movers context",
            "sector_performance_report": "Sector context",
            "factor_alignment_report": "Factor context",
            "drift_opportunities_report": "Drift context",
            "smart_money_report": "Smart money context",
            "industry_deep_dive_report": "Industry context",
        }
    )

    messages = captured_prompt.to_messages()
    assert [type(message).__name__ for message in messages] == ["SystemMessage", "HumanMessage"]
    assert messages[1].content == "Produce the final macro synthesis now as JSON only."
    assert "provider-native block" not in captured_prompt.to_string()
    assert result["macro_scan_summary"]


def test_macro_synthesis_persists_structured_canonical_regime_without_score_token(monkeypatch):
    saved_reports = []
    classify_dates = []

    def _save_node_report(state, report_key, report):
        saved_reports.append((report_key, report))

    def _classify_macro_regime(scan_date):
        classify_dates.append(scan_date)
        return {
            "regime": "risk-on",
            "score": 4,
            "confidence": "high",
            "summary": f"Risk-on regime for {scan_date}",
            "signals": [],
        }

    def _invoke(_prompt_value):
        return AIMessage(
            content='{"timeframe":"1 month","executive_summary":"Summary without score token",'
            '"macro_context":{},"key_themes":[],"stocks_to_investigate":[],'
            '"risk_factors":[]}'
        )

    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.save_node_report",
        _save_node_report,
    )
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.classify_macro_regime",
        _classify_macro_regime,
    )

    agent = create_macro_synthesis(
        RunnableLambda(_invoke), max_scan_tickers=3, scan_horizon_days=30
    )

    result = agent(
        {
            "scan_date": "2026-03-30",
            "run_id": "RUN1",
            "messages": [],
            "gatekeeper_universe_report": "NVDA AAPL MSFT",
            "geopolitical_report": "Geopolitical context",
            "market_movers_report": "Market movers context",
            "sector_performance_report": "Sector context",
            "factor_alignment_report": "Factor context",
            "drift_opportunities_report": "Drift context",
            "smart_money_report": "Smart money context",
            "industry_deep_dive_report": "Industry context",
        }
    )

    macro_summary = json.loads(result["macro_scan_summary"])

    assert macro_summary["canonical_regime"] == {
        "label": "RISK-ON",
        "score": 4,
        "confidence": "high",
    }
    assert result["macro_regime_report"].startswith("# Macro Regime Classification")
    assert saved_reports == [
        ("macro_regime_report", result["macro_regime_report"]),
        ("macro_scan_summary", result["macro_scan_summary"]),
    ]
    assert classify_dates == ["2026-03-30"]


def test_macro_synthesis_idempotent_summary_returns_existing_regime_report(monkeypatch):
    def _classify_macro_regime(_scan_date):
        raise AssertionError("classification should not run for an existing summary")

    def _invoke(_prompt_value):
        raise AssertionError("LLM should not run for an existing summary")

    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.check_and_load_report",
        lambda _state, report_key: "existing summary" if report_key == "macro_scan_summary" else "",
    )
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.classify_macro_regime",
        _classify_macro_regime,
    )

    agent = create_macro_synthesis(RunnableLambda(_invoke), max_scan_tickers=3)

    result = agent(
        {
            "scan_date": "2026-03-30",
            "run_id": "RUN1",
            "messages": [],
            "macro_regime_report": "existing regime report",
        }
    )

    assert result == {
        "macro_scan_summary": "existing summary",
        "macro_regime_report": "existing regime report",
        "sender": "macro_synthesis",
    }


def test_macro_synthesis_fails_when_regime_report_lacks_score(monkeypatch):
    def _invoke(_prompt_value):
        raise AssertionError("LLM should not run when macro regime formatting is invalid")

    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.format_macro_report",
        lambda _regime_data, *, report_date=None: (
            "# Macro Regime Classification\n\n## Regime: RISK-ON"
        ),
    )

    agent = create_macro_synthesis(RunnableLambda(_invoke), max_scan_tickers=3)

    with pytest.raises(RuntimeError) as exc:
        agent(
            {
                "scan_date": "2026-03-30",
                "run_id": "RUN1",
                "messages": [],
            }
        )

    assert "score" in str(exc.value)


def test_macro_synthesis_regime_report_uses_scan_date_not_wall_clock(monkeypatch):
    saved_reports = []

    def _save_node_report(_state, report_key, report):
        saved_reports.append((report_key, report))

    def _invoke(_prompt_value):
        return AIMessage(
            content='{"timeframe":"1 month","executive_summary":"Summary",'
            '"macro_context":{},"key_themes":[],"stocks_to_investigate":[],'
            '"risk_factors":[]}'
        )

    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.format_macro_report",
        real_format_macro_report,
    )
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.save_node_report",
        _save_node_report,
    )

    agent = create_macro_synthesis(RunnableLambda(_invoke), max_scan_tickers=3)

    result = agent(
        {
            "scan_date": "2026-03-30",
            "run_id": "RUN1",
            "messages": [],
            "gatekeeper_universe_report": "NVDA AAPL MSFT",
            "geopolitical_report": "Geopolitical context",
            "market_movers_report": "Market movers context",
            "sector_performance_report": "Sector context",
            "factor_alignment_report": "Factor context",
            "drift_opportunities_report": "Drift context",
            "smart_money_report": "Smart money context",
            "industry_deep_dive_report": "Industry context",
        }
    )

    assert "# Data retrieved on: 2026-03-30" in result["macro_regime_report"]
    assert "2026-03-30 " not in result["macro_regime_report"]
    assert saved_reports[0] == ("macro_regime_report", result["macro_regime_report"])


def test_macro_synthesis_respects_configured_deep_timeout_cap(monkeypatch):
    captured_timeout = None

    def _invoke_with_timeout(_chain, _input, *, timeout_seconds, max_tokens=None):
        nonlocal captured_timeout
        captured_timeout = timeout_seconds
        return (
            AIMessage(
                content='{"timeframe":"1 month","executive_summary":"Summary","macro_context":{},'
                '"key_themes":[],"stocks_to_investigate":[],"risk_factors":[]}'
            ),
            None,
        )

    monkeypatch.setitem(macro_synthesis_module.DEFAULT_CONFIG, "deep_think_llm_timeout", 600.0)
    monkeypatch.setitem(macro_synthesis_module.DEFAULT_CONFIG, "deep_think_llm_timeout_cap", 600.0)
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.invoke_with_timeout",
        _invoke_with_timeout,
    )
    monkeypatch.setattr(
        "tradingagents.agents.scanners.macro_synthesis.save_node_report",
        lambda *_args, **_kwargs: None,
    )

    agent = create_macro_synthesis(RunnableLambda(lambda _value: AIMessage(content="{}")))

    agent(
        {
            "scan_date": "2026-03-30",
            "run_id": "RUN1",
            "messages": [],
            "gatekeeper_universe_report": "NVDA AAPL MSFT",
            "geopolitical_report": "Geopolitical context",
            "market_movers_report": "Market movers context",
            "sector_performance_report": "Sector context",
            "factor_alignment_report": "Factor context",
            "drift_opportunities_report": "Drift context",
            "smart_money_report": "Smart money context",
            "industry_deep_dive_report": "Industry context",
        }
    )

    assert captured_timeout == 600.0


def test_macro_synthesis_fails_when_scan_date_missing():
    def _invoke(_prompt_value):
        return AIMessage(
            content='{"timeframe":"1 month","executive_summary":"Summary","macro_context":{},'
            '"key_themes":[],"stocks_to_investigate":[],"risk_factors":[]}'
        )

    agent = create_macro_synthesis(
        RunnableLambda(_invoke), max_scan_tickers=3, scan_horizon_days=30
    )

    with pytest.raises(RuntimeError) as exc:
        agent(
            {
                "run_id": "RUN1",
                "messages": [],
                "gatekeeper_universe_report": "NVDA AAPL MSFT",
                "geopolitical_report": "Geopolitical context",
                "market_movers_report": "Market movers context",
                "sector_performance_report": "Sector context",
                "factor_alignment_report": "Factor context",
                "drift_opportunities_report": "Drift context",
                "smart_money_report": "Smart money context",
                "industry_deep_dive_report": "Industry context",
            }
        )

    assert "missing required scan_date" in str(exc.value)
