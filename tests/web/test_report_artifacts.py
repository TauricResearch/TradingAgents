from datetime import datetime, timezone
from pathlib import Path

import pytest

from tradingagents.observability.events import RunEventDraft
from tradingagents.web.reports import ReportArtifactWriter, ReportPublicationError
from tradingagents.web.run_models import RunSnapshot
from tradingagents.web.store import RunStore, RunStoreError


def _state():
    return {
        "market_report": "MKT",
        "fundamentals_report": "FUND",
        "investment_debate_state": {
            "bull_history": "BULL",
            "bear_history": "BEAR",
            "judge_decision": "RESEARCH",
        },
        "trader_investment_plan": "TRADE",
        "risk_debate_state": {
            "aggressive_history": "AGG",
            "neutral_history": "NEUTRAL",
            "conservative_history": "CONSERVATIVE",
            "judge_decision": "PORTFOLIO",
        },
    }


def _store_and_run(tmp_path):
    store = RunStore(tmp_path)
    snapshot = RunSnapshot.create(ticker="AAPL", analysis_date="2026-07-17")
    store.create_run(snapshot)
    return store, snapshot


def _completed_draft(run_id, publication):
    complete = [
        artifact
        for artifact in publication.artifacts
        if artifact.locator == "reports/complete_report.md"
    ]
    assert len(complete) == 1
    timestamp = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    return RunEventDraft(
        run_id,
        "run.completed",
        {
            "run_status": "completed",
            "summary": "done",
            "final_signal": "Hold",
            "final_report_artifact_id": complete[0].artifact_id,
            "completed_at": "2026-07-22T09:30:00.000Z",
            "degraded_data_sources": [],
        },
        timestamp=timestamp,
    )


def test_partial_report_revisions_are_monotonic_content_addressed_and_immutable(tmp_path):
    store, snapshot = _store_and_run(tmp_path)
    writer = ReportArtifactWriter(store)

    first = writer.write_revision(snapshot.run_id, "market", "first")
    second = writer.write_revision(snapshot.run_id, "market", "second")

    assert first.revision == 1
    assert second.revision == 2
    assert first.artifact.content_sha256 != second.artifact.content_sha256
    assert (tmp_path / snapshot.run_id / first.artifact.locator).read_text() == "first"
    assert (tmp_path / snapshot.run_id / second.artifact.locator).read_text() == "second"
    assert not (tmp_path / snapshot.run_id / "reports").exists()


def test_retryable_report_promotion_reuses_identical_revision(tmp_path):
    store, snapshot = _store_and_run(tmp_path)
    writer = ReportArtifactWriter(store)

    first = writer.write_revision_once(snapshot.run_id, "market", "same content")
    retried = writer.write_revision_once(snapshot.run_id, "market", "same content")

    assert retried == first
    revision_dir = tmp_path / snapshot.run_id / "report-revisions" / "market"
    assert len(list(revision_dir.iterdir())) == 1


def test_content_addressed_report_is_readable_across_multiple_report_kinds(tmp_path):
    store, snapshot = _store_and_run(tmp_path)
    writer = ReportArtifactWriter(store)

    market = writer.write_revision_once(snapshot.run_id, "market", "shared")
    news = writer.write_revision_once(snapshot.run_id, "news", "shared")

    assert market.artifact.artifact_id == news.artifact.artifact_id
    assert store.read_artifact(snapshot.run_id, market.artifact.artifact_id) == b"shared"


def test_run_completed_is_rejected_until_atomic_final_tree_exists(tmp_path):
    store, snapshot = _store_and_run(tmp_path)

    with pytest.raises(RunStoreError, match="canonical report tree"):
        store.append_event(
            RunEventDraft(
                snapshot.run_id,
                "run.completed",
                {"run_status": "completed", "summary": "done"},
            )
        )

    assert store.read_events(snapshot.run_id) == []


def test_final_publication_uses_canonical_tree_then_allows_completion(tmp_path):
    store, snapshot = _store_and_run(tmp_path)
    writer = ReportArtifactWriter(store)

    publication = writer.publish_final(snapshot.run_id, _state(), "AAPL")
    completed = store.append_event(_completed_draft(snapshot.run_id, publication))

    assert publication.complete_report.is_file()
    assert "Trading Analysis Report: AAPL" in publication.complete_report.read_text()
    assert (publication.reports_directory / "1_analysts/market.md").read_text() == "MKT"
    assert (publication.reports_directory / "5_portfolio/decision.md").read_text() == "PORTFOLIO"
    assert all(ref.locator.startswith("reports/") for ref in publication.artifacts)
    complete_artifact = next(
        artifact
        for artifact in publication.artifacts
        if artifact.locator == "reports/complete_report.md"
    )
    assert store.read_artifact(snapshot.run_id, complete_artifact.artifact_id) == (
        publication.complete_report.read_bytes()
    )
    assert completed.type == "run.completed"
    final_snapshot = store.read_snapshot(snapshot.run_id)
    assert final_snapshot.status == "completed"
    assert final_snapshot.final_report_artifact_id == next(
        artifact.artifact_id
        for artifact in publication.artifacts
        if artifact.locator == "reports/complete_report.md"
    )
    assert final_snapshot.completed_at == completed.timestamp
    assert final_snapshot.degraded_data_sources == ()
    with pytest.raises(ReportPublicationError, match="already published"):
        writer.publish_final(snapshot.run_id, _state(), "AAPL")


def test_writer_failure_keeps_partial_revisions_and_never_exposes_reports(
    tmp_path,
    monkeypatch,
):
    from tradingagents.web import reports as report_module

    store, snapshot = _store_and_run(tmp_path)
    writer = ReportArtifactWriter(store)
    partial = writer.write_revision(snapshot.run_id, "fundamentals", "partial")

    def fail_after_partial(_state, _ticker, destination):
        Path(destination).mkdir(parents=True)
        (Path(destination) / "complete_report.md").write_text("incomplete")
        raise RuntimeError("writer failed")

    monkeypatch.setattr(report_module, "write_report_tree", fail_after_partial)

    with pytest.raises(RuntimeError, match="writer failed"):
        writer.publish_final(snapshot.run_id, _state(), "AAPL")

    run_dir = tmp_path / snapshot.run_id
    assert (run_dir / partial.artifact.locator).read_text() == "partial"
    assert not (run_dir / "reports").exists()
    assert list(run_dir.glob(".reports.*.tmp")) == []


def test_failed_run_retains_partial_report_without_false_final_tree(tmp_path):
    store, snapshot = _store_and_run(tmp_path)
    writer = ReportArtifactWriter(store)
    partial = writer.write_revision(snapshot.run_id, "news", "useful partial")

    store.append_event(
        RunEventDraft(
            snapshot.run_id,
            "run.failed",
            {"run_status": "failed", "summary": "provider error"},
        )
    )

    run_dir = tmp_path / snapshot.run_id
    assert (run_dir / partial.artifact.locator).is_file()
    assert not (run_dir / "reports").exists()
    assert store.read_snapshot(snapshot.run_id).status == "failed"
