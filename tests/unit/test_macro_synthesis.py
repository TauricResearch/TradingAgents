from tradingagents.agents.scanners.macro_synthesis import (
    _build_candidate_rankings,
    _extract_rankable_tickers,
    _format_horizon_label,
    _parse_gatekeeper_rows,
    _repair_macro_summary,
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
