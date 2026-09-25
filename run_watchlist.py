"""Run TradingAgents over a watchlist for the latest completed US trading session.

    python run_watchlist.py                          # every ticker in watchlist.txt
    python run_watchlist.py --tickers NVDA,AAPL      # a subset
    python run_watchlist.py --date 2026-09-24        # a specific session
    python run_watchlist.py --analysts market,news   # fewer analysts, fewer LLM calls

Each ticker is a full multi-agent run. A ticker already in the decision log for
the date is skipped, so an interrupted sweep continues where it stopped when run
again. Stocks only: crypto needs a different analyst set.
"""

import argparse
import csv
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tradingagents.agents.rating import RATINGS_5_TIER
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

WATCHLIST = Path(__file__).with_name("watchlist.txt")
ANALYSTS = "market,social,news,fundamentals"

MARKET_TZ = ZoneInfo("America/New_York")
# Yahoo publishes the final daily bar shortly after the 16:00 close. Before then
# today's candle is partial, and its Close is not a closing price.
SESSION_FINAL = time(16, 30)


def last_completed_session(now: datetime | None = None) -> str:
    """Date of the most recent US session whose daily bar is final, in New York time.

    Exchange holidays are not skipped. A holiday date still runs: the data tools
    serve the last bar before it.
    """
    now = now or datetime.now(MARKET_TZ)
    day = now.date() if now.time() >= SESSION_FINAL else now.date() - timedelta(days=1)
    while day.weekday() >= 5:  # Saturday, Sunday
        day -= timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def parse_date(value: str) -> str:
    """A YYYY-MM-DD date no later than today, as the graph requires.

    Checked once here, so a bad --date is one error instead of one per ticker.
    """
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        day = None
    if day is None or day.strftime("%Y-%m-%d") != value:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}")
    if day > date.today():
        raise argparse.ArgumentTypeError(f"{value} is in the future")
    return value


def read_watchlist(path: Path) -> list[str]:
    """Tickers from a file of one per line, ignoring blanks and # comments."""
    tickers = []
    for line in path.read_text(encoding="utf-8").splitlines():
        ticker = line.split("#", 1)[0].strip().upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--date", type=parse_date,
        help="analysis date, YYYY-MM-DD (default: last completed US session)",
    )
    parser.add_argument("--tickers", help="comma-separated tickers to run instead of watchlist.txt")
    parser.add_argument("--analysts", default=ANALYSTS, help=f"comma-separated (default: {ANALYSTS})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    trade_date = args.date or last_completed_session()
    tickers = (
        [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        if args.tickers
        else read_watchlist(WATCHLIST)
    )
    analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]

    config = DEFAULT_CONFIG.copy()
    ta = TradingAgentsGraph(analysts, config=config)
    logged = {(e["ticker"], e["date"]): e["rating"] for e in ta.memory_log.load_entries()}

    print(f"Analyzing {len(tickers)} tickers for {trade_date} with {', '.join(analysts)}", flush=True)
    results = []
    for i, ticker in enumerate(tickers, 1):
        if (ticker, trade_date) in logged:
            print(f"[{i}/{len(tickers)}] {ticker}: already decided, skipping", flush=True)
            results.append((ticker, logged[ticker, trade_date], "from decision log"))
            continue
        print(f"[{i}/{len(tickers)}] {ticker} ...", flush=True)
        try:
            final_state, rating = ta.propagate(ticker, trade_date)
            report_dir = ta.save_reports(final_state, ticker)
            results.append((ticker, rating, str(report_dir)))
            print(f"[{i}/{len(tickers)}] {ticker}: {rating}", flush=True)
        except Exception as exc:  # one failing ticker must not end the sweep
            results.append((ticker, "ERROR", str(exc)))
            print(f"[{i}/{len(tickers)}] {ticker}: failed: {exc}", flush=True)

    # Most bullish first; REVIEW and ERROR last.
    order = {r: n for n, r in enumerate(RATINGS_5_TIER)}
    results.sort(key=lambda r: order.get(r[1], len(order)))

    out_dir = Path(config["results_dir"]) / "watchlist"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / f"{trade_date}.csv"
    with open(summary, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "rating", "report"])
        writer.writerows(results)

    print(f"\nRatings for {trade_date}:")
    for ticker, rating, _ in results:
        print(f"  {ticker:10} {rating}")
    print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()
