from __future__ import annotations

import os
import sqlite3
import uuid

import pytest

from tradingagents.domain import (
    EvidenceField,
    SourceObservation,
    TrustAssessment,
    UsageRecord,
)
from tradingagents.persistence import BackupService, Database, MigrationError, Repository
from tradingagents.persistence.database import MIGRATIONS
from tradingagents.persistence.repository import utc_now


def test_empty_database_migrates_to_current_version(tmp_path):
    database = Database(tmp_path / "workspace.sqlite3")
    assert database.migrate() == 5
    with database.connect() as conn:
        assert [row[0] for row in conn.execute("SELECT version FROM schema_migrations")] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("old_version", [1, 2, 3, 4])
def test_every_prior_version_migrates_forward(tmp_path, old_version):
    path = tmp_path / f"v{old_version}.sqlite3"
    Database(path, migrations=MIGRATIONS[:old_version]).migrate()
    assert Database(path).migrate() == 5


def test_failed_migration_rolls_back_schema_and_version(tmp_path):
    path = tmp_path / "rollback.sqlite3"

    def broken(conn):
        conn.execute("CREATE TABLE must_rollback(id INTEGER)")
        raise RuntimeError("synthetic migration failure")

    database = Database(path, migrations=(MIGRATIONS[0], (2, broken)))
    with pytest.raises(MigrationError, match="Migration 2 failed"):
        database.migrate()
    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations")]
    assert "must_rollback" not in tables
    assert versions == [1]


def test_repository_round_trip_for_phase_two_records(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    job = repository.create_job({"symbol": "SPY", "analysis_date": "2026-07-21"})
    repository.update_job(job.id, "running", started_at=utc_now())
    first = repository.append_event(job.id, "analysis.started", {"symbol": "SPY"})
    assert first.event_id == 1
    report = repository.create_report(job.id, {"final_trade_decision": "Hold"}, "# Report")
    trust_id = str(uuid.uuid4())
    observation = SourceObservation(
        str(uuid.uuid4()), job.id, None, "yahoo_finance", "SPY",
        utc_now(), None, "2026-07-21", "a" * 64, "miss",
    )
    repository.add_observation(observation)
    evidence = EvidenceField(
        "currency", "USD", None, observation.id, "SPY", observation.retrieved_at,
        None, observation.effective_at, observation.raw_hash, "fresh",
    )
    trust = TrustAssessment(
        trust_id, job.id, None, "trusted", True, (), (), utc_now(), (evidence,),
    )
    repository.add_trust(trust)
    advice = repository.create_advice(
        report.id, action="hold", confidence="medium", reason="Measured evidence",
        eligibility="executable", trust_assessment_id=trust_id,
    )
    repository.update_job(job.id, "completed", report_id=report.id, advice_id=advice.id)
    conversation = repository.create_conversation(report.id)
    message = repository.add_message(conversation.id, "user", "What changed?")
    usage = UsageRecord(
        str(uuid.uuid4()), job.id, conversation.id, "demo", "demo", 1, 10, 5, 0,
        12, "completed", None, utc_now(),
    )
    repository.add_usage(usage)

    restored = repository.get_job(job.id)
    assert restored and restored.report_id == report.id and restored.advice_id == advice.id
    assert repository.list_events(job.id)[0].data == {"symbol": "SPY"}
    assert repository.get_report_for_job(job.id) == report
    assert repository.list_advice(report.id) == [advice]
    assert repository.get_conversation(conversation.id)[1] == [message]
    assert repository.list_usage(job_id=job.id) == [usage]
    assert repository.list_observations(job_id=job.id) == [observation]
    assert repository.latest_trust(job_id=job.id) == trust


def test_backup_restore_round_trip_and_preview_rejections(tmp_path):
    path = tmp_path / "state" / "workspace.sqlite3"
    repository = Repository(Database(path))
    original = repository.create_job({"symbol": "SPY"})
    backups = BackupService(repository.database)
    created = backups.create()
    assert created.valid and created.compatible and created.schema_version == 5

    repository.create_job({"symbol": "AAPL"})
    backups.restore(created.backup_id)
    assert [job.id for job in repository.list_jobs()] == [original.id]

    corrupt_id = str(uuid.uuid4())
    (backups.backup_dir / f"{corrupt_id}.sqlite3").write_bytes(b"not sqlite")
    corrupt = backups.preview(corrupt_id)
    assert not corrupt.valid and corrupt.reason == "CORRUPT_OR_INCOMPLETE"
    with pytest.raises(ValueError, match="INVALID_BACKUP_ID"):
        backups.preview("../../outside")


def test_china_fund_snapshot_and_advice_round_trip(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    snapshot = {
        "identity": {"code": "003516", "display_name": "国泰融安多策略灵活配置混合A"},
        "analysis_date": "2026-07-25",
        "retrieved_at": utc_now(),
        "trust": {"level": "trusted", "critical_ready": True},
        "warnings": [],
    }
    persisted = repository.save_china_fund_snapshot(snapshot)
    assert repository.latest_china_fund_snapshot("003516")["snapshot"] == snapshot

    first = repository.create_china_fund_advice(
        persisted["id"],
        "003516",
        {"action": "hold", "confidence": "high", "reason": "Current", "executable": True},
    )
    second = repository.create_china_fund_advice(
        persisted["id"],
        "003516",
        {"action": "subscribe", "confidence": "medium", "reason": "Open", "executable": True},
        parent_id=first["id"],
    )
    assert second["version"] == 2 and second["parent_id"] == first["id"]
    assert repository.list_china_fund_advice("003516") == [first, second]


def test_backup_list_is_newest_first(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    backups = BackupService(repository.database)
    first = backups.create()
    second = backups.create()
    first_path = backups.backup_dir / f"{first.backup_id}.sqlite3"
    second_path = backups.backup_dir / f"{second.backup_id}.sqlite3"
    os.utime(second_path, (100, 100))
    os.utime(first_path, (200, 200))
    assert [item.backup_id for item in backups.list()][:2] == [first.backup_id, second.backup_id]


def test_newer_schema_backup_is_rejected(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    backups = BackupService(repository.database)
    created = backups.create()
    backup_path = backups.backup_dir / f"{created.backup_id}.sqlite3"
    with sqlite3.connect(backup_path) as conn:
        conn.execute("INSERT INTO schema_migrations(version) VALUES (999)")
    preview = backups.preview(created.backup_id)
    assert preview.valid and not preview.compatible and preview.reason == "SCHEMA_TOO_NEW"


def test_active_jobs_become_interrupted(tmp_path):
    repository = Repository(Database(tmp_path / "workspace.sqlite3"))
    jobs = [repository.create_job({"symbol": symbol}) for symbol in ("A", "B", "C")]
    repository.update_job(jobs[0].id, "running")
    repository.update_job(jobs[1].id, "cancelling")
    repository.update_job(jobs[2].id, "completed")
    assert repository.interrupt_active_jobs() == 2
    assert [repository.get_job(job.id).status for job in jobs] == ["interrupted", "interrupted", "completed"]
