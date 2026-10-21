"""CLI for forward-only stock paper trading. Absolutely no broker calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
import pytz

from .engine import Bar, Book

DEFAULT_PATH = Path.home() / ".tradingagents" / "paper" / "portfolio.json"
DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "COST"]


def last_safe_session() -> str:
    """Wait for the NYSE close, and FX daily candle close, before processing."""
    now = datetime.now(pytz.timezone("America/New_York"))
    safe = now.date() if now.time() >= time(17, 30) else now.date() - timedelta(days=1)
    return safe.isoformat()


@contextmanager
def exclusive(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"Paper book is locked: {lock}; check for another process") from exc
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def read_book(path: Path) -> Book:
    if not path.exists():
        raise FileNotFoundError(f"No paper account at {path}; run 'tradingagents-paper init'")
    return Book.load(json.loads(path.read_text(encoding="utf-8")))


def write_book(path: Path, book: Book):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".portfolio-", suffix=".tmp", dir=path.parent)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(asdict(book), out, indent=2, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fetch_daily(tickers: list[str], start: str, end: str, *,
                required: set[str] | None = None,
                errors: dict[str, str] | None = None) -> dict[str, dict[str, Bar]]:
    """Load actual vendor OHLC, isolating bad *unheld* candidates.

    Never invent, clamp, or use yesterday's bar for a missing close. Missing or
    malformed data for held/pending positions, SPY, or FX aborts the WHOLE run:
    otherwise stops, exposure and P&L could be wrong. Optional research names
    are skipped individually, leaving other candidates available for analysis.
    """
    import yfinance as yf

    must_have = {"SPY", "GBPUSD=X"} | (required or set())
    out: dict[str, dict[str, Bar]] = {}
    start_with_fx_buffer = (date.fromisoformat(start) - timedelta(days=7)).isoformat()
    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    for ticker in tickers:
        beginning = start_with_fx_buffer if ticker == "GBPUSD=X" else start
        try:
            hist = yf.Ticker(ticker).history(start=beginning, end=end_exclusive,
                                              interval="1d", auto_adjust=False)
            if hist is None or hist.empty:
                raise ValueError("vendor returned no daily candles")
            daily: dict[str, Bar] = {}
            bad_days: list[str] = []
            for stamp, row in hist.iterrows():
                day = stamp.date().isoformat()
                try:
                    bar = Bar(float(row["Open"]), float(row["High"]),
                              float(row["Low"]), float(row["Close"]))
                except (KeyError, ValueError, TypeError) as exc:
                    bad_days.append(f"{day} (unreadable OHLC: {type(exc).__name__})")
                    continue
                if not bar.valid():
                    bad_days.append(f"{day} (O={bar.open:.6g}, H={bar.high:.6g}, "
                                    f"L={bar.low:.6g}, C={bar.close:.6g})")
                    continue
                daily[day] = bar
            if not daily:
                raise ValueError("no valid daily OHLC candles returned; "
                                 f"examples: {', '.join(bad_days[:2])}")
            # If today is malformed, fail closed for this symbol even when
            # the vendor returned an older valid candle in the same response.
            if end in {d[:10] for d in bad_days}:
                raise ValueError(f"bad latest session candle on {end}")
            # Any missing day in a required instrument may matter for stops or
            # benchmark/FX history. Fail rather than silently dropping it.
            if ticker in must_have and bad_days:
                raise ValueError(f"malformed required candles: {', '.join(bad_days[:3])}")
            if bad_days:
                print(f"Note {ticker}: ignored {len(bad_days)} malformed older daily candle(s)",
                      file=sys.stderr)
            out[ticker] = daily
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            if ticker in must_have:
                raise ValueError(f"Required price feed for {ticker} failed: {detail}") from exc
            if errors is not None:
                errors[ticker] = detail
            print(f"SKIPPED {ticker}: market-data validation failed ({detail}); "
                  "no AI signal or paper order", file=sys.stderr)
    return out


def forex_for_day(fx_daily: dict[str, Bar], session: str) -> tuple[float, float]:
    eligible = [d for d in fx_daily if d <= session and
                (date.fromisoformat(session) - date.fromisoformat(d)).days <= 4]
    if not eligible:
        raise ValueError(f"No recent GBPUSD FX quote on {session}")
    fx = fx_daily[max(eligible)]
    return 1 / fx.open, 1 / fx.close


def forward_sync(book: Book, quotes: dict[str, dict[str, Bar]], last: str) -> Book:
    """Process every completed SPY session in chronological order; never skip stops."""
    if "SPY" not in quotes or "GBPUSD=X" not in quotes:
        raise ValueError("SPY and GBPUSD=X are mandatory")
    work = book
    sessions = sorted(d for d in quotes["SPY"] if book.started <= d <= last and
                      (not book.last_session or d > book.last_session))
    for session in sessions:
        open_fx, close_fx = forex_for_day(quotes["GBPUSD=X"], session)
        required = set(work.positions) | {o["ticker"] for o in work.orders}
        bars = {ticker: quotes[ticker][session] for ticker in required
                if ticker in quotes and session in quotes[ticker]}
        work = work.step(session, bars, open_fx, close_fx, quotes["SPY"][session].close)
    return work


def run_agents(book: Book, quotes: dict[str, dict[str, Bar]], tickers: list[str],
               path: Path, stop_pct: float) -> tuple[Book, int]:
    """Forward recommendations, not executable stock orders; only queued paper orders."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.portfolio import PortfolioContext, Position

    if book.last_session is None:
        return book, 0
    day = book.last_session
    cfg = DEFAULT_CONFIG.copy()
    cfg["results_dir"] = str(path.parent / "reports")
    cfg["memory_log_path"] = str(path.parent / "trading_memory.md")
    graph = TradingAgentsGraph(config=cfg)
    done = 0
    for ticker in tickers:
        if any(e["type"] == "AGENT_RATING" and e["date"] == day and
               e["ticker"] == ticker for e in book.events):
            continue  # idempotent, even when running the CLI again the same night
        bar = quotes.get(ticker, {}).get(day)
        if bar is None:
            book._event(day, "AGENT_ERROR", ticker=ticker, reason="missing_completed_stock_bar")
            print(f"SKIPPED {ticker}: no valid completed daily candle; no paper order",
                  file=sys.stderr)
            continue
        try:
            positions = [Position(ticker=p["ticker"], quantity=p["shares"],
                                  average_price=p["entry_usd"])
                         for p in book.positions.values()]
            # No cash field: GBP cash must not be misrepresented as USD cash.
            state, rating = graph.propagate(ticker, day,
                                            portfolio=PortfolioContext(positions=positions))
            if rating not in {"Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW"}:
                rating = "REVIEW"
            graph.save_reports(state, ticker)
        except Exception as exc:
            # Fail closed; do not turn an unavailable model/data source into a BUY.
            book._event(day, "AGENT_ERROR", ticker=ticker, reason=type(exc).__name__)
            print(f"Agent failed for {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        book._event(day, "AGENT_RATING", ticker=ticker, rating=rating, reference_close_usd=bar.close)
        book.submit_signal(ticker, rating, bar.close, day, stop_fraction=stop_pct / 100)
        print(f"{ticker}: {rating}")
        done += 1
    return book, done


def report(book: Book):
    history = book.equity_history[-1] if book.equity_history else None
    print(f"Paper account | started {book.started} | last session {book.last_session or 'none'}")
    print(f"Equity £{book.equity():,.2f} | cash £{book.cash_gbp:,.2f} | "
          f"positions {len(book.positions)} | pending {len(book.orders)} | "
          f"halted {'YES' if book.halted else 'no'}")
    if history:
        print(f"Drawdown {history['drawdown']:.2%} | SPY price-only benchmark "
              f"£{history['spy_benchmark_gbp']:,.2f}")
    for p in book.positions.values():
        print(f"  {p['ticker']}: {p['shares']} shares, stop ${p['stop_usd']:.2f}, "
              f"marked ${p['mark_usd']:.2f}")
    for t in book.completed[-5:]:
        print(f"  Closed {t['ticker']}: £{t['pnl_gbp']:+,.2f} ({t['reason']})")


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="tradingagents-paper",
                                     description="US stock paper trading; NO real brokerage connectivity")
    parser.add_argument("--state", type=Path, default=DEFAULT_PATH)
    cmds = parser.add_subparsers(dest="command", required=True)
    cmds.add_parser("init", help="Create a NEW £10k simulated GBP portfolio")
    cmds.add_parser("status", help="Show paper equity and positions")
    run = cmds.add_parser("run", help="Sync completed daily bars and query TradingAgents")
    run.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    run.add_argument("--stop-pct", type=float, default=8.0,
                     help="Initial stop distance from signal close (default 8%%)")
    args = parser.parse_args(argv)
    path = args.state.expanduser().resolve()
    try:
        if args.command == "status":
            report(read_book(path))
            return 0
        with exclusive(path):
            if args.command == "init":
                if path.exists():
                    raise FileExistsError(f"Refusing to overwrite existing paper ledger: {path}")
                book = Book.new(datetime.now(pytz.timezone("America/New_York")).date().isoformat())
                write_book(path, book)
                print(f"Created paper account at {path}. No real broker connection.")
                report(book)
                return 0
            book = read_book(path)
            if not 1 <= args.stop_pct <= 30:
                raise ValueError("--stop-pct must be between 1 and 30")
            tickers = list(dict.fromkeys(s.strip().upper() for s in args.tickers))
            if any(not t or not all(c.isalnum() or c in '.-' for c in t) for t in tickers):
                raise ValueError("Invalid ticker in watchlist")
            last = last_safe_session()
            if last < book.started:
                print("No completed US market day since initialization; run after 5:30pm New York.")
                return 0
            start = book.started if book.last_session is None else book.last_session
            symbols = list(dict.fromkeys(["SPY", "GBPUSD=X", *tickers,
                                          *book.positions, *(o["ticker"] for o in book.orders)]))
            data_errors: dict[str, str] = {}
            required = {"SPY", "GBPUSD=X", *book.positions,
                        *(o["ticker"] for o in book.orders)}
            quotes = fetch_daily(symbols, start, last,
                                 required=required, errors=data_errors)
            book = forward_sync(book, quotes, last)
            if book.last_session:
                for ticker, reason in data_errors.items():
                    book._event(book.last_session, "MARKET_DATA_ERROR", ticker=ticker,
                                reason=reason)
                book, done = run_agents(book, quotes, tickers, path, args.stop_pct)
            else:
                done = 0
            write_book(path, book)
            report(book)
            print(f"Completed {done} AI analyses. Queued orders fill no earlier than the next session.")
            return 0
    except (FileExistsError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
