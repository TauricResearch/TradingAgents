"""Filesystem document store for portfolio and run artifacts.

All artifacts for a triggered process are scoped under one canonical run id:

    reports/daily/{date}/{run_id}/
        market/report/
        {TICKER}/report/
        portfolio/report/
        run_meta.json
        run_events.jsonl

Timestamp-prefixed report files allow multiple rewrites within the same run
without overwriting earlier artifacts. Load methods return the latest matching
artifact within the configured run; when no run_id is configured, they search
across all runs for the date and return the latest match.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.portfolio.exceptions import ReportStoreError
from tradingagents.report_paths import ts_now


class ReportStore:
    """Filesystem document store for all portfolio-related reports."""

    def __init__(
        self,
        base_dir: str | Path = "reports",
        run_id: str | None = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._run_id = run_id

    @property
    def run_id(self) -> str | None:
        """The canonical run identifier set on this store, if any."""
        return self._run_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _date_root(self, date: str, *, for_write: bool = False) -> Path:
        daily = self._base_dir / "daily" / date
        if self._run_id:
            return daily / self._run_id
        if for_write:
            raise ReportStoreError("run_id is required for report-store writes")
        return daily

    def _portfolio_dir(self, date: str, *, for_write: bool = False) -> Path:
        return self._date_root(date, for_write=for_write) / "portfolio"

    def _run_roots(self, date: str) -> list[Path]:
        daily = self._base_dir / "daily" / date
        if self._run_id:
            return [daily / self._run_id]
        if not daily.exists():
            return []
        return sorted((p for p in daily.iterdir() if p.is_dir()), reverse=True)

    @staticmethod
    def _load_latest_ts(directory: Path, name: str) -> dict[str, Any] | None:
        if not directory.exists():
            return None
        candidates = sorted(directory.glob(f"*_{name}"), reverse=True)
        if not candidates:
            return None
        try:
            return json.loads(candidates[0].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _load_latest_from_runs(self, date: str, relative_dir: str, name: str) -> dict[str, Any] | None:
        for root in self._run_roots(date):
            data = self._load_latest_ts(root / relative_dir, name)
            if data is not None:
                return data
        return None

    def _glob_run_files(self, pattern: str) -> list[Path]:
        return sorted(self._base_dir.glob(pattern), reverse=True)

    @staticmethod
    def _sanitize(obj: Any) -> Any:
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, dict):
            return {k: ReportStore._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ReportStore._sanitize(item) for item in obj]
        if hasattr(obj, "type") and hasattr(obj, "content"):
            try:
                if hasattr(obj, "dict") and callable(obj.dict):
                    return ReportStore._sanitize(obj.dict())
            except Exception:
                pass
            return {"type": str(obj.type), "content": str(obj.content)}
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)


    def _write_json(self, path: Path, data: dict[str, Any]) -> Path:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            sanitized = self._sanitize(data)
            path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
            return path
        except OSError as exc:
            raise ReportStoreError(f"Failed to write {path}: {exc}") from exc

    def _read_json(self, path: Path) -> dict[str, Any] | None:
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
        root = self._date_root(date, for_write=True)
        path = root / "market" / "report" / f"{ts_now()}_macro_scan_summary.json"
        return self._write_json(path, data)

    def load_scan(self, date: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, "market/report", "macro_scan_summary.json")

    # ------------------------------------------------------------------
    # Per-Ticker Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        root = self._date_root(date, for_write=True)
        path = root / ticker.upper() / "report" / f"{ts_now()}_complete_report.json"
        return self._write_json(path, data)

    def load_analysis(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, f"{ticker.upper()}/report", "complete_report.json")

    # ------------------------------------------------------------------
    # Holding Reviews
    # ------------------------------------------------------------------

    def save_holding_review(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        pdir = self._portfolio_dir(date, for_write=True)
        path = pdir / "report" / f"{ts_now()}_{ticker.upper()}_holding_review.json"
        return self._write_json(path, data)

    def load_holding_review(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, "portfolio/report", f"{ticker.upper()}_holding_review.json")

    # ------------------------------------------------------------------
    # Risk Metrics
    # ------------------------------------------------------------------

    def save_risk_metrics(self, date: str, portfolio_id: str, data: dict[str, Any]) -> Path:
        pdir = self._portfolio_dir(date, for_write=True)
        path = pdir / "report" / f"{ts_now()}_{portfolio_id}_risk_metrics.json"
        return self._write_json(path, data)

    def load_risk_metrics(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, "portfolio/report", f"{portfolio_id}_risk_metrics.json")

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
        pdir = self._portfolio_dir(date, for_write=True)
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
        return json_path

    def load_pm_decision(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, "portfolio/report", f"{portfolio_id}_pm_decision.json")

    def save_execution_result(self, date: str, portfolio_id: str, data: dict[str, Any]) -> Path:
        pdir = self._portfolio_dir(date, for_write=True)
        path = pdir / "report" / f"{ts_now()}_{portfolio_id}_execution_result.json"
        return self._write_json(path, data)

    def load_execution_result(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, "portfolio/report", f"{portfolio_id}_execution_result.json")

    def save_portfolio_node_results(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
    ) -> Path:
        """Persist node-level portfolio outputs for a single run."""
        pdir = self._portfolio_dir(date, for_write=True)
        path = pdir / "report" / f"{ts_now()}_{portfolio_id}_node_results.json"
        return self._write_json(path, data)

    def load_portfolio_node_results(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        """Load the latest node-level portfolio output payload."""
        return self._load_latest_from_runs(date, "portfolio/report", f"{portfolio_id}_node_results.json")

    def clear_portfolio_stage(self, date: str, portfolio_id: str) -> list[str]:
        deleted: list[str] = []
        for root in self._run_roots(date):
            report_dir = root / "portfolio" / "report"
            if not report_dir.exists():
                continue
            for suffix in (
                f"{portfolio_id}_pm_decision.json",
                f"{portfolio_id}_pm_decision.md",
                f"{portfolio_id}_execution_result.json",
            ):
                for path in report_dir.glob(f"*_{suffix}"):
                    path.unlink()
                    deleted.append(path.name)
        return deleted

    # ------------------------------------------------------------------
    # Run Meta / Events persistence
    # ------------------------------------------------------------------

    def save_run_meta(self, date: str, data: dict[str, Any]) -> Path:
        root = self._date_root(date, for_write=True)
        return self._write_json(root / "run_meta.json", data)

    def load_run_meta(self, date: str) -> dict[str, Any] | None:
        if self._run_id:
            return self._read_json(self._date_root(date) / "run_meta.json")
        for root in self._run_roots(date):
            data = self._read_json(root / "run_meta.json")
            if data is not None:
                return data
        return None

    def save_run_events(self, date: str, events: list[dict[str, Any]]) -> Path:
        root = self._date_root(date, for_write=True)
        path = root / "run_events.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(self._sanitize(evt), separators=(",", ":")) for evt in events]
            path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
            return path
        except OSError as exc:
            raise ReportStoreError(f"Failed to write {path}: {exc}") from exc

    def load_run_events(self, date: str) -> list[dict[str, Any]]:
        candidates: list[Path]
        if self._run_id:
            candidates = [self._date_root(date) / "run_events.jsonl"]
        else:
            candidates = [root / "run_events.jsonl" for root in self._run_roots(date)]

        for path in candidates:
            if not path.exists():
                continue
            events: list[dict[str, Any]] = []
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
                return events
            except json.JSONDecodeError as exc:
                raise ReportStoreError(f"Corrupt JSONL at {path}: {exc}") from exc
        return []

    @classmethod
    def list_run_metas(cls, base_dir: str | Path = "reports") -> list[dict[str, Any]]:
        base = Path(base_dir)
        metas: list[dict[str, Any]] = []
        for path in base.glob("daily/*/*/run_meta.json"):
            try:
                metas.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        metas.sort(key=lambda m: m.get("created_at", 0), reverse=True)
        return metas

    # ------------------------------------------------------------------
    # Analyst / Trader Checkpoints
    # ------------------------------------------------------------------

    def save_analysts_checkpoint(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        root = self._date_root(date, for_write=True)
        path = root / ticker.upper() / "report" / f"{ts_now()}_analysts_checkpoint.json"
        return self._write_json(path, data)

    def load_analysts_checkpoint(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, f"{ticker.upper()}/report", "analysts_checkpoint.json")

    def save_trader_checkpoint(self, date: str, ticker: str, data: dict[str, Any]) -> Path:
        root = self._date_root(date, for_write=True)
        path = root / ticker.upper() / "report" / f"{ts_now()}_trader_checkpoint.json"
        return self._write_json(path, data)

    def load_trader_checkpoint(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._load_latest_from_runs(date, f"{ticker.upper()}/report", "trader_checkpoint.json")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def list_pm_decisions(self, portfolio_id: str) -> list[Path]:
        pattern = f"daily/*/*/portfolio/report/*_{portfolio_id}_pm_decision.json"
        return self._glob_run_files(pattern)

    def list_analyses_for_date(self, date: str) -> list[str]:
        tickers: set[str] = set()
        for root in self._run_roots(date):
            for report_path in root.glob("*/report/*_complete_report.json"):
                ticker = report_path.parent.parent.name
                if ticker not in {"MARKET", "PORTFOLIO", "REPORT"}:
                    tickers.add(ticker.upper())
        return sorted(tickers)
