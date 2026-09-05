"""Local, immutable archive for completed research workflow bundles."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from tradingagents.dataflows.utils import safe_ticker_component

from .research_report import ResearchReportBundle


class ResearchRunSummary(BaseModel):
    """Small index record for one completed research run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    as_of_date: datetime
    generated_at: datetime
    has_signal: bool
    has_risk_review: bool
    has_backtest: bool
    narrative_mode: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None


class ResearchRunArchive(Protocol):
    """Persistence boundary for completed research bundles."""

    def save_bundle(self, bundle: ResearchReportBundle) -> ResearchRunSummary:
        """Persist an immutable workflow bundle and return its summary."""

    def list_runs(self, symbol: str) -> list[ResearchRunSummary]:
        """List completed bundles for a symbol, newest first."""

    def load_latest_bundle(self, symbol: str) -> ResearchReportBundle | None:
        """Load the newest completed bundle for a symbol."""

    def load_bundle(self, symbol: str, run_id: str) -> ResearchReportBundle | None:
        """Load one archived bundle by its opaque local run ID."""


class JsonResearchRunArchive:
    """Filesystem archive colocated with the JSONL artifact cache.

    Artifacts in ``prices/`` and similar directories are current cached facts.
    Each file in ``runs/`` instead captures the complete point-in-time research
    view, including the signal, deterministic risk decision, and backtest.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save_bundle(self, bundle: ResearchReportBundle) -> ResearchRunSummary:
        run_id = _new_run_id(bundle.generated_at)
        path = self._path(bundle.symbol, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        return _summary(run_id, bundle)

    def list_runs(self, symbol: str) -> list[ResearchRunSummary]:
        records: list[ResearchRunSummary] = []
        for path in self._directory(symbol).glob("*.json"):
            bundle = self._load_path(path)
            if bundle is not None:
                records.append(_summary(path.stem, bundle))
        return sorted(records, key=lambda item: (item.generated_at, item.run_id), reverse=True)

    def load_latest_bundle(self, symbol: str) -> ResearchReportBundle | None:
        summaries = self.list_runs(symbol)
        if not summaries:
            return None
        return self._load_path(self._path(symbol, summaries[0].run_id))

    def load_bundle(self, symbol: str, run_id: str) -> ResearchReportBundle | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            return None
        return self._load_path(self._path(symbol, run_id))

    def _load_path(self, path: Path) -> ResearchReportBundle | None:
        try:
            return ResearchReportBundle.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _directory(self, symbol: str) -> Path:
        return self.root / "runs" / safe_ticker_component(symbol)

    def _path(self, symbol: str, run_id: str) -> Path:
        return self._directory(symbol) / f"{run_id}.json"


def _new_run_id(generated_at: datetime) -> str:
    timestamp = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid4().hex[:10]}"


def _summary(run_id: str, bundle: ResearchReportBundle) -> ResearchRunSummary:
    return ResearchRunSummary(
        run_id=run_id,
        symbol=bundle.symbol,
        as_of_date=bundle.as_of_date,
        generated_at=bundle.generated_at,
        has_signal=bundle.signal is not None,
        has_risk_review=bundle.risk_review is not None,
        has_backtest=bundle.backtest_result is not None,
        narrative_mode=(bundle.run_audit.narrative_mode if bundle.run_audit is not None else None),
        llm_provider=(bundle.run_audit.llm_provider if bundle.run_audit is not None else None),
        llm_model=(bundle.run_audit.llm_model if bundle.run_audit is not None else None),
    )
