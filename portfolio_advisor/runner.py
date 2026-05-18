from __future__ import annotations

import logging
from datetime import date
from typing import List, Tuple

from .config import Config

logger = logging.getLogger(__name__)

# Validate at import time so a broken TradingAgents upgrade fails loudly at
# startup rather than silently during a scheduled run.
try:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    _IMPORT_OK = True
except Exception as exc:
    logger.error("TradingAgents import failed — check installation: %s", exc)
    _IMPORT_OK = False


def _build_ta_config(cfg: Config) -> dict:
    ta_cfg = DEFAULT_CONFIG.copy()
    ta_cfg.update({
        "llm_provider": cfg.llm_provider,
        "deep_think_llm": cfg.deep_think_llm,
        "quick_think_llm": cfg.quick_think_llm,
        "max_debate_rounds": cfg.max_debate_rounds,
        "max_risk_discuss_rounds": cfg.max_risk_discuss_rounds,
        "results_dir": cfg.results_dir,
        "data_cache_dir": cfg.data_cache_dir,
    })
    return ta_cfg


def run_tickers(
    tickers: List[str],
    trade_date: date,
    cfg: Config,
    on_progress=None,
) -> List[Tuple[str, dict, str]]:
    """Run TradingAgents on each ticker.

    Returns a list of (ticker, final_state, signal) tuples.
    Tickers that fail are logged and skipped.

    on_progress(fraction: float, detail: str) is called before each ticker
    with fraction in [0, 1) and a human-readable detail string.
    """
    if not _IMPORT_OK:
        raise RuntimeError(
            "TradingAgents is not importable. Run compat_test.py to diagnose."
        )

    ta_cfg = _build_ta_config(cfg)
    graph = TradingAgentsGraph(
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config=ta_cfg,
    )

    date_str = trade_date.strftime("%Y-%m-%d")
    results: List[Tuple[str, dict, str]] = []
    total = len(tickers)

    for idx, ticker in enumerate(tickers):
        if on_progress and total:
            on_progress(idx / total, f"{ticker} ({idx + 1}/{total})")
        try:
            final_state, signal = graph.propagate(ticker, date_str)
            results.append((ticker, final_state, signal))
            logger.info("%s → %s", ticker, signal)
        except Exception as exc:
            logger.error("TradingAgents failed for %s: %s", ticker, exc)

    return results
