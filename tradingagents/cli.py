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
    args = parser.parse_args(argv)

    # Live dependencies — imported here so the package stays import-light.
    from .brain import ForkStructuredLLM
    from .ingestion import YFinanceFetcher, YFinanceNewsFetcher
    from .orchestration import make_brain_analyzer

    analyzer = make_brain_analyzer(ForkStructuredLLM())
    report = run_once(
        args.symbols,
        fetcher=YFinanceFetcher(),
        news_fetcher=YFinanceNewsFetcher(),
        analyzer=analyzer,
        db_url=args.db,
        start=args.start,
        end=args.end,
        base_risk_pct=args.base_risk,
    )

    print(
        f"cycle: triggers={report.triggers} analyzed={report.analyzed} "
        f"traded={report.traded} skipped_cost={report.skipped_cost} "
        f"skipped_not_tradable={report.skipped_not_tradable}"
    )
    for t in report.trades:
        print(f"  {t.action.upper()} {t.symbol} qty={t.quantity} @ {t.entry_price} -> {t.status}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
