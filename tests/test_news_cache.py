"""Tests for run-scoped news result caching across analysts."""

import time

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.interface import _news_result_cache, route_to_vendor
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.observability.provenance import CacheOrigin
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore


@pytest.fixture(autouse=True)
def _scoped_clean_cache(request):
    """Give legacy-style cache tests one explicit, isolated run scope."""
    _news_result_cache.clear()
    with interface.news_cache_scope(f"test:{request.node.nodeid}"):
        yield
    _news_result_cache.clear()


def _install_counting_news(monkeypatch):
    call_count = {"n": 0}

    def counting_news(*args, **kwargs):
        call_count["n"] += 1
        return f"news result #{call_count['n']}"

    monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {"tavily": counting_news},
    )
    return call_count


def _observer(tmp_path):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-18")
    store.create_run(snapshot)
    observer = DurableRunObserver(store, snapshot.run_id)
    turn = observer.start_turn(
        actor_id="analyst.news",
        graph_task_id="task-news",
        graph_step=1,
        turn_index=1,
    )
    return store, snapshot, observer, turn


class TestNewsResultCache:
    def test_same_call_returns_cached_result(self, monkeypatch):
        call_count = _install_counting_news(monkeypatch)

        r1 = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
        r2 = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")

        assert r1 == r2
        assert call_count["n"] == 1  # only one actual call

    def test_different_params_bypass_cache(self, monkeypatch):
        call_count = {"n": 0}

        def counting_news(*args, **kwargs):
            call_count["n"] += 1
            return f"news result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {"tavily": counting_news},
        )

        route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
        route_to_vendor("get_news", "AAPL", "2026-05-08", "2026-05-14")

        assert call_count["n"] == 2

    def test_non_news_methods_not_cached(self, monkeypatch):
        call_count = {"n": 0}

        def counting_stock(*args, **kwargs):
            call_count["n"] += 1
            return f"stock result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "yfinance")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_stock_data",
            {"yfinance": counting_stock},
        )

        route_to_vendor("get_stock_data", "AAPL", "2026-05-01", "2026-05-07")
        route_to_vendor("get_stock_data", "AAPL", "2026-05-01", "2026-05-07")

        assert call_count["n"] == 2  # no caching for non-news

    def test_global_news_also_cached(self, monkeypatch):
        call_count = {"n": 0}

        def counting_global(*args, **kwargs):
            call_count["n"] += 1
            return f"global #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_global_news",
            {"tavily": counting_global},
        )

        route_to_vendor("get_global_news", "2026-05-07")
        route_to_vendor("get_global_news", "2026-05-07")

        assert call_count["n"] == 1

    def test_cache_cleared_externally(self, monkeypatch):
        call_count = {"n": 0}

        def counting_news(*args, **kwargs):
            call_count["n"] += 1
            return f"result #{call_count['n']}"

        monkeypatch.setattr(interface, "get_vendor", lambda cat, method=None: "tavily")
        monkeypatch.setitem(
            interface.VENDOR_METHODS,
            "get_news",
            {"tavily": counting_news},
        )

        route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
        _news_result_cache.clear()
        route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")

        assert call_count["n"] == 2  # cache was cleared, so 2 calls

    def test_different_run_scopes_do_not_share_news_results(self, monkeypatch):
        call_count = _install_counting_news(monkeypatch)

        with interface.news_cache_scope("run-a"):
            first_a = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
            second_a = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")

        with interface.news_cache_scope("run-b"):
            first_b = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
            second_b = route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")

        assert first_a == second_a
        assert first_b == second_b
        assert first_a != first_b
        assert call_count["n"] == 2

    def test_scope_exit_removes_only_its_namespace(self, monkeypatch):
        _install_counting_news(monkeypatch)

        with interface.news_cache_scope("run-cleanup"):
            route_to_vendor("get_news", "AAPL", "2026-05-01", "2026-05-07")
            assert any(key[0] == "run-cleanup" for key in _news_result_cache)

        assert not any(key[0] == "run-cleanup" for key in _news_result_cache)

    def test_observed_cache_entry_without_provenance_is_forced_miss(
        self,
        monkeypatch,
        tmp_path,
    ):
        call_count = _install_counting_news(monkeypatch)
        _store, snapshot, observer, turn = _observer(tmp_path)

        with (
            interface.news_cache_scope(snapshot.run_id),
            observer.invocation_scope(
                turn,
                graph_task_id="task-news",
                graph_step=1,
            ),
        ):
            cache_key = interface._build_news_cache_key(
                "get_news",
                ("AAPL", "2026-05-01", "2026-05-07"),
                {},
            )
            assert cache_key is not None
            _news_result_cache[cache_key] = interface._NewsCacheEntry(
                result="untraceable stale result",
                origin=CacheOrigin((), (), time.monotonic()),
            )

            result = route_to_vendor(
                "get_news",
                "AAPL",
                "2026-05-01",
                "2026-05-07",
            )

        assert result != "untraceable stale result"
        assert call_count["n"] == 1
