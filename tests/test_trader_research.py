import copy
import threading

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from trader.research import Researcher, ResearchResult, UsageRecorder, build_config
from trader.settings import ANALYSTS, BENCHMARK, GLOBAL_NEWS_QUERIES, Settings
from tradingagents.default_config import DEFAULT_CONFIG

DEEP, QUICK = DEFAULT_CONFIG["deep_think_llm"], DEFAULT_CONFIG["quick_think_llm"]


class FakeModel(GenericFakeChatModel):
    """GenericFakeChatModel with a model name, which langchain_core passes to
    callbacks as ls_model_name, as it does for the real clients."""

    model: str


def _replies(*items):
    """Yield the scripted replies in turn; an exception among them is raised instead."""
    for item in items:
        if isinstance(item, BaseException):
            raise item
        yield item


def _with_usage(tokens_in, tokens_out):
    return AIMessage(
        "ok",
        usage_metadata={
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        },
    )


class FakeGraph:
    """Stands in for graph_factory and the graph it builds. ``propagate`` sends each
    scripted (tier, reply) through a fake chat model named as the config names that
    tier, carrying the callbacks the graph was given, as the real graph's clients do."""

    def __init__(self, replies=(), signal="Overweight"):
        self.replies = list(replies)
        self.signal = signal
        self.built_with = None
        self.calls = []

    def __call__(self, **kwargs):
        self.built_with = kwargs
        return self

    def propagate(self, company_name, trade_date, asset_type="stock", portfolio=None):
        self.calls.append((company_name, trade_date, asset_type, portfolio))
        config, callbacks = self.built_with["config"], self.built_with["callbacks"]
        for tier, reply in self.replies:
            model = config[f"{tier}_think_llm"]
            FakeModel(model=model, messages=_replies(reply), callbacks=callbacks).invoke("go")
        return {}, self.signal


def _settings(tmp_path, deep=(15.0, 75.0), quick=(3.0, 15.0)):
    return Settings(home=tmp_path, price_deep=deep, price_quick=quick)


def test_config_puts_files_under_home_and_leaves_defaults_alone(tmp_path):
    before = copy.deepcopy(DEFAULT_CONFIG)
    config = build_config(_settings(tmp_path))
    assert config == {
        **before,
        "results_dir": str(tmp_path / "logs"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
        "benchmark_ticker": BENCHMARK,
        "checkpoint_enabled": True,
        "global_news_queries": list(GLOBAL_NEWS_QUERIES),
    }
    assert before == DEFAULT_CONFIG
    assert config["data_vendors"] is not DEFAULT_CONFIG["data_vendors"]


def test_graph_is_built_with_the_analysts_config_and_recorder(tmp_path):
    graph = FakeGraph()
    researcher = Researcher(_settings(tmp_path), graph_factory=graph)
    assert graph.built_with == {
        "selected_analysts": ANALYSTS,
        "config": build_config(_settings(tmp_path)),
        "callbacks": [researcher.recorder],
    }


def test_runs_the_crypto_pipeline_without_a_portfolio(tmp_path):
    graph = FakeGraph(signal="Underweight")
    result = Researcher(_settings(tmp_path), graph_factory=graph).run("SOL-USD", "2026-01-04")
    assert graph.calls == [("SOL-USD", "2026-01-04", "crypto", None)]
    assert result == ResearchResult(
        rating="Underweight", error=None, tokens_in=0, tokens_out=0, cost_usd=0.0
    )


def test_tokens_are_counted_per_model_and_priced_at_its_tier(tmp_path):
    assert DEEP != QUICK
    graph = FakeGraph([
        ("quick", _with_usage(1000, 100)),
        ("deep", _with_usage(2000, 500)),
        ("quick", _with_usage(3000, 200)),
    ])
    researcher = Researcher(_settings(tmp_path), graph_factory=graph)
    result = researcher.run("BTC-USD", "2026-01-04")
    assert researcher.recorder.tokens == {QUICK: (4000, 300), DEEP: (2000, 500)}
    assert (result.tokens_in, result.tokens_out) == (6000, 800)
    expected = (4000 * 3.0 + 300 * 15.0 + 2000 * 15.0 + 500 * 75.0) / 1_000_000
    assert result.cost_usd == pytest.approx(expected)


def test_overlapping_calls_are_attributed_to_the_model_each_asked_for():
    # The analysts call the model from parallel threads: both calls start before either ends.
    recorder = UsageRecorder()
    both_started = threading.Barrier(2, timeout=5)

    def after_both_start(reply):
        both_started.wait()
        yield reply

    def call(model, reply):
        FakeModel(model=model, messages=after_both_start(reply), callbacks=[recorder]).invoke("go")

    threads = [
        threading.Thread(target=call, args=("model-a", _with_usage(10, 1))),
        threading.Thread(target=call, args=("model-b", _with_usage(20, 2))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert recorder.tokens == {"model-a": (10, 1), "model-b": (20, 2)}


def test_deep_price_wins_when_both_tiers_name_one_model(tmp_path, monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "quick_think_llm", DEEP)
    graph = FakeGraph([("quick", _with_usage(1_000_000, 1_000_000))])
    settings = _settings(tmp_path, deep=(1.0, 2.0), quick=(100.0, 200.0))
    assert Researcher(settings, graph_factory=graph).run("BTC-USD", "2026-01-04").cost_usd == 3.0


def test_cost_is_unknown_once_a_model_without_a_price_is_used(tmp_path):
    graph = FakeGraph([("deep", _with_usage(1000, 100))])
    researcher = Researcher(_settings(tmp_path, quick=None), graph_factory=graph)
    assert researcher.run("BTC-USD", "2026-01-04").cost_usd == pytest.approx(0.0225)
    graph.replies.append(("quick", _with_usage(500, 50)))
    result = researcher.run("BTC-USD", "2026-01-04")
    assert (result.tokens_in, result.tokens_out, result.cost_usd) == (1500, 150, None)


def test_cost_is_unknown_when_a_call_reports_no_usage(tmp_path):
    graph = FakeGraph([("deep", _with_usage(1000, 100)), ("quick", AIMessage("no usage"))])
    researcher = Researcher(_settings(tmp_path), graph_factory=graph)
    result = researcher.run("BTC-USD", "2026-01-04")
    assert researcher.recorder.missing == 1
    assert (result.tokens_in, result.tokens_out, result.cost_usd) == (1000, 100, None)


def test_a_failed_run_has_no_rating_and_keeps_the_tokens_it_spent(tmp_path):
    graph = FakeGraph([
        ("quick", _with_usage(1000, 200)),
        ("deep", TimeoutError("x" * 1000)),
    ])
    researcher = Researcher(_settings(tmp_path), graph_factory=graph)
    result = researcher.run("ETH-USD", "2026-01-04")
    assert result.rating is None
    assert len(result.error) == 500
    assert result.error.startswith("TimeoutError: xxx")
    # The failed call is dropped, not counted as one that ended without usage.
    assert researcher.recorder.missing == 0
    assert (result.tokens_in, result.tokens_out) == (1000, 200)
    assert result.cost_usd == pytest.approx((1000 * 3.0 + 200 * 15.0) / 1_000_000)


def test_each_run_counts_only_its_own_calls(tmp_path):
    graph = FakeGraph([("quick", _with_usage(1000, 100)), ("deep", AIMessage("no usage"))])
    researcher = Researcher(_settings(tmp_path), graph_factory=graph)
    assert researcher.run("BTC-USD", "2026-01-04").cost_usd is None
    graph.replies = [("deep", _with_usage(2000, 300))]
    result = researcher.run("ETH-USD", "2026-01-04")
    assert researcher.recorder.tokens == {DEEP: (2000, 300)}
    assert researcher.recorder.missing == 0
    assert (result.tokens_in, result.tokens_out) == (2000, 300)
    assert result.cost_usd == pytest.approx((2000 * 15.0 + 300 * 75.0) / 1_000_000)


def test_the_real_graph_builds_offline_and_makes_the_trader_dirs(tmp_path):
    # Researcher creates no directories: TradingAgentsGraph makes the results and
    # cache dirs, and its TradingMemoryLog the memory log's parent.
    Researcher(_settings(tmp_path))
    assert all((tmp_path / name).is_dir() for name in ("logs", "cache", "memory"))


def test_the_result_carries_the_final_trade_decision(tmp_path):
    graph = FakeGraph()
    graph.propagate = lambda *args, **kwargs: ({"final_trade_decision": "Rating: Buy"}, "Buy")
    result = Researcher(_settings(tmp_path), graph_factory=graph).run("BTC-USD", "2026-01-04")
    assert (result.rating, result.decision) == ("Buy", "Rating: Buy")


def test_a_rerun_downloads_its_data_anew_into_an_emptied_cache_of_its_own(tmp_path):
    first = tmp_path / "cache" / "BTC-USD-data.csv"
    stale = tmp_path / "cache" / "rerun" / "BTC-USD-data.csv"
    for path in (first, stale):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("the candles up to the day before")
    graph = FakeGraph()
    Researcher(_settings(tmp_path), graph_factory=graph, fresh_data=True)
    assert graph.built_with["config"] == {
        **build_config(_settings(tmp_path)), "data_cache_dir": str(tmp_path / "cache" / "rerun"),
    }
    assert first.exists() and not stale.exists()
