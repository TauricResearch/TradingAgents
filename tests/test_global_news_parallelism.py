import importlib.util
import sys
import threading
import time
import types
from pathlib import Path


def _load_yfinance_news_module():
    fake_config = types.ModuleType("tradingagents.dataflows.config")
    fake_config.get_config = lambda: {
        "global_news_lookback_days": 7,
        "global_news_article_limit": 10,
        "global_news_query_concurrency": 3,
        "global_news_queries": ["fed", "gdp", "oil"],
    }
    sys.modules["tradingagents.dataflows.config"] = fake_config

    fake_stockstats_utils = types.ModuleType("tradingagents.dataflows.stockstats_utils")
    fake_stockstats_utils.yf_retry = lambda func: func()
    sys.modules["tradingagents.dataflows.stockstats_utils"] = fake_stockstats_utils

    module_path = (
        Path(__file__).resolve().parents[1]
        / "tradingagents"
        / "dataflows"
        / "yfinance_news.py"
    )
    spec = importlib.util.spec_from_file_location(
        "tradingagents.dataflows.yfinance_news_test_module",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_global_news_queries_run_with_parallel_fanout(monkeypatch):
    module = _load_yfinance_news_module()

    active = 0
    max_seen = 0
    lock = threading.Lock()

    class FakeSearch:
        def __init__(self, query, news_count, enable_fuzzy_query):
            nonlocal active, max_seen
            with lock:
                active += 1
                max_seen = max(max_seen, active)
            time.sleep(0.05)
            self.news = [
                {
                    "title": f"{query} headline",
                    "publisher": "Test",
                    "link": f"https://example.com/{query}",
                }
            ]
            with lock:
                active -= 1

    monkeypatch.setattr(module.yf, "Search", FakeSearch, raising=False)

    report = module.get_global_news_yfinance("2026-05-15")

    assert "fed headline" in report
    assert "gdp headline" in report
    assert "oil headline" in report
    assert max_seen >= 2
