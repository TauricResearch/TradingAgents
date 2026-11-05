"""Run the TradingAgents graph on one coin and count what the run cost.

Uses only the library's public surface (ADR 0001): a config built over
DEFAULT_CONFIG, ``TradingAgentsGraph`` and ``propagate``. No portfolio is
passed, so the rating stays a view (ADR 0003).
"""

from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult

from trader.settings import ANALYSTS, BENCHMARK, GLOBAL_NEWS_QUERIES, Settings
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)


def build_config(settings: Settings) -> dict:
    """A deep copy of DEFAULT_CONFIG, which already carries the .env LLM settings, with:

    results_dir, data_cache_dir and memory_log_path under settings.home (the
    trader's records stay apart from manual CLI runs, which settle against SPY);
    benchmark_ticker = BENCHMARK; checkpoint_enabled = True, so a retry resumes
    where the failed run stopped; global_news_queries = list(GLOBAL_NEWS_QUERIES).
    DEFAULT_CONFIG itself is left unchanged.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(
        # The library's own layout (logs, cache, memory), under the trader's home.
        results_dir=str(settings.home / "logs"),
        data_cache_dir=str(settings.home / "cache"),
        memory_log_path=str(settings.memory_log_path),
        benchmark_ticker=BENCHMARK,
        checkpoint_enabled=True,
        global_news_queries=list(GLOBAL_NEWS_QUERIES),
    )
    return config


class UsageRecorder(BaseCallbackHandler):
    """Counts input and output tokens per requested model across one run.

    Both model tiers share this handler, so each call is attributed to the model
    it asked for, recorded when the call starts, rather than to whatever name a
    relay reports back. Thread-safe, since the analysts run in parallel.

    ``tokens`` maps model name to (input_tokens, output_tokens); ``missing``
    counts calls that ended without usage metadata. ``reset`` clears both.
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._models: dict[UUID, str | None] = {}  # run_id -> requested model, while in flight
        self.tokens: dict[str, tuple[int, int]] = {}
        self.missing = 0

    def reset(self) -> None:
        with self._lock:
            self.tokens = {}
            self.missing = 0

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        # langchain_core puts the model the call asked for, a per-call override
        # included, in ls_model_name; the OpenAI, Anthropic and Google clients all set it.
        with self._lock:
            self._models[run_id] = (metadata or {}).get("ls_model_name")

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        usage = _usage(response)
        with self._lock:
            model = self._models.pop(run_id, None)
            if not usage:
                self.missing += 1
                return
            tokens_in, tokens_out = self.tokens.get(model, (0, 0))
            self.tokens[model] = (
                tokens_in + usage.get("input_tokens", 0),
                tokens_out + usage.get("output_tokens", 0),
            )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        # Dropped, not counted in ``missing``: the call failed rather than ended without usage.
        with self._lock:
            self._models.pop(run_id, None)


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
        self.recorder = UsageRecorder()
        config = build_config(settings)
        # Deep last, so its price wins when both tiers name the same model.
        self._prices = {
            config["quick_think_llm"]: settings.price_quick,
            config["deep_think_llm"]: settings.price_deep,
        }
        self.graph = graph_factory(
            selected_analysts=ANALYSTS, config=config, callbacks=[self.recorder]
        )

    def run(self, ticker: str, trade_date: str) -> ResearchResult:
        """``propagate(ticker, trade_date, asset_type="crypto")`` and its rating.

        Never raises: an exception becomes ``rating=None`` with ``error`` set, and
        the tokens the failed run spent are still counted and priced.
        """
        self.recorder.reset()
        rating = error = None
        try:
            _, rating = self.graph.propagate(ticker, trade_date, asset_type="crypto")
        except Exception as exc:
            logger.exception("research of %s for %s failed", ticker, trade_date)
            error = f"{type(exc).__name__}: {exc}"[:500]
        with self.recorder._lock:
            tokens, missing = dict(self.recorder.tokens), self.recorder.missing
        return ResearchResult(
            rating=rating,
            error=error,
            tokens_in=sum(i for i, _ in tokens.values()),
            tokens_out=sum(o for _, o in tokens.values()),
            cost_usd=None if missing else self._cost(tokens),
        )

    def _cost(self, tokens: dict[str, tuple[int, int]]) -> float | None:
        """USD for the tokens at the prices per million; None when a model has no price."""
        cost = 0.0
        for model, (tokens_in, tokens_out) in tokens.items():
            price = self._prices.get(model)
            if price is None:
                return None
            cost += (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000
        return cost


def _usage(response: LLMResult) -> dict | None:
    """The usage_metadata of the response's message, read as cli/stats_handler.py does."""
    try:
        message = response.generations[0][0].message
    except (IndexError, TypeError, AttributeError):
        return None
    return message.usage_metadata if isinstance(message, AIMessage) else None
