import pandas as pd


def _make_income_csv(n_quarters: int = 8) -> str:
    dates = pd.date_range("2024-01-01", periods=n_quarters, freq="QS")
    revenues = [10_000_000_000 * (1.05**i) for i in range(n_quarters)]
    gross_profit = [revenue * 0.40 for revenue in revenues]
    operating_income = [revenue * 0.20 for revenue in revenues]
    net_income = [revenue * 0.15 for revenue in revenues]
    df = pd.DataFrame(
        {
            "Total Revenue": revenues,
            "Gross Profit": gross_profit,
            "Operating Income": operating_income,
            "Net Income": net_income,
        },
        index=dates,
    )
    return df.to_csv()


def _make_balance_csv(n_quarters: int = 8) -> str:
    dates = pd.date_range("2024-01-01", periods=n_quarters, freq="QS")
    df = pd.DataFrame(
        {
            "Total Assets": [50_000_000_000] * n_quarters,
            "Total Debt": [10_000_000_000] * n_quarters,
            "Stockholders Equity": [20_000_000_000] * n_quarters,
        },
        index=dates,
    )
    return df.to_csv()


def _make_cashflow_csv(n_quarters: int = 8) -> str:
    dates = pd.date_range("2024-01-01", periods=n_quarters, freq="QS")
    df = pd.DataFrame(
        {
            "Free Cash Flow": [2_000_000_000] * n_quarters,
            "Operating Cash Flow": [3_000_000_000] * n_quarters,
        },
        index=dates,
    )
    return df.to_csv()


def test_compute_ttm_metrics_sums_last_four_quarters():
    from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics

    metrics = compute_ttm_metrics(
        _make_income_csv(),
        _make_balance_csv(),
        _make_cashflow_csv(),
    )

    expected = sum(10_000_000_000 * (1.05**i) for i in range(4, 8))
    assert metrics["quarters_available"] == 8
    assert metrics["ttm"]["revenue"] == expected


def test_compute_ttm_metrics_exposes_qoq_and_yoy_revenue_trends():
    from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics

    metrics = compute_ttm_metrics(
        _make_income_csv(),
        _make_balance_csv(),
        _make_cashflow_csv(),
    )

    assert metrics["trends"]["revenue_qoq_pct"] is not None
    assert metrics["trends"]["revenue_yoy_pct"] is not None
    assert metrics["trends"]["gross_margin_direction"] == "stable"


def test_compute_ttm_metrics_handles_empty_income_csv():
    from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics

    metrics = compute_ttm_metrics("", _make_balance_csv(), _make_cashflow_csv())

    assert metrics["quarters_available"] == 0
    assert "income statement parse failed" in metrics["metadata"]["parse_errors"]


def test_compute_ttm_metrics_preserves_zero_values():
    from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics

    dates = pd.date_range("2024-01-01", periods=4, freq="QS")
    income_csv = pd.DataFrame(
        {
            "Total Revenue": [10_000_000_000] * 4,
            "Gross Profit": [0] * 4,
            "Operating Income": [0] * 4,
            "Net Income": [0] * 4,
        },
        index=dates,
    ).to_csv()
    balance_csv = pd.DataFrame(
        {
            "Total Assets": [50_000_000_000] * 4,
            "Total Debt": [0] * 4,
            "Stockholders Equity": [20_000_000_000] * 4,
        },
        index=dates,
    ).to_csv()
    cashflow_csv = pd.DataFrame(
        {
            "Free Cash Flow": [0] * 4,
            "Operating Cash Flow": [0] * 4,
        },
        index=dates,
    ).to_csv()

    metrics = compute_ttm_metrics(income_csv, balance_csv, cashflow_csv)

    assert metrics["ttm"]["gross_margin_pct"] == 0.0
    assert metrics["ttm"]["net_margin_pct"] == 0.0
    assert metrics["ttm"]["debt_to_equity"] == 0.0


def test_format_ttm_report_includes_ttm_and_quarterly_sections():
    from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics, format_ttm_report

    metrics = compute_ttm_metrics(
        _make_income_csv(),
        _make_balance_csv(),
        _make_cashflow_csv(),
    )
    report = format_ttm_report(metrics, "AAPL")

    assert "Trailing Twelve Months" in report
    assert "Trend Signals" in report
    assert "Quarter" in report
