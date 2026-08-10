"""Prove the price feed is live and NaN-free, per market. Run from the repo root.

    python scripts/check_live_data.py            # one pass
    python scripts/check_live_data.py --rounds 5 # five passes, 20s apart

Exists because a single healthy-looking pass cannot tell "working" from "got
lucky", and because Yahoo serves .NS daily bars with a NaN close for hours after
the NSE session closes — which silently broke position marking, equity
snapshots, the screener and the trend filter before it was caught.

During market hours prices should CHANGE between rounds; outside them they are
expected to be static, and only crypto ticks. Both outcomes are reported rather
than judged, so this is meaningful whenever it is run.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sqlite3
import time
from datetime import datetime

import pytz

SESSIONS = {
    "us": ("America/New_York", "09:30", "16:00"),
    "india": ("Asia/Kolkata", "09:15", "15:30"),
}


def market_open(market: str) -> bool | None:
    """True/False for equity markets, None for 24/7 (crypto)."""
    if market not in SESSIONS:
        return None
    tz, start, end = SESSIONS[market]
    now = datetime.now(pytz.timezone(tz))
    if now.weekday() >= 5:
        return False
    return start <= now.strftime("%H:%M") <= end


def usable(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--gap", type=int, default=20, help="seconds between rounds")
    args = parser.parse_args()

    import app.services.paper_broker as pb
    from app.services.books import BOOKS
    from app.services.core_holding import core_etf_for

    con = sqlite3.connect("data/assistant.db")
    watch = {r[0]: r[1] for r in con.execute("select symbol, market from watchlist")}
    for r in con.execute("select distinct symbol, market from positions"):
        watch.setdefault(r[0], r[1])
    con.close()
    for book in BOOKS:
        watch.setdefault(core_etf_for(book), "us")
    symbols = sorted(watch)

    print(f"{len(symbols)} symbols, {len(BOOKS)} books, {args.rounds} round(s)")
    for market, (tz, start, end) in SESSIONS.items():
        now = datetime.now(pytz.timezone(tz))
        print(f"  {market:<6} {now:%Y-%m-%d %H:%M %Z}  session {start}-{end}  "
              f"{'OPEN' if market_open(market) else 'CLOSED'}")
    print()

    history: list[dict[str, float | None]] = []
    problems: list[str] = []
    for rnd in range(1, args.rounds + 1):
        started = time.monotonic()
        pb._PRICE_CACHE.clear()
        pb._FX_CACHE.clear()
        prices = pb._batch_prices_sync(symbols)
        history.append(dict(prices))

        missing = [s for s in symbols if not usable(prices.get(s))]
        fx = await pb.usd_rate("INR")
        equities = {b: await pb.paper_equity_usd(b) for b in BOOKS}
        bad_equity = [b for b, e in equities.items() if not usable(e)]

        if missing:
            problems.append(f"round {rnd}: unpriced {missing}")
        if not usable(fx):
            problems.append(f"round {rnd}: FX INR unusable ({fx!r})")
        if bad_equity:
            problems.append(f"round {rnd}: equity unusable for {bad_equity}")

        print(f"  round {rnd}: {len(symbols) - len(missing)}/{len(symbols)} priced, "
              f"FX={fx if usable(fx) else 'FAIL'}, "
              f"{len(BOOKS) - len(bad_equity)}/{len(BOOKS)} books valued")
        if rnd < args.rounds:
            time.sleep(max(0, args.gap - (time.monotonic() - started)))

    if args.rounds > 1:
        print("\nmovement by market (open markets should move):")
        by_market: dict[str, list[int]] = {}
        for sym in symbols:
            vals = {h[sym] for h in history if usable(h.get(sym))}
            by_market.setdefault(watch.get(sym, "us"), []).append(len(vals) > 1)
        for market, flags in sorted(by_market.items()):
            state = market_open(market)
            label = "24/7" if state is None else ("OPEN" if state else "closed")
            moved = sum(flags)
            note = ""
            if state and not moved:
                note = "  <- market OPEN but nothing moved: STALE FEED"
                problems.append(f"{market} open but no price moved")
            print(f"  {market:<7} ({label:<6}) {moved}/{len(flags)} symbols moved{note}")

    print()
    if problems:
        print(f"{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("live data OK: every symbol priced, no NaN, every book valued")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
