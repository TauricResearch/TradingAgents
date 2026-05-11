from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.progress import capture_progress


def test_news_route_emits_start_and_success_progress(monkeypatch):
    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "tavily,yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "tavily": lambda *args, **kwargs: {
                "source": "tavily",
                "items": [
                    {
                        "title": "Company update",
                        "url": "https://example.com/news",
                        "content": "Summary.",
                    }
                ],
            },
            "yfinance": lambda *args, **kwargs: "No news found for 002636.SZ",
        },
    )
    set_config({"news_curator_max_items": 10})

    with capture_progress() as events:
        result = interface.route_to_vendor("get_news", "002636.SZ", "2026-04-28", "2026-05-01")

    assert "Curated News Package" in result
    messages = [event.message for event in events]
    assert any("数据调用开始：get_news | tavily | 002636.SZ | 2026-04-28~2026-05-01" in msg for msg in messages)
    assert any("数据调用成功：get_news | tavily | 返回 1 条新闻" in msg for msg in messages)
    assert any("数据调用失败：get_news | yfinance | No news found for 002636.SZ" in msg for msg in messages)


def test_a_share_supplement_emits_progress_without_secret_leak(monkeypatch):
    calls = []
    yfinance_data = (
        "# Stock data for 002636.SZ from 2026-01-01 to 2026-01-31\n"
        "# Total records: 1\n\n"
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-02,10,11,9,10.5,1000\n"
    )

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance,tushare")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": lambda *args, **kwargs: calls.append("yfinance") or yfinance_data,
            "tushare": lambda *args, **kwargs: calls.append("tushare") or "# Source: tushare\nDate,Open\n2026-01-02,10\n",
        },
    )
    set_config({"a_share_yfinance_min_rows": 3, "a_share_yfinance_min_coverage_ratio": 0.6})

    with capture_progress() as events:
        result = interface.route_to_vendor("get_stock_data", "002636.SZ", "2026-01-01", "2026-01-31")

    assert "Supplemental source: tushare" in result
    assert calls == ["yfinance", "tushare"]
    messages = [event.message for event in events]
    assert any("数据调用开始：get_stock_data | yfinance | 002636.SZ | 2026-01-01~2026-01-31" in msg for msg in messages)
    assert any("数据源补充：get_stock_data | yfinance 覆盖不足，继续尝试 tushare" in msg for msg in messages)
    assert any("数据调用成功：get_stock_data | tushare" in msg for msg in messages)
    assert "secret" not in "\n".join(messages).lower()
