"""Run the TradingAgents graph on one coin and count what the run cost.

Uses only the library's public surface (ADR 0001): a config built over
DEFAULT_CONFIG, ``TradingAgentsGraph`` and ``propagate``. No portfolio is
passed, so the rating stays a view (ADR 0003).
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.callbacks import BaseCallbackHandler

from trader.settings import Settings
from tradingagents.graph.trading_graph import TradingAgentsGraph


def build_config(settings: Settings) -> dict:
    """A deep copy of DEFAULT_CONFIG, which already carries the .env LLM settings, with:

    results_dir, data_cache_dir and memory_log_path under settings.home (the
    trader's records stay apart from manual CLI runs, which settle against SPY);
    benchmark_ticker = BENCHMARK; checkpoint_enabled = True, so a retry resumes
    where the failed run stopped; global_news_queries = list(GLOBAL_NEWS_QUERIES).
    DEFAULT_CONFIG itself is left unchanged.
    """
    raise NotImplementedError


class UsageRecorder(BaseCallbackHandler):
    """Counts input and output tokens per requested model across one run.

    Both model tiers share this handler, so each call is attributed to the model
    it asked for, recorded when the call starts, rather than to whatever name a
    relay reports back. Thread-safe, since the analysts run in parallel.

    ``tokens`` maps model name to (input_tokens, output_tokens); ``missing``
    counts calls that ended without usage metadata. ``reset`` clears both.
    """

    def reset(self) -> None:
        raise NotImplementedError


@dataclass
class ResearchResult:
    rating: str | None      # 5-tier rating or "REVIEW"; None when the run raised
    error: str | None       # the exception, truncated, when the run raised
    tokens_in: int
    tokens_out: int
    cost_usd: float | None  # None when a model used has no price or a call had no usage


class Researcher:
    """Builds the graph once; ``run`` researches one coin for one trade date.

    The graph is ``graph_factory(selected_analysts=ANALYSTS, config=build_config(settings),
    callbacks=[recorder])``. Prices come from settings.price_deep for the config's
    deep_think_llm and settings.price_quick for its quick_think_llm.
    """

    def __init__(self, settings: Settings, graph_factory=TradingAgentsGraph):
        raise NotImplementedError

    def run(self, ticker: str, trade_date: str) -> ResearchResult:
        """``propagate(ticker, trade_date, asset_type="crypto")`` and its rating.

        Never raises: an exception becomes ``rating=None`` with ``error`` set, and
        the tokens the failed run spent are still counted and priced.
        """
        raise NotImplementedError
