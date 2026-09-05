from datetime import date, datetime, timezone

from tradingagents.research_platform.agent_contracts import (
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)
from tradingagents.research_platform.research_report import ResearchReportBundle
from tradingagents.research_platform.run_archive import JsonResearchRunArchive


def _bundle(*, generated_at: datetime) -> ResearchReportBundle:
    return ResearchReportBundle(
        symbol="NVDA",
        as_of_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        generated_at=generated_at,
        signal=TradeSignal(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            direction=TradeDirection.BUY,
            horizon=TradeHorizon.MEDIUM,
            confidence=0.8,
            rationale="Fixture signal.",
            proposed_position_pct=0.05,
        ),
    )


def test_json_run_archive_saves_and_loads_latest_bundle(tmp_path):
    archive = JsonResearchRunArchive(tmp_path)
    older = archive.save_bundle(_bundle(generated_at=datetime(2026, 1, 5, 9, tzinfo=timezone.utc)))
    newer = archive.save_bundle(_bundle(generated_at=datetime(2026, 1, 5, 10, tzinfo=timezone.utc)))

    runs = archive.list_runs("NVDA")
    bundle = archive.load_latest_bundle("NVDA")

    assert [run.run_id for run in runs] == [newer.run_id, older.run_id]
    assert runs[0].has_signal is True
    assert bundle is not None
    assert bundle.generated_at == datetime(2026, 1, 5, 10, tzinfo=timezone.utc)
    assert bundle.signal is not None
    assert bundle.signal.direction == TradeDirection.BUY
    assert archive.load_bundle("NVDA", newer.run_id) == bundle
    assert archive.load_bundle("NVDA", "../outside") is None


def test_json_run_archive_ignores_corrupt_bundle_files(tmp_path):
    archive = JsonResearchRunArchive(tmp_path)
    directory = tmp_path / "runs" / "NVDA"
    directory.mkdir(parents=True)
    (directory / "broken.json").write_text("not-json", encoding="utf-8")

    assert archive.list_runs("NVDA") == []
    assert archive.load_latest_bundle("NVDA") is None
