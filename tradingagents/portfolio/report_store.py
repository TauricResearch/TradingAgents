"""Filesystem document store for Portfolio Manager reports.

Saves and loads all non-transactional portfolio artifacts (scans, per-ticker
analysis, holding reviews, risk metrics, PM decisions) using the existing
``tradingagents/report_paths.py`` path convention.

When a ``flow_id`` is set on the store, artifacts are written under a
flow-scoped subdirectory with **timestamp-prefixed filenames** so that
re-runs within the same flow never overwrite earlier results and the most
recent version is always resolved by sorting::

    reports/daily/{date}/{flow_id}/
    ├── market/report/
    │   └── {ts}_macro_scan_summary.json
    ├── {TICKER}/report/
    │   ├── {ts}_complete_report.json
    │   ├── {ts}_analysts_checkpoint.json
    │   └── {ts}_trader_checkpoint.json
    ├── portfolio/report/
    │   ├── {ts}_{TICKER}_holding_review.json
    │   ├── {ts}_{portfolio_id}_risk_metrics.json
    │   ├── {ts}_{portfolio_id}_pm_decision.json
    │   └── {ts}_{portfolio_id}_execution_result.json
    ├── run_meta.json
    └── run_events.jsonl

When only a legacy ``run_id`` is provided the layout is preserved for
backward compatibility::

    reports/daily/{date}/runs/{run_id}/
    ├── market/macro_scan_summary.json
    ├── {TICKER}/complete_report.json
    └── portfolio/{portfolio_id}_pm_decision.json

A ``latest.json`` pointer at the date level is updated on legacy
``run_id``-based writes for backward-compatible reads.

Usage::

    from tradingagents.portfolio.report_store import ReportStore

    # New flow_id-based (timestamped versioning)
    store = ReportStore(flow_id="a1b2c3d4")
    store.save_scan("2026-03-20", {"watchlist": [...]})
    data = store.load_scan("2026-03-20")  # always loads the most recent

    # Legacy run_id-based (backward compat)
    store = ReportStore(run_id="a1b2c3d4")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.portfolio.exceptions import ReportStoreError
from tradingagents.report_paths import read_latest_pointer, ts_now, write_latest_pointer


class ReportStore:
    """Filesystem document store for all portfolio-related reports.

    Directories are created automatically on first write.
    All load methods return ``None`` when the file does not exist.

    When ``flow_id`` is provided, all artifacts are written under
    ``{base_dir}/daily/{date}/{flow_id}/…`` with timestamp-prefixed filenames.
    Load methods always return the most recently written version.

    When only ``run_id`` is provided (legacy), the old ``runs/{run_id}/``
    layout is used for backward compatibility.
    """

    def __init__(
        self,
        base_dir: str | Path = "reports",
        flow_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Initialise the store with a base reports directory.

        Args:
            base_dir: Root directory for all reports. Defaults to ``"reports"``
                      (relative to CWD), matching ``report_paths.REPORTS_ROOT``.
                      Override via the ``PORTFOLIO_DATA_DIR`` env var or
                      ``get_portfolio_config()["data_dir"]``.
            flow_id:  Flow identifier grouping all phases of one analysis intent.
                      When set, writes use timestamped filenames under
                      ``{base}/daily/{date}/{flow_id}/``.
            run_id:   Legacy run identifier (backward compat).  When set without
                      ``flow_id``, writes go to ``runs/{run_id}/`` (old layout).
        """
        self._base_dir = Path(base_dir)
        self._flow_id = flow_id
        self._run_id = run_id

    @property
    def flow_id(self) -> str | None:
        """The flow identifier set on this store, if any."""
        return self._flow_id

    @property
    def run_id(self) -> str | None:
        """The run/flow identifier set on this store (flow_id takes precedence)."""
        return self._flow_id or self._run_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _date_root(self, date: str, *, for_write: bool = False) -> Path:
        """Return the base directory for a given date.

        Resolution order:
        1. ``flow_id``  → ``daily/{date}/{flow_id}`` (new timestamped layout)
        2. ``run_id``   → ``daily/{date}/runs/{run_id}`` (legacy layout)
        3. Neither (read path): check ``latest.json`` pointer, then flat layout.
        """
        daily = self._base_dir / "daily" / date

        if self._flow_id:
            return daily / self._flow_id

        if self._run_id:
            return daily / "runs" / self._run_id

        if not for_write:
            # Read path: check latest.json pointer (using our base_dir)
            latest_id = read_latest_pointer(date, base_dir=self._base_dir)
            if latest_id:
                candidate = daily / "runs" / latest_id
                if candidate.exists():
                    return candidate

        # Fallback to legacy flat layout
        return daily

    def _update_latest(self, date: str) -> None:
        """Update the latest.json pointer (legacy run_id only).

        No-op for flow_id-based stores — timestamps make pointers unnecessary.
        """
        if self._run_id and not self._flow_id:
            write_latest_pointer(date, self._run_id, base_dir=self._base_dir)

    def _portfolio_dir(self, date: str, *, for_write: bool = False) -> Path:
        """Return the portfolio subdirectory for a given date.

        Path: ``{base}/daily/{date}[/{flow_id}|/runs/{run_id}]/portfolio/``
        """
        return self._date_root(date, for_write=for_write) / "portfolio"

    @staticmethod
    def _load_latest_ts(directory: Path, name: str) -> dict[str, Any] | None:
        """Return the payload from the most recent timestamped report file.

        Scans *directory* for files matching ``*_{name}``, sorts lexicographically
        (ISO timestamps are sortable), and returns the parsed JSON of the newest.
        Returns ``None`` when no matching file exists.
        """
        if not directory.exists():
            return None
        candidates = sorted(directory.glob(f"*_{name}"), reverse=True)
        if not candidates:
            return None
        try:
            return json.loads(candidates[0].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

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

        Flow path:   ``{base}/daily/{date}/{flow_id}/market/report/{ts}_macro_scan_summary.json``
        Legacy path: ``{base}/daily/{date}[/runs/{run_id}]/market/macro_scan_summary.json``

        Args:
            date: ISO date string, e.g. ``"2026-03-20"``.
            data: Scan output dict (typically the macro_scan_summary).

        Returns:
            Path of the written file.
        """
        root = self._date_root(date, for_write=True)
        if self._flow_id:
            path = root / "market" / "report" / f"{ts_now()}_macro_scan_summary.json"
        else:
            path = root / "market" / "macro_scan_summary.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_scan(self, date: str) -> dict[str, Any] | None:
        """Load macro scan summary. Returns None if the file does not exist."""
        root = self._date_root(date)
        if self._flow_id:
            return self._load_latest_ts(root / "market" / "report", "macro_scan_summary.json")
        return self._read_json(root / "market" / "macro_scan_summary.json")

    # ------------------------------------------------------------------
    # Per-Ticker Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        """Save per-ticker analysis report as JSON.

        Flow path:   ``{base}/daily/{date}/{flow_id}/{TICKER}/report/{ts}_complete_report.json``
        Legacy path: ``{base}/daily/{date}[/runs/{run_id}]/{TICKER}/complete_report.json``

        Args:
            date: ISO date string.
            ticker: Ticker symbol (stored as uppercase).
            data: Analysis output dict.
        """
        root = self._date_root(date, for_write=True)
        if self._flow_id:
            path = root / ticker.upper() / "report" / f"{ts_now()}_complete_report.json"
        else:
            path = root / ticker.upper() / "complete_report.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_analysis(self, date: str, ticker: str) -> dict[str, Any] | None:
        """Load per-ticker analysis JSON. Returns None if the file does not exist."""
        root = self._date_root(date)
        if self._flow_id:
            return self._load_latest_ts(root / ticker.upper() / "report", "complete_report.json")
        return self._read_json(root / ticker.upper() / "complete_report.json")

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

        Flow path:   ``…/portfolio/report/{ts}_{TICKER}_holding_review.json``
        Legacy path: ``…/portfolio/{TICKER}_holding_review.json``

        Args:
            date: ISO date string.
            ticker: Ticker symbol (stored as uppercase).
            data: HoldingReviewerAgent output dict.
        """
        pdir = self._portfolio_dir(date, for_write=True)
        if self._flow_id:
            path = pdir / "report" / f"{ts_now()}_{ticker.upper()}_holding_review.json"
        else:
            path = pdir / f"{ticker.upper()}_holding_review.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_holding_review(self, date: str, ticker: str) -> dict[str, Any] | None:
        """Load holding review output. Returns None if the file does not exist."""
        pdir = self._portfolio_dir(date)
        if self._flow_id:
            return self._load_latest_ts(pdir / "report", f"{ticker.upper()}_holding_review.json")
        return self._read_json(pdir / f"{ticker.upper()}_holding_review.json")

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

        Flow path:   ``…/portfolio/report/{ts}_{portfolio_id}_risk_metrics.json``
        Legacy path: ``…/portfolio/{portfolio_id}_risk_metrics.json``

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: Risk metrics dict (Sharpe, Sortino, VaR, etc.).
        """
        pdir = self._portfolio_dir(date, for_write=True)
        if self._flow_id:
            path = pdir / "report" / f"{ts_now()}_{portfolio_id}_risk_metrics.json"
        else:
            path = pdir / f"{portfolio_id}_risk_metrics.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_risk_metrics(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load risk metrics. Returns None if the file does not exist."""
        pdir = self._portfolio_dir(date)
        if self._flow_id:
            return self._load_latest_ts(pdir / "report", f"{portfolio_id}_risk_metrics.json")
        return self._read_json(pdir / f"{portfolio_id}_risk_metrics.json")

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

        Flow path:   ``…/portfolio/report/{ts}_{portfolio_id}_pm_decision.json``
        Legacy path: ``…/portfolio/{portfolio_id}_pm_decision.json``

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: PM decision dict (sells, buys, holds, rationale, …).
            markdown: Optional human-readable version; written when provided.

        Returns:
            Path of the written JSON file.
        """
        pdir = self._portfolio_dir(date, for_write=True)
        if self._flow_id:
            ts = ts_now()
            json_path = pdir / "report" / f"{ts}_{portfolio_id}_pm_decision.json"
            self._write_json(json_path, data)
            if markdown is not None:
                md_path = pdir / "report" / f"{ts}_{portfolio_id}_pm_decision.md"
                try:
                    md_path.parent.mkdir(parents=True, exist_ok=True)
                    md_path.write_text(markdown, encoding="utf-8")
                except OSError as exc:
                    raise ReportStoreError(f"Failed to write {md_path}: {exc}") from exc
        else:
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
        pdir = self._portfolio_dir(date)
        if self._flow_id:
            return self._load_latest_ts(pdir / "report", f"{portfolio_id}_pm_decision.json")
        return self._read_json(pdir / f"{portfolio_id}_pm_decision.json")

    def save_execution_result(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
    ) -> Path:
        """Save trade execution results.

        Flow path:   ``…/portfolio/report/{ts}_{portfolio_id}_execution_result.json``
        Legacy path: ``…/portfolio/{portfolio_id}_execution_result.json``

        Args:
            date: ISO date string.
            portfolio_id: UUID of the target portfolio.
            data: TradeExecutor output dict.
        """
        pdir = self._portfolio_dir(date, for_write=True)
        if self._flow_id:
            path = pdir / "report" / f"{ts_now()}_{portfolio_id}_execution_result.json"
        else:
            path = pdir / f"{portfolio_id}_execution_result.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_execution_result(
        self,
        date: str,
        portfolio_id: str,
    ) -> dict[str, Any] | None:
        """Load execution result. Returns None if the file does not exist."""
        pdir = self._portfolio_dir(date)
        if self._flow_id:
            return self._load_latest_ts(pdir / "report", f"{portfolio_id}_execution_result.json")
        return self._read_json(pdir / f"{portfolio_id}_execution_result.json")

    def clear_portfolio_stage(self, date: str, portfolio_id: str) -> list[str]:
        """Delete PM decision and execution result files for a given date/portfolio.

        For flow_id-based stores, deletes ALL timestamped versions.
        Returns a list of deleted file names so the caller can log what was removed.
        """
        pdir = self._portfolio_dir(date, for_write=True)
        deleted = []
        if self._flow_id:
            report_dir = pdir / "report"
            if report_dir.exists():
                for suffix in (
                    f"{portfolio_id}_pm_decision.json",
                    f"{portfolio_id}_pm_decision.md",
                    f"{portfolio_id}_execution_result.json",
                ):
                    for path in report_dir.glob(f"*_{suffix}"):
                        path.unlink()
                        deleted.append(path.name)
        else:
            targets = [
                pdir / f"{portfolio_id}_pm_decision.json",
                pdir / f"{portfolio_id}_pm_decision.md",
                pdir / f"{portfolio_id}_execution_result.json",
            ]
            for path in targets:
                if path.exists():
                    path.unlink()
                    deleted.append(path.name)
        return deleted

    # ------------------------------------------------------------------
    # Run Meta / Events persistence
    # ------------------------------------------------------------------

    def save_run_meta(self, date: str, data: dict[str, Any]) -> Path:
        """Save run metadata JSON.

        Path: ``{base}/daily/{date}[/runs/{run_id}]/run_meta.json``
        """
        root = self._date_root(date, for_write=True)
        path = root / "run_meta.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_run_meta(self, date: str) -> dict[str, Any] | None:
        """Load run metadata. Returns None if the file does not exist."""
        root = self._date_root(date)
        path = root / "run_meta.json"
        return self._read_json(path)

    def save_run_events(self, date: str, events: list[dict[str, Any]]) -> Path:
        """Save run events as JSONL (one JSON object per line).

        Path: ``{base}/daily/{date}[/runs/{run_id}]/run_events.jsonl``
        """
        root = self._date_root(date, for_write=True)
        path = root / "run_events.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            for evt in events:
                sanitized = self._sanitize(evt)
                lines.append(json.dumps(sanitized, separators=(",", ":")))
            path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
            return path
        except OSError as exc:
            raise ReportStoreError(f"Failed to write {path}: {exc}") from exc

    def load_run_events(self, date: str) -> list[dict[str, Any]]:
        """Load run events from JSONL file. Returns empty list if file does not exist."""
        root = self._date_root(date)
        path = root / "run_events.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ReportStoreError(f"Corrupt JSONL at {path}: {exc}") from exc
        return events

    @classmethod
    def list_run_metas(cls, base_dir: str | Path = "reports") -> list[dict[str, Any]]:
        """Scan for all run_meta.json files and return metadata dicts, newest first.

        Searches both the new flow_id layout (``daily/*/{flow_id}/run_meta.json``)
        and the legacy run_id layout (``daily/*/runs/*/run_meta.json``).

        Args:
            base_dir: Root reports directory.

        Returns:
            List of run_meta dicts sorted by ``created_at`` descending.
        """
        base = Path(base_dir)
        # New flow_id layout: daily/{date}/{flow_id}/run_meta.json
        # Legacy run_id layout: daily/{date}/runs/{run_id}/run_meta.json
        patterns = ("daily/*/*/run_meta.json", "daily/*/runs/*/run_meta.json")
        seen: set[str] = set()
        metas: list[dict[str, Any]] = []
        for pattern in patterns:
            for path in base.glob(pattern):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    key = data.get("id") or str(path)
                    if key not in seen:
                        seen.add(key)
                        metas.append(data)
                except (json.JSONDecodeError, OSError):
                    continue
        metas.sort(key=lambda m: m.get("created_at", 0), reverse=True)
        return metas

    # ------------------------------------------------------------------
    # Analyst / Trader Checkpoints
    # ------------------------------------------------------------------

    def save_analysts_checkpoint(
        self, date: str, ticker: str, data: dict[str, Any]
    ) -> Path:
        """Save analysts checkpoint for a ticker.

        Flow path:   ``…/{TICKER}/report/{ts}_analysts_checkpoint.json``
        Legacy path: ``…/{TICKER}/analysts_checkpoint.json``
        """
        root = self._date_root(date, for_write=True)
        if self._flow_id:
            path = root / ticker.upper() / "report" / f"{ts_now()}_analysts_checkpoint.json"
        else:
            path = root / ticker.upper() / "analysts_checkpoint.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_analysts_checkpoint(
        self, date: str, ticker: str
    ) -> dict[str, Any] | None:
        """Load analysts checkpoint. Returns None if file does not exist."""
        root = self._date_root(date)
        if self._flow_id:
            return self._load_latest_ts(root / ticker.upper() / "report", "analysts_checkpoint.json")
        return self._read_json(root / ticker.upper() / "analysts_checkpoint.json")

    def save_trader_checkpoint(
        self, date: str, ticker: str, data: dict[str, Any]
    ) -> Path:
        """Save trader checkpoint for a ticker.

        Flow path:   ``…/{TICKER}/report/{ts}_trader_checkpoint.json``
        Legacy path: ``…/{TICKER}/trader_checkpoint.json``
        """
        root = self._date_root(date, for_write=True)
        if self._flow_id:
            path = root / ticker.upper() / "report" / f"{ts_now()}_trader_checkpoint.json"
        else:
            path = root / ticker.upper() / "trader_checkpoint.json"
        result = self._write_json(path, data)
        self._update_latest(date)
        return result

    def load_trader_checkpoint(
        self, date: str, ticker: str
    ) -> dict[str, Any] | None:
        """Load trader checkpoint. Returns None if file does not exist."""
        root = self._date_root(date)
        if self._flow_id:
            return self._load_latest_ts(root / ticker.upper() / "report", "trader_checkpoint.json")
        return self._read_json(root / ticker.upper() / "trader_checkpoint.json")

    # ------------------------------------------------------------------
    # PM Decisions
    # ------------------------------------------------------------------

    def list_pm_decisions(self, portfolio_id: str) -> list[Path]:
        """Return all saved PM decision JSON paths for portfolio_id, newest first.

        Searches flow_id, run_id-scoped, and legacy flat layouts.

        Args:
            portfolio_id: UUID of the target portfolio.

        Returns:
            Sorted list of Path objects, newest date first.
        """
        # New flow_id layout: daily/*/{flow_id}/portfolio/report/*_{pid}_pm_decision.json
        flow_pattern = f"daily/*/*/portfolio/report/*_{portfolio_id}_pm_decision.json"
        # Run-scoped layout: daily/*/runs/*/portfolio/{pid}_pm_decision.json
        run_pattern = f"daily/*/runs/*/portfolio/{portfolio_id}_pm_decision.json"
        # Legacy flat layout: daily/*/portfolio/{pid}_pm_decision.json
        flat_pattern = f"daily/*/portfolio/{portfolio_id}_pm_decision.json"
        paths = (
            set(self._base_dir.glob(flow_pattern))
            | set(self._base_dir.glob(run_pattern))
            | set(self._base_dir.glob(flat_pattern))
        )
        return sorted(paths, reverse=True)
