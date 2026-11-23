"""Run the full agent graph over a watchlist and record each decision in the signal store.

Each ticker is one independent run on the analysis date: the graph decides, its
reports are saved, and the risk-based size and ATR stop for that date are computed
in Python from the same final closes the risk step uses. A ticker that fails is
recorded as failed with its reason and the sweep goes on. A ticker already recorded
for the date is skipped unless ``rerun`` is set, so an interrupted sweep resumes by
being run again.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from research_platform.config import platform_dir
from research_platform.store import Signal, SignalStore

logger = logging.getLogger(__name__)

# (ticker, date, asset_type, analysts, cfg) -> (rating, decision text, report folder or None)
Runner = Callable[[str, str, str, tuple[str, ...], dict], tuple[str, str, str | None]]
# (ticker, date, asset_type, cfg) -> RiskMetrics-like object, or raises
MetricsFn = Callable[[str, str, str, dict], object]


def parse_watchlist(text: str) -> list[str]:
    """Tickers from free text: one per line or comma separated; '#' starts a comment.

    Each is checked and made canonical like the CLI does (``2222.sr`` -> ``2222.SR``);
    a duplicate is kept once, in first-seen order.
    """
    from cli.prompts import parse_ticker

    tickers = []
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        for part in line.replace(";", ",").split(","):
            if part.strip():
                tickers.append(parse_ticker(part.strip()))
    return list(dict.fromkeys(tickers))


def load_watchlist(path: str | Path) -> list[str]:
    """A watchlist file: plain text (one ticker per line or comma separated) or a JSON list."""
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        return parse_watchlist("\n".join(str(t) for t in json.loads(text)))
    return parse_watchlist(text)


def asset_type_for(ticker: str) -> str:
    from cli.prompts import detect_asset_type

    return detect_asset_type(ticker).value


def graph_runner(ticker: str, date: str, asset_type: str, analysts: tuple[str, ...],
                 cfg: dict) -> tuple[str, str, str | None]:
    """The real run: build the graph, propagate, save the report tree."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(list(analysts), config=cfg)
    final_state, rating = graph.propagate(ticker, date, asset_type)
    report = graph.save_reports(final_state, ticker)
    return rating, final_state.get("final_trade_decision", ""), str(report)


def risk_metrics_fn(ticker: str, date: str, asset_type: str, cfg: dict):
    from tradingagents.dataflows.config import run_config
    from tradingagents.risk_metrics.service import compute_metrics

    with run_config(cfg):
        return compute_metrics(ticker, date, asset_type, cfg)


@dataclass
class SweepResult:
    date: str
    ran: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def default_store(cfg: dict) -> SignalStore:
    return SignalStore(platform_dir(cfg) / "platform.db")


def run_watchlist(
    tickers: list[str],
    date: str,
    cfg: dict,
    analysts: tuple[str, ...] = ("market", "news", "fundamentals", "valuation"),
    *,
    store: SignalStore | None = None,
    name: str | None = None,
    rerun: bool = False,
    runner: Runner = graph_runner,
    metrics: MetricsFn = risk_metrics_fn,
    progress: Callable[[int, int, str], None] | None = None,
) -> SweepResult:
    """Analyze every ticker on ``date`` and record the outcome of each in ``store``."""
    store = store or default_store(cfg)
    result = SweepResult(date=date)
    tickers = list(dict.fromkeys(tickers))
    for index, ticker in enumerate(tickers, 1):
        existing = store.get(ticker, date)
        if existing and existing.status == "done" and not rerun:
            result.skipped.append(ticker)
            continue
        if progress:
            progress(index, len(tickers), ticker)
        asset_type = asset_type_for(ticker)
        signal = Signal(
            ticker=ticker, date=date, asset_type=asset_type, analysts=",".join(analysts),
            llm_provider=cfg.get("llm_provider"), deep_model=cfg.get("deep_think_llm"),
            quick_model=cfg.get("quick_think_llm"), watchlist=name,
        )
        try:
            signal.rating, signal.decision, signal.report_path = runner(ticker, date, asset_type, analysts, cfg)
        except Exception as exc:  # noqa: BLE001 - one failed ticker must not end the sweep
            logger.warning("Watchlist run %s %s failed: %s", ticker, date, exc)
            signal.status, signal.error = "failed", f"{type(exc).__name__}: {exc}"
            store.save(signal)
            result.failed.append((ticker, signal.error))
            continue
        _attach_risk(signal, metrics, cfg)
        store.save(signal)
        result.ran.append(ticker)
    return result


def _attach_risk(signal: Signal, metrics: MetricsFn, cfg: dict) -> None:
    """Record the size and stop the risk step computed for this date; leave them empty if it cannot."""
    try:
        m = metrics(signal.ticker, signal.date, signal.asset_type, cfg)
    except Exception as exc:  # noqa: BLE001 - missing prices leave the sizing empty, never guessed
        note = f"risk metrics unavailable: {type(exc).__name__}: {exc}"
        signal.error = f"{signal.error}; {note}" if signal.error else note
        return
    signal.price = m.price
    signal.stop_long = m.stop_long
    signal.size_pct = m.sizing.size_pct
    signal.atr = m.atr
    signal.volatility = m.volatility
