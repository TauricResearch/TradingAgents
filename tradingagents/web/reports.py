"""Immutable partial reports and atomic canonical final report publication."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tradingagents.observability.events import ArtifactRef
from tradingagents.reporting import write_report_tree

from .run_models import utc_timestamp
from .store import RunStore, RunStoreError


REPORT_KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
REVISION_PATTERN = re.compile(r"^(\d{6})-([0-9a-f]{64})\.md$")


class ReportPublicationError(RunStoreError):
    pass


@dataclass(frozen=True)
class ReportRevision:
    report_kind: str
    revision: int
    artifact: ArtifactRef


@dataclass(frozen=True)
class FinalReportPublication:
    reports_directory: Path
    complete_report: Path
    artifacts: tuple[ArtifactRef, ...]
    published_at: str


class ReportArtifactWriter:
    def __init__(self, store: RunStore):
        self.store = store

    def write_revision(
        self,
        run_id: str,
        report_kind: str,
        content: str,
    ) -> ReportRevision:
        if not REPORT_KIND_PATTERN.fullmatch(report_kind):
            raise ReportPublicationError("invalid report kind")
        if not isinstance(content, str) or not content:
            raise ReportPublicationError("report revision content is required")
        run_dir = self.store._run_dir(run_id)
        revision_dir = run_dir / "report-revisions" / report_kind
        encoded = content.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()

        with self.store.lock_for(run_id):
            revision_dir.mkdir(parents=True, exist_ok=True)
            existing = [
                int(match.group(1))
                for path in revision_dir.iterdir()
                if path.is_file() and (match := REVISION_PATTERN.fullmatch(path.name))
            ]
            revision = max(existing, default=0) + 1
            filename = f"{revision:06d}-{digest}.md"
            destination = revision_dir / filename
            if destination.exists():
                raise ReportPublicationError("report revision path already exists")
            self.store._write_bytes_atomic(destination, encoded)
            self.store._fsync_directory(revision_dir)

        locator = destination.relative_to(run_dir).as_posix()
        return ReportRevision(
            report_kind=report_kind,
            revision=revision,
            artifact=ArtifactRef(
                artifact_id=f"report-revision:{digest}",
                kind="report-revision",
                media_type="text/markdown",
                content_sha256=digest,
                byte_size=len(encoded),
                locator=locator,
            ),
        )

    def publish_final(
        self,
        run_id: str,
        final_state: dict[str, Any],
        ticker: str,
    ) -> FinalReportPublication:
        run_dir = self.store._run_dir(run_id)
        reports_dir = run_dir / "reports"
        with self.store.lock_for(run_id):
            if reports_dir.exists():
                raise ReportPublicationError("canonical reports are already published")
            temporary = run_dir / f".reports.{uuid.uuid4().hex}.tmp"
            try:
                complete = write_report_tree(final_state, ticker, temporary)
                self._verify_report_tree(temporary, complete, final_state)
                self._fsync_tree(temporary)
                os.replace(temporary, reports_dir)
                self.store._fsync_directory(run_dir)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise

        artifacts = tuple(self._final_artifacts(run_dir, reports_dir))
        return FinalReportPublication(
            reports_directory=reports_dir,
            complete_report=reports_dir / "complete_report.md",
            artifacts=artifacts,
            published_at=utc_timestamp(),
        )

    @staticmethod
    def _verify_report_tree(
        temporary: Path,
        complete_report: Path,
        final_state: dict[str, Any],
    ) -> None:
        expected = {Path("complete_report.md")}
        report_paths = {
            "market_report": Path("1_analysts/market.md"),
            "sentiment_report": Path("1_analysts/sentiment.md"),
            "news_report": Path("1_analysts/news.md"),
            "fundamentals_report": Path("1_analysts/fundamentals.md"),
            "trader_investment_plan": Path("3_trading/trader.md"),
        }
        for state_key, relative in report_paths.items():
            if final_state.get(state_key):
                expected.add(relative)
        debate = final_state.get("investment_debate_state") or {}
        for state_key, filename in {
            "bull_history": "bull.md",
            "bear_history": "bear.md",
            "judge_decision": "manager.md",
        }.items():
            if debate.get(state_key):
                expected.add(Path("2_research") / filename)
        risk = final_state.get("risk_debate_state") or {}
        for state_key, filename in {
            "aggressive_history": "aggressive.md",
            "conservative_history": "conservative.md",
            "neutral_history": "neutral.md",
        }.items():
            if risk.get(state_key):
                expected.add(Path("4_risk") / filename)
        if risk.get("judge_decision"):
            expected.add(Path("5_portfolio/decision.md"))

        if complete_report != temporary / "complete_report.md":
            raise ReportPublicationError("canonical writer returned an unexpected path")
        missing = [relative.as_posix() for relative in expected if not (temporary / relative).is_file()]
        if missing:
            raise ReportPublicationError(
                "canonical report tree is incomplete: " + ", ".join(sorted(missing))
            )

    @staticmethod
    def _fsync_tree(root: Path) -> None:
        directories = []
        for current, dirnames, filenames in os.walk(root):
            current_path = Path(current)
            directories.append(current_path)
            for filename in filenames:
                with (current_path / filename).open("rb") as handle:
                    os.fsync(handle.fileno())
        for directory in reversed(directories):
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @staticmethod
    def _final_artifacts(run_dir: Path, reports_dir: Path):
        for path in sorted(reports_dir.rglob("*")):
            if not path.is_file():
                continue
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            yield ArtifactRef(
                artifact_id=f"report-final:{digest}",
                kind="report-final",
                media_type="text/markdown",
                content_sha256=digest,
                byte_size=len(content),
                locator=path.relative_to(run_dir).as_posix(),
            )

