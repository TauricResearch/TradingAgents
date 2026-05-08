import json

from gui import storage


def test_write_run_error_log_persists_traceback_and_recent_events(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "gui.db")
    storage.init_db()
    storage.create_run(
        run_id="run-123",
        ticker="SPY",
        trade_date="2026-05-08",
        provider="openai",
        deep_model="gpt-5.4",
        quick_model="gpt-5.4-mini",
        debate_rounds=1,
        risk_rounds=1,
        vendors={"news_data": "yfinance"},
    )

    path = storage.write_run_error_log(
        run_id="run-123",
        meta={"ticker": "SPY", "trade_date": "2026-05-08", "llm_provider": "openai"},
        message="Server disconnected without sending a response.",
        traceback_text="Traceback details",
        events=[{"type": "start"}, {"type": "error", "message": "boom"}],
    )
    storage.finalize_run(
        "run-123",
        decision=None,
        log_path=None,
        error="Server disconnected without sending a response.",
        error_log_path=str(path),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    row = storage.get_run("run-123")

    assert payload["kind"] == "tradingagents-gui-error"
    assert payload["message"] == "Server disconnected without sending a response."
    assert payload["traceback"] == "Traceback details"
    assert payload["metadata"]["ticker"] == "SPY"
    assert [event["type"] for event in payload["recent_events"]] == ["start", "error"]
    assert row is not None
    assert row["error_log_path"] == str(path)


def test_init_db_migrates_error_log_path_column(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "gui.db")
    storage.init_db()

    row = storage.get_run("missing")

    assert row is None
    with storage._conn() as conn:
        columns = {info["name"] for info in conn.execute("PRAGMA table_info(runs)").fetchall()}
    assert "error_log_path" in columns
