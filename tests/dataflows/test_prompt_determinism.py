from pathlib import Path


def test_yfinance_payloads_do_not_include_runtime_retrieval_timestamps():
    source = (
        Path(__file__).parents[2]
        / "tradingagents"
        / "dataflows"
        / "y_finance.py"
    ).read_text(encoding="utf-8")

    assert "Data retrieved on:" not in source
    assert "Retrieved on:" not in source
