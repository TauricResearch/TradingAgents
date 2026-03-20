"""Filesystem document store for Portfolio Manager reports.

Saves and loads all non-transactional portfolio artifacts (scans, per-ticker
analysis, holding reviews, risk metrics, PM decisions) using the existing
``tradingagents/report_paths.py`` path convention.

Directory layout::

    reports/daily/{date}/
    ├── market/
    │   └── macro_scan_summary.json        ← save_scan / load_scan
    ├── {TICKER}/
    │   └── complete_report.json           ← save_analysis / load_analysis
    └── portfolio/
        ├── {TICKER}_holding_review.json   ← save/load_holding_review
        ├── {portfolio_id}_risk_metrics.json
        ├── {portfolio_id}_pm_decision.json
        └── {portfolio_id}_pm_decision.md

Usage::

    from tradingagents.portfolio.report_store import ReportStore

    store = ReportStore()
    store.save_scan("2026-03-20", {"watchlist": [...]})
    data = store.load_scan("2026-03-20")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ReportStore:
    """Filesystem document store for all portfolio-related reports.

    Directories are created automatically on first write.
    All load methods return ``None`` when the file does not exist.
    """

    def __init__(self, base_dir: str | Path = "reports") -> None:
        """Initialise the store with a base reports directory.

        Args:
            base_dir: Root directory for all reports. Defaults to ``"reports"``
                      (relative to CWD), matching ``report_paths.REPORTS_ROOT``.
                      Override via the ``PORTFOLIO_DATA_DIR`` env var or
                      ``get_portfolio_config()["data_dir"]``.
        """
        # TODO: implement — store Path(base_dir), resolve as needed
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _portfolio_dir(self, date: str) -> Path:
        """Return the portfolio subdirectory for a given date.

        Path: ``{base_dir}/daily/{date}/portfolio/``
        """
        # TODO: implement
        raise NotImplementedError

    def _write_json(self, path: Path, data: dict[str, Any]) -> Path:
        """Write a dict to a JSON file, creating parent directories as needed.

        Args:
            path: Target file path.
            data: Data to serialise.

        Returns:
            The path written.

        Raises:
            ReportStoreError: On filesystem write failure.
        """
        # TODO: implement
        raise NotImplementedError

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """Read a JSON file, returning None if the file does not exist.

        Raises:
            ReportStoreError: On JSON parse error (file exists but is corrupt).
        """
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Macro Scan
    # ------------------------------------------------------------------

    def save_scan(self, date: str, data: dict[str, Any]) -> Path:
        """Save macro scan summary JSON.

        Path: ``{base_dir}/daily/{date}/market/macro_scan_summary.json``

        Args:
            date: ISO date string, e.g. ``"2026-03-20"``.
            data: Scan output dict (typically the macro_scan_summary).

        Returns:
            Path of the written file.
        """
        # TODO: implement
        raise NotImplementedError

    def load_scan(self, date: str) -> dict[str, Any] | None:
        """Load macro scan summary. Returns None if the file does not exist."""
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Per-Ticker Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        """Save per-ticker analysis report as JSON.

        Path: ``{base_dir}/daily/{date}/{TICKER}/complete_report.json``

        Args:
            date: ISO date string.
            ticker: Ticker symbol (stored as uppercase).
            data: Analysis output dict.
        """
        # TODO: implement
        raise NotImplementedError

    def load_analysis(self, date: str, ticker: str) -> dict[str, Any] | None:
        """Load per-ticker analysis JSON. Returns None if the file does not exist."""
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Holding Reviews
    # ------------------------------------------------------------------

    def save_holding_review(
        self,
        date: str,
        ticker: str,
        data: dict[str, Any],
    ) -> Path:
        """Save holding reviewer output for one ticker.

        Path: ``{base_dir}/daily/{date}/portfolio/{TICKER}_holding_review.json``

        Args:
            date: ISO date string.
            ticker: Ticker symbol (stored as uppercase).
            data: HoldingReviewerAgent output dict.
        """
        # TODO: implement
        raise NotImplementedError

    def load_holding_review(self, date: str, ticker: str) -> dict[str, Any] | None:
        """Load holding review output. Returns None if the file does not exist."""
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Risk Metrics
    # ------------------------------------------------------------------

    def save_risk_metrics(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
    ) -> Path:
        """Save risk computation results.

        Path: ``{base_dir}/daily/{date}/portfolio/{portfolio_id}_risk_metrics.json``

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: Risk metrics dict (Sharpe, Sortino, VaR, etc.).
        """
        # TODO: implement
        raise NotImplementedError

    def load_risk_metrics(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load risk metrics. Returns None if the file does not exist."""
        # TODO: implement
        raise NotImplementedError

    # ------------------------------------------------------------------
    # PM Decisions
    # ------------------------------------------------------------------

    def save_pm_decision(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
        markdown: str | None = None,
    ) -> Path:
        """Save PM agent decision.

        JSON path: ``{base_dir}/daily/{date}/portfolio/{portfolio_id}_pm_decision.json``
        MD path:   ``{base_dir}/daily/{date}/portfolio/{portfolio_id}_pm_decision.md``
                   (written only when ``markdown`` is not None)

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: PM decision dict (sells, buys, holds, rationale, …).
            markdown: Optional human-readable version; written when provided.

        Returns:
            Path of the written JSON file.
        """
        # TODO: implement
        raise NotImplementedError

    def load_pm_decision(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load PM decision JSON. Returns None if the file does not exist."""
        # TODO: implement
        raise NotImplementedError

    def list_pm_decisions(self, portfolio_id: str) -> list[Path]:
        """Return all saved PM decision JSON paths for portfolio_id, newest first.

        Scans ``{base_dir}/daily/*/portfolio/{portfolio_id}_pm_decision.json``.

        Args:
            portfolio_id: UUID of the target portfolio.

        Returns:
            Sorted list of Path objects, newest date first.
        """
        # TODO: implement
        raise NotImplementedError
