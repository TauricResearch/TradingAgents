"""One-time migration: backfill historical analyses into recommendations table.

Scans all completed analyses in the database, finds their
``final_trade_decision.md`` files, and runs the extractor to populate
the ``recommendations`` table.

Reports that fail to parse get ``verdict='UNKNOWN'`` and ``is_active=0``
so they don't pollute the dashboard but are available for manual review.

Usage
-----
From the project root::

    python -m desktop.utils.migrate_historical          # dry-run (default)
    python -m desktop.utils.migrate_historical --apply   # actually write to DB

Or from Python::

    from desktop.utils.migrate_historical import migrate
    stats = migrate(dry_run=False)
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from desktop.services.recommendation_extractor import (
    ExtractedRecommendation,
    extract_from_file,
)
from desktop.state.database import HistoryDB

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationStats:
    """Summary of a migration run."""

    total_analyses: int
    already_migrated: int
    migrated_ok: int
    migrated_unknown: int
    skipped_no_file: int
    skipped_error: int


def migrate(
    *,
    db: HistoryDB | None = None,
    dry_run: bool = True,
) -> MigrationStats:
    """Backfill the recommendations table from historical analyses.

    Parameters
    ----------
    db : HistoryDB, optional
        Database instance. Uses the default if not provided.
    dry_run : bool
        If True, log what would happen but don't write to DB.

    Returns
    -------
    MigrationStats
        Summary of the migration results.
    """
    if db is None:
        db = HistoryDB()

    analyses = db.list_analyses(status="completed", limit=10_000)
    total = len(analyses)
    already = 0
    ok = 0
    unknown = 0
    no_file = 0
    errors = 0

    logger.info(
        "Migration %s: processing %d completed analyses",
        "DRY-RUN" if dry_run else "APPLY",
        total,
    )

    for analysis in analyses:
        # Skip if recommendation already exists for this analysis
        existing = db.get_recommendation_by_analysis(analysis.id)
        if existing is not None:
            already += 1
            continue

        # Find the final_trade_decision.md file
        if not analysis.result_dir:
            no_file += 1
            logger.debug("Analysis #%d: no result_dir, skipping", analysis.id)
            continue

        decision_path = Path(analysis.result_dir) / "final_trade_decision.md"
        if not decision_path.exists():
            no_file += 1
            logger.debug(
                "Analysis #%d: %s not found, skipping",
                analysis.id,
                decision_path,
            )
            continue

        # Extract recommendation
        try:
            rec = extract_from_file(
                decision_path,
                ticker=analysis.ticker,
                analysis_id=analysis.id,
            )
        except Exception:
            logger.exception(
                "Analysis #%d: extraction failed for %s",
                analysis.id,
                decision_path,
            )
            errors += 1
            rec = None

        if dry_run:
            if rec and rec.verdict != "UNKNOWN":
                logger.info(
                    "  [DRY] #%d %s: %s stop=%s entry=%s target=%s",
                    analysis.id,
                    rec.ticker or analysis.ticker,
                    rec.verdict,
                    rec.stop_loss,
                    rec.entry_trigger,
                    rec.profit_target,
                )
                ok += 1
            elif rec:
                logger.info(
                    "  [DRY] #%d %s: UNKNOWN (would be inactive)",
                    analysis.id,
                    analysis.ticker,
                )
                unknown += 1
            continue

        # Write to DB
        if rec is None or rec.verdict == "UNKNOWN":
            # Fallback: create an UNKNOWN inactive record
            ticker = analysis.ticker
            rec_id = db.insert_recommendation(
                analysis_id=analysis.id,
                ticker=ticker,
                verdict="UNKNOWN",
                notes="Migration: extraction failed or returned UNKNOWN",
            )
            # Immediately deactivate
            db.deactivate_recommendation(rec_id)
            unknown += 1
            logger.info(
                "  #%d %s: UNKNOWN (inactive) → rec #%d",
                analysis.id,
                ticker,
                rec_id,
            )
        else:
            # Deactivate older recommendations for same ticker
            ticker = rec.ticker or analysis.ticker
            rec_id = db.insert_recommendation(
                analysis_id=analysis.id,
                ticker=ticker,
                verdict=rec.verdict,
                confidence=rec.confidence,
                price_at_analysis=rec.price_at_analysis,
                stop_loss=rec.stop_loss,
                entry_trigger=rec.entry_trigger,
                profit_target=rec.profit_target,
                review_date=rec.review_date,
                notes=rec.notes,
            )
            # Deactivate older recs for this ticker
            deactivated = db.deactivate_older_for_ticker(ticker, keep_id=rec_id)
            if deactivated:
                logger.info(
                    "  Deactivated %d older recommendation(s) for %s",
                    deactivated,
                    ticker,
                )
            ok += 1
            logger.info(
                "  #%d %s: %s → rec #%d",
                analysis.id,
                ticker,
                rec.verdict,
                rec_id,
            )

    stats = MigrationStats(
        total_analyses=total,
        already_migrated=already,
        migrated_ok=ok,
        migrated_unknown=unknown,
        skipped_no_file=no_file,
        skipped_error=errors,
    )

    logger.info(
        "Migration %s complete: %d total, %d already done, "
        "%d OK, %d UNKNOWN, %d no-file, %d errors",
        "DRY-RUN" if dry_run else "APPLY",
        stats.total_analyses,
        stats.already_migrated,
        stats.migrated_ok,
        stats.migrated_unknown,
        stats.skipped_no_file,
        stats.skipped_error,
    )

    return stats


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("=== DRY RUN (pass --apply to write to DB) ===\n")

    stats = migrate(dry_run=dry_run)

    print(f"\n{'='*50}")
    print(f"Total analyses:     {stats.total_analyses}")
    print(f"Already migrated:   {stats.already_migrated}")
    print(f"Migrated OK:        {stats.migrated_ok}")
    print(f"Migrated UNKNOWN:   {stats.migrated_unknown}")
    print(f"Skipped (no file):  {stats.skipped_no_file}")
    print(f"Skipped (error):    {stats.skipped_error}")

    if dry_run and (stats.migrated_ok + stats.migrated_unknown) > 0:
        print("\nRe-run with --apply to persist these changes.")


if __name__ == "__main__":
    main()
