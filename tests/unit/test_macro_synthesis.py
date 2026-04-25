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
