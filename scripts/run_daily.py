"""Headless driver for the scheduled TradingAgents runner.

Run via ``python scripts/run_daily.py`` (or via the macOS launchd job
installed by ``scripts/install_launchd.sh``). For every entry in
``config/watchlist.yaml`` it:

1. Runs the TradingAgents pipeline for the configured analysis date.
2. Persists the canonical reports folder to ``reports/<TICKER>_<TS>/``.
3. Renders the Portfolio Manager ``decision.md`` to a PDF.
4. Sends the short message + PDF to the configured Telegram chat.

Failures for one ticker are logged and skipped; the runner exits 0 if at
least one ticker produced a report, 1 if every ticker failed, 2 if the
watchlist was empty / unreadable.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

# Make the project root importable when launched directly via launchd
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tradingagents import default_config as _default_config  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.notifications import telegram as telegram_mod  # noqa: E402
from tradingagents.reports.exporter import (  # noqa: E402
    extract_decision_summary,
    markdown_to_pdf,
    save_report_to_disk,
)
from tradingagents.watchlist import WatchlistEntry, load_watchlist  # noqa: E402

logger = logging.getLogger("run_daily")

EXIT_OK = 0
EXIT_ALL_FAILED = 1
EXIT_BAD_WATCHLIST = 2


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _run_one(
    entry: WatchlistEntry,
    *,
    analysis_date: str,
    reports_root: Path,
) -> dict[str, Any] | None:
    """Execute the pipeline for a single watchlist entry.

    Returns a dict ``{"report_dir", "decision_md", "pdf", "summary"}`` on
    success or ``None`` on failure (with the failure already logged).
    """
    symbol = entry.symbol
    asset_type = entry.asset_type
    config = _default_config.DEFAULT_CONFIG.copy()

    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = reports_root / f"{symbol}_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Analyzing %s (%s) on %s -> %s", symbol, asset_type, analysis_date, report_dir)

    graph_kwargs: dict[str, Any] = {"debug": False, "config": config}
    if entry.analysts is not None:
        graph_kwargs["selected_analysts"] = entry.analysts

    try:
        graph = TradingAgentsGraph(**graph_kwargs)
        final_state, _decision = graph.propagate(symbol, analysis_date, asset_type=asset_type)
    except Exception:
        logger.exception("propagate() failed for %s", symbol)
        return None

    save_report_to_disk(final_state, symbol, report_dir)
    decision_md_path = report_dir / "5_portfolio" / "decision.md"
    if not decision_md_path.exists():
        logger.error("decision.md missing for %s at %s", symbol, decision_md_path)
        return None

    decision_text = decision_md_path.read_text(encoding="utf-8")
    summary = extract_decision_summary(decision_text)

    pdf_path = markdown_to_pdf(decision_md_path)
    if pdf_path is None:
        logger.warning(
            "PDF conversion failed for %s; Telegram will fall back to .md attachment", symbol
        )

    return {
        "report_dir": report_dir,
        "decision_md": decision_md_path,
        "pdf": pdf_path,
        "summary": summary,
    }


def _deliver(
    entry: WatchlistEntry,
    result: dict[str, Any],
) -> bool:
    try:
        return telegram_mod.send_report(
            entry.symbol,
            result["summary"],
            pdf_path=result["pdf"],
            markdown_path=result["decision_md"],
        )
    except telegram_mod.TelegramError:
        logger.exception("Telegram delivery failed for %s", entry.symbol)
        return False
    except Exception:
        logger.exception("Unexpected error during Telegram delivery for %s", entry.symbol)
        return False


def run(
    *,
    analysis_date: str,
    reports_root: Path,
    watchlist_path: Path | None = None,
) -> int:
    try:
        entries = load_watchlist(watchlist_path)
    except Exception:
        logger.exception("Failed to load watchlist")
        return EXIT_BAD_WATCHLIST

    if not entries:
        logger.warning("Watchlist is empty; nothing to do")
        return EXIT_OK

    logger.info("Running scheduled analysis for %d ticker(s)", len(entries))
    reports_root.mkdir(parents=True, exist_ok=True)

    successes = 0
    for entry in entries:
        try:
            result = _run_one(entry, analysis_date=analysis_date, reports_root=reports_root)
        except Exception:
            logger.exception("Unhandled error processing %s", entry.symbol)
            continue
        if result is None:
            continue
        delivered = _deliver(entry, result)
        suffix = "delivered" if delivered else "telegram not delivered"
        logger.info("Done %s: report=%s (%s)", entry.symbol, result["report_dir"], suffix)
        successes += 1

    if successes == 0:
        logger.error("All tickers failed; aborting with non-zero exit")
        return EXIT_ALL_FAILED
    logger.info("Scheduled run complete: %d/%d succeeded", successes, len(entries))
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--date",
        default=_dt.date.today().isoformat(),
        help="Analysis date in YYYY-MM-DD (default: today, local time)",
    )
    parser.add_argument(
        "--reports-root",
        default=str(PROJECT_ROOT / "reports"),
        help="Where to write the per-run reports folder",
    )
    parser.add_argument(
        "--watchlist",
        default=None,
        help="Override TRADINGAGENTS_WATCHLIST_PATH for this run",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args()
    _configure_logging(args.verbose)

    watchlist = Path(args.watchlist) if args.watchlist else None
    try:
        return run(
            analysis_date=args.date,
            reports_root=Path(args.reports_root),
            watchlist_path=watchlist,
        )
    except Exception:
        # Defense in depth: the per-entry try/except should have caught this
        # but a bug in the runner itself should not fail silently.
        logger.error("run_daily crashed:\n%s", traceback.format_exc())
        return EXIT_ALL_FAILED


if __name__ == "__main__":
    sys.exit(main())
