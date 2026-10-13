"""Settling past decisions: once a decision's holding window has traded, score
it against its benchmark and record a reflection on it in the memory log."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.market import get_closes

logger = logging.getLogger(__name__)


def resolve_benchmark(ticker: str, config: dict) -> str:
    """Pick the benchmark ticker for alpha calculation against ``ticker``.

    ``config["benchmark_ticker"]`` overrides everything when set; otherwise
    the suffix map matches the ticker's exchange suffix (e.g. ``.T`` for
    Tokyo). US-listed tickers without a dotted suffix fall through to the
    empty-suffix entry (SPY by default). Unrecognised suffixes, including
    US tickers with dots like ``BRK.B``, also take the empty-suffix entry.
    Returns are compared as percentages, each in its own currency.
    """

    explicit = config.get("benchmark_ticker")
    if explicit:
        # Same alias mapping as the analyzed ticker; an unmapped alias finds
        # no prices, and the decision would stay pending for good.
        return normalize_symbol(explicit)
    benchmark_map = config.get("benchmark_map", {})
    ticker_upper = normalize_symbol(ticker)
    for suffix, benchmark in benchmark_map.items():
        if suffix and ticker_upper.endswith(suffix.upper()):
            return benchmark
    return benchmark_map.get("", "SPY")


def _by_day(closes):
    """Closes keyed by the calendar day of their bar, missing closes dropped.

    Yahoo stamps a daily bar at midnight in its market's time zone (UTC for a
    coin, New York for SPY), so two series meet on their dates, not their
    instants. A missing or non-positive close is no price at all, not a bar to
    score on.
    """
    closes = closes[closes > 0]
    if getattr(closes.index, "tz", None) is not None:
        closes = closes.tz_localize(None)
    return closes


def fetch_returns(
    ticker: str, trade_date: str, holding_days: int = 5,
    benchmark: str = "SPY",
) -> tuple[float | None, float | None, int | None, str | None]:
    """Fetch raw and alpha return for ticker over holding_days from trade_date.

    ``benchmark`` is the index used as the alpha baseline (resolved by the
    caller via ``resolve_benchmark``). Returns ``(raw_return, alpha_return,
    holding_days, resolution_date)`` — where ``resolution_date`` is the date
    of the last price bar used, i.e. when the outcome became known (#1251) —
    or ``(None, None, None, None)`` when the full holding window has not traded
    yet (#1169). A failure to get or read the prices is raised, for the caller
    to report.
    """
    start = datetime.strptime(trade_date, "%Y-%m-%d")
    # holding_days counts trading days, so ask for the calendar span they
    # occupy (about 7 for every 5) plus a week for holidays.
    end = start + timedelta(days=round(holding_days * 7 / 5) + 7)
    end_str = end.strftime("%Y-%m-%d")

    # Closes for the instrument the analysis priced (XAUUSD -> GC=F, #984).
    stock = _by_day(get_closes(ticker, trade_date, end_str))
    # From a week earlier, so the benchmark has a close on or before entry.
    bench_start = (start - timedelta(days=7)).strftime("%Y-%m-%d")
    bench = _by_day(get_closes(benchmark, bench_start, end_str))

    # Require the full holding window to have traded. A rerun before it has
    # leaves the entry pending to retry next run, rather than settling on a
    # premature partial return (#1169).
    if len(stock) <= holding_days:
        return None, None, None, None
    entry, exit_ = stock.index[0], stock.index[holding_days]
    # The window is the stock's own sessions; the benchmark is valued at its
    # last close by each end, so both returns span the same dates even when
    # the calendars differ (a coin trades at weekends, an index does not).
    # It must have traded through the exit, or its close there may yet move.
    if bench.empty or bench.index[0] > entry or bench.index[-1] < exit_:
        return None, None, None, None

    raw = float((stock.iloc[holding_days] - stock.iloc[0]) / stock.iloc[0])
    bench_entry, bench_exit = bench.asof(entry), bench.asof(exit_)
    bench_ret = float((bench_exit - bench_entry) / bench_entry)
    alpha = raw - bench_ret
    # Every close used is known by the exit: the point-in-time cutoff for
    # injecting the lesson (#1251).
    resolution_date = exit_.strftime("%Y-%m-%d")
    return raw, alpha, holding_days, resolution_date


@dataclass
class Settlement:
    """What a settlement pass did: the decisions it settled and those it could not."""

    settled: list[tuple[str, str]] = field(default_factory=list)        # (ticker, date)
    failed: list[tuple[str, str, str]] = field(default_factory=list)    # (ticker, date, reason)


def settle_pending(ticker: str, memory_log, reflector, config: dict, wait: bool = True) -> Settlement:
    """Settle ``ticker``'s pending decisions whose holding window has traded.

    One pass at a time per log (``memory_log.settling()``), so runs sharing a log
    never pay for the same reflection twice. Each outcome is written as soon as
    its reflection is done, so an interrupted pass keeps what it finished.
    Entries whose window has not traded yet are skipped; an entry whose prices
    or reflection could not be had stays pending and is reported as failed.
    With ``wait=False`` a pass already running elsewhere is left to do the work.
    """
    result = Settlement()
    with memory_log.settling(wait=wait) as held:
        if not held:
            return result
        pending = [e for e in memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return result
        benchmark = resolve_benchmark(ticker, config)
        for entry in pending:
            try:
                raw, alpha, days, resolution_date = fetch_returns(
                    ticker, entry["date"], config.get("holding_period_days", 5), benchmark=benchmark,
                )
            except Exception as exc:
                logger.warning("Prices for settling %s on %s were unavailable: %s", ticker, entry["date"], exc)
                result.failed.append((ticker, entry["date"], f"prices unavailable: {exc}"))
                continue
            if raw is None:
                continue  # the holding window has not traded yet: try again next run
            try:
                reflection = reflector.reflect_on_final_decision(
                    final_decision=entry.get("decision", ""),
                    raw_return=raw,
                    alpha_return=alpha,
                    benchmark_name=benchmark,
                    holding_days=days,
                )
            except Exception as exc:
                # Reflection calls a provider: a transient failure leaves the entry
                # pending for the next pass rather than stopping the analysis.
                logger.warning("Reflection failed for %s on %s: %s", ticker, entry["date"], exc)
                result.failed.append((ticker, entry["date"], f"reflection failed: {exc}"))
                continue
            if memory_log.update_with_outcome(ticker, entry["date"], raw, alpha, days, reflection,
                                              resolution_date=resolution_date):
                result.settled.append((ticker, entry["date"]))
    return result


def settle_all_pending(memory_log, reflector, config: dict, wait: bool = True) -> Settlement:
    """Settle every ticker's pending decisions whose holding window has traded (#1445).

    A run settles its own ticker; a ticker no longer analysed would otherwise
    keep its decisions pending, and their lessons out of later runs.
    """
    result = Settlement()
    for ticker in dict.fromkeys(e["ticker"] for e in memory_log.get_pending_entries()):
        done = settle_pending(ticker, memory_log, reflector, config, wait=wait)
        result.settled.extend(done.settled)
        result.failed.extend(done.failed)
    return result
