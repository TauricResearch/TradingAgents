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


def test_hydrate_run_record_strips_stray_auto_ticker_params():
    record = _hydrate_run_record(
        {
            "id": "run-4",
            "type": "auto",
            "status": "completed",
            "created_at": 123.0,
            "params": {"date": "2026-03-29", "ticker": "msft", "max_tickers": 5},
        }
    )

    assert record["params"] == {"date": "2026-03-29", "max_tickers": 5}


def test_hydrate_run_record_drops_noncanonical_mock_auto_ticker():
    record = _hydrate_run_record(
        {
            "id": "run-5",
            "type": "mock",
            "status": "completed",
            "created_at": 123.0,
            "params": {
                "date": "2026-03-29",
                "mock_type": "auto",
                "ticker": "aapl, nvda , tsla",
                "speed": 3,
            },
        }
    )

    assert record["params"] == {
        "date": "2026-03-29",
        "mock_type": "auto",
        "speed": 3,
    }
