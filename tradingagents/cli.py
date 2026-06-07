"""CLI: run the alpha from the global config.

    python -m tradingagents.cli AAPL MSFT [--loop SECONDS]

All tunable parameters live in ``config.toml`` (see tradingagents/config.py);
secrets live in ``.env``. CLI flags override a few config values per-run.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the trading-agent.")
    parser.add_argument("symbols", nargs="+", help="Ticker symbols, e.g. AAPL MSFT")
    parser.add_argument("--config", default=None, help="Path to config.toml")
    parser.add_argument("--start", default=None, help="History start (override config)")
    parser.add_argument("--end", default=None, help="History end (default today)")
    parser.add_argument("--db", default=None, help="Database URL (default local SQLite)")
    parser.add_argument("--loop", type=float, default=None, metavar="SECONDS",
                        help="Run continuously every SECONDS (default from config)")
    args = parser.parse_args(argv)

    import os

    from .config import load_settings

    settings = load_settings(args.config)
    start = args.start or settings.data.history_start

    print(
        f"model: provider={settings.llm.provider} "
        f"deep={settings.llm.deep_model} quick={settings.llm.quick_model}"
    )

    from .brain import ForkStructuredLLM
    from .brain.tooling import Extractors
    from .broker import PerTradeCommission, ZeroCommission
    from .ingestion import (
        StockTwitsFetcher,
        YFinanceFetcher,
        YFinanceFundamentalsFetcher,
        YFinanceNewsFetcher,
    )
    from .orchestration import make_brain_analyzer

    macro_fetcher = None
    if os.environ.get("FRED_API_KEY"):
        from .ingestion import FredFetcher

        macro_fetcher = FredFetcher()

    price_f = YFinanceFetcher()
    news_f = YFinanceNewsFetcher()
    fund_f = YFinanceFundamentalsFetcher()
    social_f = StockTwitsFetcher()

    extractors = Extractors(
        price_fetcher=price_f, news_fetcher=news_f, fundamentals_fetcher=fund_f,
        macro_fetcher=macro_fetcher, social_fetcher=social_f, history_start=start,
    )

    broker = None
    if os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"):
        from .broker.alpaca import AlpacaBroker

        broker = AlpacaBroker()
        print("broker: Alpaca (paper)")
    else:
        print("broker: PaperBroker (simulated)")

    fee = settings.costs.commission_per_trade
    commission = PerTradeCommission(fee) if fee > 0 else ZeroCommission()

    llm = ForkStructuredLLM(config=settings.llm_config())
    analyzer = make_brain_analyzer(
        llm, extractors=extractors,
        max_revisions=settings.cycle.max_revisions,
        base_risk_pct=settings.risk.base_risk_pct,
        charter=settings.charter_dict(),
    )

    deps = dict(
        broker=broker,
        fetcher=price_f, news_fetcher=news_f, fundamentals_fetcher=fund_f,
        macro_fetcher=macro_fetcher, social_fetcher=social_f,
        analyzer=analyzer,
        commission_model=commission,
        charter=settings.charter_dict(),
        top_k=settings.screening.top_k,
        base_risk_pct=settings.risk.base_risk_pct,
        db_url=args.db, start=start, end=args.end,
    )

    from .app import run_once

    def _print(report):
        print(
            f"cycle: triggers={report.triggers} analyzed={report.analyzed} "
            f"traded={report.traded} closed={report.closed} "
            f"skipped_cost={report.skipped_cost} skipped_not_tradable={report.skipped_not_tradable}"
        )
        for t in report.trades:
            print(f"  {t.action.upper()} {t.symbol} qty={t.quantity} @ {t.entry_price} -> {t.status}")

    interval = args.loop if args.loop is not None else None
    if interval:
        import time

        print(f"autonomous loop every {interval}s (Ctrl-C to stop)")
        try:
            while True:
                _print(run_once(args.symbols, **deps))
                time.sleep(interval)
        except KeyboardInterrupt:
            print("stopped")
        return 0

    _print(run_once(args.symbols, **deps))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
