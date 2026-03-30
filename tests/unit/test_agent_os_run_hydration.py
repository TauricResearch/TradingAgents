from agent_os.backend.main import _hydrate_run_record


def test_hydrate_run_record_marks_persisted_running_as_failed():
    record = _hydrate_run_record(
        {
            "id": "run-1",
            "type": "auto",
            "status": "running",
            "created_at": 123.0,
            "params": {"date": "2026-03-29"},
        }
    )

    assert record["status"] == "failed"
    assert record["error"] == "Run did not complete (server restarted)"
    assert record["hydrated_from_disk"] is True


def test_hydrate_run_record_keeps_terminal_statuses():
    completed = _hydrate_run_record(
        {
            "id": "run-2",
            "type": "auto",
            "status": "completed",
            "created_at": 123.0,
            "params": {"date": "2026-03-29"},
        }
    )
    failed = _hydrate_run_record(
        {
            "id": "run-3",
            "type": "auto",
            "status": "failed",
            "created_at": 123.0,
            "params": {"date": "2026-03-29"},
        }
    )

    assert completed["status"] == "completed"
    assert "error" not in completed
    assert failed["status"] == "failed"
