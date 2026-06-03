import inspect

import tradingagents.dataflows.y_finance as yfmod


def test_yfinance_payloads_do_not_include_runtime_retrieval_timestamps():
    source = inspect.getsource(yfmod)

    assert "Data retrieved on:" not in source
    assert "Retrieved on:" not in source
