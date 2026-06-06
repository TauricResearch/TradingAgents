"""Minimal CLI: run one live alpha cycle.

    python -m tradingagents.cli AAPL MSFT --start 2024-01-01

Builds the live dependencies (yfinance fetcher + DeepSeek brain via OpenRouter)
and runs a single cycle on the paper broker. Requires the provider keys in .env
(TRADINGAGENTS_LLM_PROVIDER=openrouter + the model + OPENROUTER_API_KEY).
"""

from __future__ import annotations

import argparse

from .app import run_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one trading-agent cycle.")
    parser.add_argument("symbols", nargs="+", help="Ticker symbols, e.g. AAPL MSFT")
    parser.add_argument("--start", default="2024-01-01", help="History start (yyyy-mm-dd)")
    parser.add_argument("--end", default=None, help="History end (yyyy-mm-dd, default today)")
    parser.add_argument("--db", default=None, help="Database URL (default local SQLite)")
    parser.add_argument("--base-risk", type=float, default=0.01, help="Base risk fraction")
    parser.add_argument("--loop", type=float, default=None, metavar="SECONDS",
                        help="Run continuously every SECONDS (autonomous loop)")
    args = parser.parse_args(argv)

    # Live dependencies — imported here so the package stays import-light.
    import os

    from .brain import ForkStructuredLLM
    from .ingestion import (
        StockTwitsFetcher,
        YFinanceFetcher,
        YFinanceFundamentalsFetcher,
        YFinanceNewsFetcher,
    )
    from .orchestration import make_brain_analyzer

    # Macro is optional: only if a FRED key is configured.
    macro_fetcher = None
    if os.environ.get("FRED_API_KEY"):
        from .ingestion import FredFetcher

        macro_fetcher = FredFetcher()

    analyzer = make_brain_analyzer(ForkStructuredLLM())
    deps = dict(
        fetcher=YFinanceFetcher(),
        news_fetcher=YFinanceNewsFetcher(),
        fundamentals_fetcher=YFinanceFundamentalsFetcher(),
        macro_fetcher=macro_fetcher,
        social_fetcher=StockTwitsFetcher(),
        analyzer=analyzer,
        db_url=args.db,
        start=args.start,
        end=args.end,
        base_risk_pct=args.base_risk,
    )

    def _print(report):
        print(
            f"cycle: triggers={report.triggers} analyzed={report.analyzed} "
            f"traded={report.traded} skipped_cost={report.skipped_cost} "
            f"skipped_not_tradable={report.skipped_not_tradable}"
        )
        for t in report.trades:
            print(f"  {t.action.upper()} {t.symbol} qty={t.quantity} @ {t.entry_price} -> {t.status}")

    if args.loop:
        import time

        print(f"autonomous loop every {args.loop}s (Ctrl-C to stop)")
        try:
            while True:
                _print(run_once(args.symbols, **deps))
                time.sleep(args.loop)
        except KeyboardInterrupt:
            print("stopped")
        return 0

    _print(run_once(args.symbols, **deps))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
