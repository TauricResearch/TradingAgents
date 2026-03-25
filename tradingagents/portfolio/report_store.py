"""Filesystem document store for Portfolio Manager reports.

Saves and loads all non-transactional portfolio artifacts (scans, per-ticker
analysis, holding reviews, risk metrics, PM decisions) using the existing
``tradingagents/report_paths.py`` path convention.

When a ``run_id`` is set on the store, all artifacts are written under a
run-specific subdirectory so that same-day re-runs never overwrite earlier
results::

    reports/daily/{date}/runs/{run_id}/
    ├── market/
    │   └── macro_scan_summary.json
    ├── {TICKER}/
    │   └── complete_report.json
    └── portfolio/
        ├── {TICKER}_holding_review.json
        ├── {portfolio_id}_risk_metrics.json
        ├── {portfolio_id}_pm_decision.json
        └── {portfolio_id}_pm_decision.md

A ``latest.json`` pointer at the date level is updated on every write so
that load methods (when called *without* a ``run_id``) transparently
resolve to the most recent run.

Usage::

    from tradingagents.portfolio.report_store import ReportStore

    store = ReportStore(run_id="a1b2c3d4")
    store.save_scan("2026-03-20", {"watchlist": [...]})
    data = store.load_scan("2026-03-20")  # reads from latest run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.portfolio.exceptions import ReportStoreError
from tradingagents.report_paths import read_latest_pointer, write_latest_pointer


class ReportStore:
    """Filesystem document store for all portfolio-related reports.

    Directories are created automatically on first write.
    All load methods return ``None`` when the file does not exist.

    When ``run_id`` is provided, write paths are scoped under
    ``{base_dir}/daily/{date}/runs/{run_id}/…`` and a ``latest.json``
    pointer is updated automatically.  Load methods resolve through
    the pointer when no ``run_id`` is set.
    """

    def __init__(
        self,
        base_dir: str | Path = "reports",
        run_id: str | None = None,
    ) -> None:
        """Initialise the store with a base reports directory.

        Args:
            base_dir: Root directory for all reports. Defaults to ``"reports"``
                      (relative to CWD), matching ``report_paths.REPORTS_ROOT``.
                      Override via the ``PORTFOLIO_DATA_DIR`` env var or
                      ``get_portfolio_config()["data_dir"]``.
            run_id:   Optional short identifier for the current run.  When set,
                      all writes are scoped under a ``runs/{run_id}/``
                      subdirectory so that same-day re-runs are preserved.
        """
        self._base_dir = Path(base_dir)
        self._run_id = run_id

    @property
    def run_id(self) -> str | None:
        """The run identifier set on this store, if any."""
        return self._run_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _date_root(self, date: str, *, for_write: bool = False) -> Path:
        """Return the base directory for a given date, scoped by run_id.

        When ``for_write=True``, the run_id *must* be used (if present) so
        that writes land in the run-specific directory.

        When ``for_write=False`` (reads), the method first tries the
        run_id directory, then falls back to latest.json pointer, and
        finally falls back to the legacy flat layout.
        """
        daily = self._base_dir / "daily" / date

        if for_write and self._run_id:
            return daily / "runs" / self._run_id
        if self._run_id:
            return daily / "runs" / self._run_id

        # Read path: check latest.json pointer (using our base_dir)
        latest_id = read_latest_pointer(date, base_dir=self._base_dir)
        if latest_id:
            candidate = daily / "runs" / latest_id
            if candidate.exists():
                return candidate

        # Fallback to legacy flat layout
        return daily

    def _update_latest(self, date: str) -> None:
        """Update the latest.json pointer if run_id is set."""
        if self._run_id:
            write_latest_pointer(date, self._run_id, base_dir=self._base_dir)

    def _portfolio_dir(self, date: str, *, for_write: bool = False) -> Path:
        """Return the portfolio subdirectory for a given date.

        Path: ``{base}/daily/{date}[/runs/{run_id}]/portfolio/``
        """
        return self._date_root(date, for_write=for_write) / "portfolio"

    @staticmethod
    def _sanitize(obj: Any) -> Any:
        """Recursively convert non-JSON-serializable objects to safe types.

        Handles LangChain message objects (``HumanMessage``, ``AIMessage``,
        etc.) that appear in LangGraph state dicts, as well as any other
        arbitrary objects that are not natively JSON-serializable.
        """
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, dict):
            return {k: ReportStore._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ReportStore._sanitize(item) for item in obj]
        # LangChain BaseMessage objects expose .type and .content
        if hasattr(obj, "type") and hasattr(obj, "content"):
            try:
                if hasattr(obj, "dict") and callable(obj.dict):
                    return ReportStore._sanitize(obj.dict())
            except Exception:
                pass
            return {"type": str(obj.type), "content": str(obj.content)}
        # Generic fallback: try a serialization probe first
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

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
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            sanitized = self._sanitize(data)
            path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
            return path
        except OSError as exc:
            raise ReportStoreError(f"Failed to write {path}: {exc}") from exc

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """Read a JSON file, returning None if the file does not exist.

        Raises:
            ReportStoreError: On JSON parse error (file exists but is corrupt).
        """
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReportStoreError(f"Corrupt JSON at {path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Macro Scan
    # ------------------------------------------------------------------

    def save_scan(self, date: str, data: dict[str, Any]) -> Path:
        """Save macro scan summary JSON.

        Path: ``{base}/daily/{date}[/runs/{run_id}]/market/macro_scan_summary.json``

        Args:
            date: ISO date string, e.g. ``"2026-03-20"``.
            data: Scan output dict (typically the macro_scan_summary).

        Returns:
            Path of the written file.
        """
        root = self._date_root(date, for_write=True)
        path = root / "market" / "macro_scan_summary.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_scan(self, date: str) -> dict[str, Any] | None:
        """Load macro scan summary. Returns None if the file does not exist."""
        root = self._date_root(date)
        path = root / "market" / "macro_scan_summary.json"
        return self._read_json(path)

    # ------------------------------------------------------------------
    # Per-Ticker Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        """Save per-ticker analysis report as JSON.

        Path: ``{base}/daily/{date}[/runs/{run_id}]/{TICKER}/complete_report.json``

        Args:
            date: ISO date string.
            ticker: Ticker symbol (stored as uppercase).
            data: Analysis output dict.
        """
        root = self._date_root(date, for_write=True)
        path = root / ticker.upper() / "complete_report.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_analysis(self, date: str, ticker: str) -> dict[str, Any] | None:
        """Load per-ticker analysis JSON. Returns None if the file does not exist."""
        root = self._date_root(date)
        path = root / ticker.upper() / "complete_report.json"
        return self._read_json(path)

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

        Path: ``{base}/daily/{date}[/runs/{run_id}]/portfolio/{TICKER}_holding_review.json``

        Args:
            date: ISO date string.
            ticker: Ticker symbol (stored as uppercase).
            data: HoldingReviewerAgent output dict.
        """
        path = self._portfolio_dir(date, for_write=True) / f"{ticker.upper()}_holding_review.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_holding_review(self, date: str, ticker: str) -> dict[str, Any] | None:
        """Load holding review output. Returns None if the file does not exist."""
        path = self._portfolio_dir(date) / f"{ticker.upper()}_holding_review.json"
        return self._read_json(path)

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

        Path: ``{base}/daily/{date}[/runs/{run_id}]/portfolio/{portfolio_id}_risk_metrics.json``

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: Risk metrics dict (Sharpe, Sortino, VaR, etc.).
        """
        path = self._portfolio_dir(date, for_write=True) / f"{portfolio_id}_risk_metrics.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_risk_metrics(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load risk metrics. Returns None if the file does not exist."""
        path = self._portfolio_dir(date) / f"{portfolio_id}_risk_metrics.json"
        return self._read_json(path)

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

        JSON path: ``{base}/daily/{date}[/runs/{run_id}]/portfolio/{portfolio_id}_pm_decision.json``
        MD path:   ``…/{portfolio_id}_pm_decision.md`` (written only when ``markdown`` is not None)

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: PM decision dict (sells, buys, holds, rationale, …).
            markdown: Optional human-readable version; written when provided.

        Returns:
            Path of the written JSON file.
        """
        pdir = self._portfolio_dir(date, for_write=True)
        json_path = pdir / f"{portfolio_id}_pm_decision.json"
        self._write_json(json_path, data)
        if markdown is not None:
            md_path = pdir / f"{portfolio_id}_pm_decision.md"
            try:
                md_path.write_text(markdown, encoding="utf-8")
            except OSError as exc:
                raise ReportStoreError(f"Failed to write {md_path}: {exc}") from exc
        self._update_latest(date)
        return json_path

    def load_pm_decision(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load PM decision JSON. Returns None if the file does not exist."""
        path = self._portfolio_dir(date) / f"{portfolio_id}_pm_decision.json"
        return self._read_json(path)

    def save_execution_result(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
    ) -> Path:
        """Save trade execution results.

        Path: ``{base}/daily/{date}[/runs/{run_id}]/portfolio/{portfolio_id}_execution_result.json``

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: TradeExecutor output dict.
        """
        path = self._portfolio_dir(date, for_write=True) / f"{portfolio_id}_execution_result.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_execution_result(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load execution result. Returns None if the file does not exist."""
        path = self._portfolio_dir(date) / f"{portfolio_id}_execution_result.json"
        return self._read_json(path)

    def clear_portfolio_stage(self, date: str, portfolio_id: str) -> list[str]:
        """Delete PM decision and execution result files for a given date/portfolio.

        Returns a list of deleted file names so the caller can log what was removed.
        """
        pdir = self._portfolio_dir(date, for_write=True)
        targets = [
            pdir / f"{portfolio_id}_pm_decision.json",
            pdir / f"{portfolio_id}_pm_decision.md",
            pdir / f"{portfolio_id}_execution_result.json",
        ]
        deleted = []
        for path in targets:
            if path.exists():
                path.unlink()
                deleted.append(path.name)
        return deleted

    def list_pm_decisions(self, portfolio_id: str) -> list[Path]:
        """Return all saved PM decision JSON paths for portfolio_id, newest first.

        Searches both run-scoped and legacy flat layouts.

        Args:
            portfolio_id: UUID of the target portfolio.

        Returns:
            Sorted list of Path objects, newest date first.
        """
        # Run-scoped layout: daily/*/runs/*/portfolio/{pid}_pm_decision.json
        run_pattern = f"daily/*/runs/*/portfolio/{portfolio_id}_pm_decision.json"
        # Legacy flat layout: daily/*/portfolio/{pid}_pm_decision.json
        flat_pattern = f"daily/*/portfolio/{portfolio_id}_pm_decision.json"
        paths = set(self._base_dir.glob(run_pattern)) | set(self._base_dir.glob(flat_pattern))
        return sorted(paths, reverse=True)
