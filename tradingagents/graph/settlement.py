"""Settling past decisions: once a decision's holding window has traded, score
it against its benchmark and record a reflection on it in the decision log."""

import logging
from datetime import datetime, timedelta

import pandas as pd

from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.yahoo.market import get_closes

logger = logging.getLogger(__name__)


def resolve_benchmark(ticker: str, config: dict) -> str:
    """Pick the benchmark ticker for alpha calculation against ``ticker``.

    ``config["benchmark_ticker"]`` overrides everything when set; otherwise
    the suffix map matches the ticker's exchange suffix (e.g. ``.T`` for
    Tokyo). US-listed tickers without a dotted suffix fall through to the
    empty-suffix entry (SPY by default). Unrecognised suffixes (including
    US tickers with dots like ``BRK.B``) also fall back to the empty-suffix
    entry, which is the right default because the alpha calculation works
    in USD.
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


# Calendar days of benchmark history fetched before the trade date, enough to
# span a weekend or a market holiday week.
_BENCHMARK_LOOKBACK_DAYS = 10


def _by_day(closes: pd.Series) -> pd.Series:
    """Closes indexed by each bar's own trading date, without its time zone.

    Yahoo stamps a crypto bar at midnight UTC and a US session in New York
    time; comparing two series by date needs the dates alone.
    """
    days = pd.DatetimeIndex(pd.to_datetime(closes.index).strftime("%Y-%m-%d"))
    return pd.Series(closes.to_numpy(), index=days)


def fetch_returns(
    ticker: str, trade_date: str, holding_days: int = 5,
    benchmark: str = "SPY",
) -> tuple[float | None, float | None, int | None, str | None]:
    """Fetch raw and alpha return for ticker over holding_days from trade_date.

    ``benchmark`` is the index used as the alpha baseline (resolved by the
    caller via ``resolve_benchmark``). Returns ``(raw_return, alpha_return,
    holding_days, resolution_date)`` — where ``resolution_date`` is the date
    of the last price bar needed, i.e. when the outcome became known (#1251) —
    or ``(None, None, None, None)`` when the outcome cannot be settled yet:
    the full holding window has not traded (#1169), or the symbol is delisted
    or unreachable.

    ``holding_days`` counts the instrument's own bars. The benchmark is
    measured over the same dates, from its last close on or before the entry
    bar to its last close on or before the exit bar, so an instrument on
    another calendar (a crypto pair trading every day against SPY) is not
    compared with a benchmark window that ends days later. When the benchmark
    did not trade on the exit day, the outcome waits for its next session and
    is dated then.
    """
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        # holding_days counts trading days, so ask for the calendar span they
        # occupy (about 7 for every 5) plus a week for holidays.
        end = start + timedelta(days=round(holding_days * 7 / 5) + 7)
        end_str = end.strftime("%Y-%m-%d")

        # Closes for the instrument the analysis priced (XAUUSD -> GC=F, #984).
        stock = _by_day(get_closes(ticker, trade_date, end_str))

        # Require the full holding window. A rerun before it has traded leaves
        # the entry pending to retry next run, rather than settling on a
        # premature partial return (#1169).
        if len(stock) <= holding_days:
            return None, None, None, None
        entry, exit_ = stock.index[0], stock.index[holding_days]

        # From before the trade date, so a benchmark closed on the entry day (a
        # weekend for a crypto pair) still has the close before it.
        bench_start = (start - timedelta(days=_BENCHMARK_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        bench = _by_day(get_closes(benchmark, bench_start, end_str)).dropna()
        if bench.empty or bench.index[0] > entry:
            return None, None, None, None
        # The benchmark must have traded through the exit day too; until then
        # its close for that day may still be missing. Its first session on or
        # after the exit confirms which close ends the window.
        confirmed_on = bench.index[bench.index >= exit_]
        if confirmed_on.empty:
            return None, None, None, None
        bench_entry, bench_exit = bench.asof(entry), bench.asof(exit_)

        raw = float((stock.iloc[holding_days] - stock.iloc[0]) / stock.iloc[0])
        bench_ret = float((bench_exit - bench_entry) / bench_entry)
        alpha = raw - bench_ret
        # The outcome is known once the last bar it waited for is out: the
        # benchmark session confirming the window, on or after the exit bar.
        # That date is the point-in-time cutoff for injecting the lesson
        # (#1251). It is the exit day unless the benchmark was closed then,
        # e.g. the Monday after a crypto pair's Saturday exit.
        resolution_date = confirmed_on[0].strftime("%Y-%m-%d")
        return raw, alpha, holding_days, resolution_date
    except Exception as e:
        logger.warning(
            "Could not resolve outcome for %s on %s vs %s (will retry next run): %s",
            ticker, trade_date, benchmark, e,
        )
        return None, None, None, None


def settle_pending(ticker: str, memory_log, reflector, config: dict) -> None:
    """Settle ``ticker``'s pending decisions whose holding window has traded.

    Fetches returns for each same-ticker pending entry, generates reflections,
    then writes all updates in a single atomic batch write to avoid redundant I/O.
    Skips entries whose price data is not yet available (too recent or delisted).

    Trade-off: only same-ticker entries are resolved per run.  Entries for
    other tickers accumulate until that ticker is run again.
    """
    pending = [e for e in memory_log.get_pending_entries() if e["ticker"] == ticker]
    if not pending:
        return

    benchmark = resolve_benchmark(ticker, config)
    updates = []
    for entry in pending:
        raw, alpha, days, resolution_date = fetch_returns(
            ticker, entry["date"], config.get("holding_period_days", 5),
            benchmark=benchmark,
        )
        if raw is None:
            continue  # price not available yet — try again next run
        try:
            reflection = reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
                benchmark_name=benchmark,
                holding_days=days,
            )
        except Exception as exc:
            # Reflection calls a provider, and this runs on the way into a
            # new run: a transient failure leaves the entry pending for the
            # next one rather than stopping the analysis that was asked for.
            logger.warning("Reflection failed for %s on %s: %s", ticker, entry["date"], exc)
            continue
        updates.append({
            "ticker": ticker,
            "trade_date": entry["date"],
            "raw_return": raw,
            "alpha_return": alpha,
            "holding_days": days,
            "reflection": reflection,
            "resolution_date": resolution_date,
        })

    if updates:
        memory_log.batch_update_with_outcomes(updates)
