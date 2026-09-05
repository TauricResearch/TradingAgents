"""Headless local entry point for an explicit watchlist refresh."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .narrative_provider import NarrativeMode
from .research_jobs import LocalResearchJobRunner, ResearchDataProvider
from .watchlist import JsonWatchlistStore
from .watchlist_refresh import WatchlistRefreshRequest, execute_watchlist_refresh


def main(argv: list[str] | None = None) -> int:
    """Run an explicit local refresh and return nonzero when a job fails."""

    parser = argparse.ArgumentParser(description="Refresh the explicit local stock watchlist.")
    parser.add_argument(
        "--data-dir", default=".research-data", help="Local research artifact directory"
    )
    parser.add_argument(
        "--as-of", type=date.fromisoformat, help="Research date in YYYY-MM-DD format"
    )
    parser.add_argument("--lookback-days", type=int, default=90, help="Price history lookback")
    parser.add_argument(
        "--data-provider",
        choices=[item.value for item in ResearchDataProvider],
        default=ResearchDataProvider.AUTO.value,
    )
    parser.add_argument(
        "--narrative-mode",
        choices=[item.value for item in NarrativeMode],
        default=NarrativeMode.DETERMINISTIC.value,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print selected symbols without data calls"
    )
    args = parser.parse_args(argv)

    watchlist = JsonWatchlistStore(Path(args.data_dir))
    symbols = [entry.symbol for entry in watchlist.list_entries()]
    if args.dry_run:
        print(json.dumps({"dry_run": True, "symbols": symbols}, ensure_ascii=True))
        return 0

    request = WatchlistRefreshRequest(
        as_of_date=args.as_of or date.today(),
        lookback_days=args.lookback_days,
        data_provider=ResearchDataProvider(args.data_provider),
        narrative_mode=NarrativeMode(args.narrative_mode),
    )
    runner = LocalResearchJobRunner(args.data_dir)
    try:
        outcome = execute_watchlist_refresh(watchlist, runner, request)
    finally:
        runner.shutdown()
    print(
        json.dumps(
            {
                "batch_id": outcome.batch_id,
                "symbols": outcome.symbols,
                "succeeded": outcome.succeeded,
                "failed": outcome.failed,
                "jobs": [job.model_dump(mode="json") for job in outcome.jobs],
            },
            ensure_ascii=True,
        )
    )
    return 1 if outcome.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
