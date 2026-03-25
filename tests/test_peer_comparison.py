from unittest.mock import patch

import pandas as pd


def _make_price_history(symbols: list[str]) -> pd.DataFrame:
    dates = pd.date_range("2025-09-01", periods=130, freq="B")
    payload = {}
    for index, symbol in enumerate(symbols, start=1):
        payload[symbol] = pd.Series(
            [100 * (1 + 0.001 * index) ** i for i in range(len(dates))],
            index=dates,
        )
    frame = pd.DataFrame(payload, index=dates)
    return pd.concat({"Close": frame}, axis=1)


def test_get_sector_peers_maps_known_sector_and_excludes_self():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"sector": "Technology"}
        from tradingagents.dataflows.peer_comparison import get_sector_peers

        sector_display, sector_key, peers = get_sector_peers("AAPL")

    assert sector_display == "Technology"
    assert sector_key == "technology"
    assert "AAPL" not in peers
    assert "MSFT" in peers


def test_compute_relative_performance_returns_ranked_markdown_table():
    with patch(
        "yfinance.download",
        return_value=_make_price_history(["AAPL", "MSFT", "NVDA", "XLK"]),
    ):
        from tradingagents.dataflows.peer_comparison import compute_relative_performance

        report = compute_relative_performance("AAPL", "technology", ["MSFT", "NVDA"])

    assert "| Symbol | Role |" in report
    assert "► TARGET" in report
    assert "ETF Benchmark" in report
    assert "Alpha vs Sector ETF" in report


def test_compute_relative_performance_ranks_against_peers_only():
    with patch(
        "yfinance.download",
        return_value=_make_price_history(["AAPL", "MSFT", "NVDA", "XLK"]),
    ):
        from tradingagents.dataflows.peer_comparison import compute_relative_performance

        report = compute_relative_performance(
            "AAPL",
            "technology",
            ["MSFT", "NVDA"],
        )

    assert "Peer rank (3M): 3/3" in report


def test_get_sector_relative_report_handles_unknown_sector_gracefully():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"sector": "Unknown Sector"}
        from tradingagents.dataflows.peer_comparison import get_sector_relative_report

        report = get_sector_relative_report("AAPL")

    assert "No ETF benchmark" in report


def test_get_sector_relative_report_handles_missing_columns_gracefully():
    dates = pd.date_range("2025-09-01", periods=130, freq="B")
    partial_history = pd.concat(
        {"Close": pd.DataFrame({"XLK": pd.Series(range(130), index=dates)}, index=dates)},
        axis=1,
    )

    with patch("yfinance.Ticker") as mock_ticker, patch(
        "yfinance.download",
        return_value=partial_history,
    ):
        mock_ticker.return_value.info = {"sector": "Technology"}
        from tradingagents.dataflows.peer_comparison import get_sector_relative_report

        report = get_sector_relative_report("AAPL")

    assert "| 1-Week |" in report
    assert "N/A" in report


def test_peer_comparison_uses_curr_date_as_end_date():
    calls = []

    def fake_download(symbols, **kwargs):
        calls.append(kwargs)
        return _make_price_history(["AAPL", "MSFT", "XLK"])

    with patch("yfinance.download", side_effect=fake_download):
        from tradingagents.dataflows.peer_comparison import compute_relative_performance

        compute_relative_performance(
            "AAPL",
            "technology",
            ["MSFT"],
            curr_date="2026-03-17",
        )

    assert calls[0]["end"].startswith("2026-03-18")
