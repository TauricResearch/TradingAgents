"""Tests for the SQLite history database.

Uses a temp-file DB per test to avoid cross-test contamination.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from desktop.state.database import AnalysisRow, HistoryDB, LogEntryRow


@pytest.fixture
def db(tmp_path: Path) -> HistoryDB:
    """Create a fresh HistoryDB in a temp directory."""
    return HistoryDB(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSchema:
    def test_tables_created(self, db: HistoryDB) -> None:
        conn = db._connect()
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            names = [r["name"] for r in tables]
            assert "analyses" in names
            assert "settings" in names
        finally:
            conn.close()

    def test_wal_mode_enabled(self, db: HistoryDB) -> None:
        conn = db._connect()
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_idempotent_schema_creation(self, tmp_path: Path) -> None:
        """Creating HistoryDB twice on the same file must not error."""
        path = tmp_path / "reuse.db"
        HistoryDB(db_path=path)
        HistoryDB(db_path=path)  # No exception


# ---------------------------------------------------------------------------
# Analyses CRUD
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalysesCRUD:
    def test_insert_and_get(self, db: HistoryDB) -> None:
        row_id = db.insert_analysis(
            ticker="AAPL",
            date="2026-05-14",
            provider="anthropic",
            model="claude-opus-4-20250514",
            config={"max_debate_rounds": 2},
            result_dir="/tmp/results/AAPL",
            selected_analysts=["market", "news"],
        )
        assert row_id >= 1

        analysis = db.get_analysis(row_id)
        assert analysis is not None
        assert analysis.ticker == "AAPL"
        assert analysis.date == "2026-05-14"
        assert analysis.provider == "anthropic"
        assert analysis.model == "claude-opus-4-20250514"
        assert analysis.status == "running"
        assert analysis.started_at is not None
        assert analysis.completed_at is None
        assert analysis.error_text is None
        assert analysis.selected_analysts == "market,news"

        config = json.loads(analysis.config_json)
        assert config["max_debate_rounds"] == 2

    def test_get_nonexistent_returns_none(self, db: HistoryDB) -> None:
        assert db.get_analysis(9999) is None

    def test_mark_completed(self, db: HistoryDB) -> None:
        row_id = db.insert_analysis(
            ticker="SPY", date="2026-01-01", provider="openai", model="gpt-4o"
        )
        db.mark_completed(row_id)

        analysis = db.get_analysis(row_id)
        assert analysis is not None
        assert analysis.status == "completed"
        assert analysis.completed_at is not None

    def test_mark_failed(self, db: HistoryDB) -> None:
        row_id = db.insert_analysis(
            ticker="SPY", date="2026-01-01", provider="openai", model="gpt-4o"
        )
        db.mark_failed(row_id, "API rate limit exceeded")

        analysis = db.get_analysis(row_id)
        assert analysis is not None
        assert analysis.status == "failed"
        assert analysis.error_text == "API rate limit exceeded"
        assert analysis.completed_at is not None

    def test_mark_interrupted(self, db: HistoryDB) -> None:
        row_id = db.insert_analysis(
            ticker="SPY", date="2026-01-01", provider="openai", model="gpt-4o"
        )
        db.mark_interrupted(row_id)

        analysis = db.get_analysis(row_id)
        assert analysis is not None
        assert analysis.status == "interrupted"

    def test_update_result_dir(self, db: HistoryDB) -> None:
        row_id = db.insert_analysis(
            ticker="TSLA", date="2026-03-01", provider="google", model="gemini-2.5"
        )
        db.update_result_dir(row_id, "/home/user/results/TSLA_20260301")

        analysis = db.get_analysis(row_id)
        assert analysis is not None
        assert analysis.result_dir == "/home/user/results/TSLA_20260301"

    def test_list_analyses_default_order(self, db: HistoryDB) -> None:
        """Newest first."""
        id1 = db.insert_analysis(
            ticker="AAA", date="2026-01-01", provider="x", model="m"
        )
        id2 = db.insert_analysis(
            ticker="BBB", date="2026-01-02", provider="x", model="m"
        )

        rows = db.list_analyses()
        assert len(rows) == 2
        assert rows[0].id == id2  # newest first
        assert rows[1].id == id1

    def test_list_analyses_filter_by_ticker(self, db: HistoryDB) -> None:
        db.insert_analysis(ticker="AAPL", date="2026-01-01", provider="x", model="m")
        db.insert_analysis(ticker="TSLA", date="2026-01-02", provider="x", model="m")

        rows = db.list_analyses(ticker="AAPL")
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"

    def test_list_analyses_filter_by_status(self, db: HistoryDB) -> None:
        id1 = db.insert_analysis(ticker="A", date="d", provider="x", model="m")
        id2 = db.insert_analysis(ticker="B", date="d", provider="x", model="m")
        db.mark_completed(id1)

        rows = db.list_analyses(status="completed")
        assert len(rows) == 1
        assert rows[0].status == "completed"

    def test_list_analyses_pagination(self, db: HistoryDB) -> None:
        for i in range(5):
            db.insert_analysis(ticker=f"T{i}", date="d", provider="x", model="m")

        page1 = db.list_analyses(limit=2, offset=0)
        page2 = db.list_analyses(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    def test_count_analyses(self, db: HistoryDB) -> None:
        db.insert_analysis(ticker="A", date="d", provider="x", model="m")
        db.insert_analysis(ticker="B", date="d", provider="x", model="m")
        assert db.count_analyses() == 2
        assert db.count_analyses(ticker="A") == 1

    def test_analysis_row_is_frozen(self, db: HistoryDB) -> None:
        row_id = db.insert_analysis(
            ticker="X", date="d", provider="p", model="m"
        )
        analysis = db.get_analysis(row_id)
        assert analysis is not None
        with pytest.raises(AttributeError):
            analysis.ticker = "Y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSettingsCRUD:
    def test_set_and_get(self, db: HistoryDB) -> None:
        db.set_setting("default_provider", "anthropic")
        assert db.get_setting("default_provider") == "anthropic"

    def test_get_missing_returns_default(self, db: HistoryDB) -> None:
        assert db.get_setting("nonexistent") is None
        assert db.get_setting("nonexistent", "fallback") == "fallback"

    def test_upsert(self, db: HistoryDB) -> None:
        db.set_setting("key", "v1")
        db.set_setting("key", "v2")
        assert db.get_setting("key") == "v2"

    def test_get_all_settings(self, db: HistoryDB) -> None:
        db.set_setting("a", "1")
        db.set_setting("b", "2")

        settings = db.get_all_settings()
        assert settings == {"a": "1", "b": "2"}

    def test_delete_setting(self, db: HistoryDB) -> None:
        db.set_setting("temp", "value")
        db.delete_setting("temp")
        assert db.get_setting("temp") is None

    def test_delete_nonexistent_no_error(self, db: HistoryDB) -> None:
        db.delete_setting("does_not_exist")  # No exception


# ---------------------------------------------------------------------------
# Log entries CRUD
# ---------------------------------------------------------------------------


@pytest.fixture
def analysis_id(db: HistoryDB) -> int:
    """Insert a dummy analysis and return its ID."""
    return db.insert_analysis(
        ticker="TEST", date="2026-01-01", provider="test", model="m"
    )


@pytest.mark.unit
class TestLogEntriesCRUD:
    def test_flush_and_read(self, db: HistoryDB, analysis_id: int) -> None:
        messages = [
            ("2026-01-01T10:00:01", "System", "Pipeline started"),
            ("2026-01-01T10:00:02", "Agent", "Market Analyst working"),
        ]
        tool_calls = [
            ("2026-01-01T10:00:03", "get_stock_data", {"ticker": "TEST"}),
        ]
        count = db.flush_logs(analysis_id, messages, tool_calls)
        assert count == 3

        entries = db.get_log_entries(analysis_id)
        assert len(entries) == 3
        assert all(isinstance(e, LogEntryRow) for e in entries)
        # Chronological order
        assert entries[0].content == "Pipeline started"
        assert entries[1].content == "Market Analyst working"
        assert entries[2].entry_type == "Tool"
        assert "get_stock_data" in entries[2].content

    def test_flush_empty(self, db: HistoryDB, analysis_id: int) -> None:
        count = db.flush_logs(analysis_id, [], [])
        assert count == 0
        assert db.get_log_entries(analysis_id) == []

    def test_filter_by_type(self, db: HistoryDB, analysis_id: int) -> None:
        messages = [
            ("2026-01-01T10:00:01", "System", "msg1"),
            ("2026-01-01T10:00:02", "Error", "something broke"),
            ("2026-01-01T10:00:03", "System", "msg2"),
        ]
        db.flush_logs(analysis_id, messages, [])

        errors = db.get_log_entries(analysis_id, entry_type="Error")
        assert len(errors) == 1
        assert errors[0].content == "something broke"

        systems = db.get_log_entries(analysis_id, entry_type="System")
        assert len(systems) == 2

    def test_count_log_entries(self, db: HistoryDB, analysis_id: int) -> None:
        assert db.count_log_entries(analysis_id) == 0
        messages = [("ts", "Agent", f"msg{i}") for i in range(5)]
        db.flush_logs(analysis_id, messages, [])
        assert db.count_log_entries(analysis_id) == 5

    def test_long_args_truncated(self, db: HistoryDB, analysis_id: int) -> None:
        long_args = "x" * 1000
        tool_calls = [("ts", "tool_name", long_args)]
        db.flush_logs(analysis_id, [], tool_calls)

        entries = db.get_log_entries(analysis_id)
        assert len(entries) == 1
        assert len(entries[0].content) < 600  # truncated to ~500 + tool name

    def test_log_entry_row_is_frozen(self, db: HistoryDB, analysis_id: int) -> None:
        db.flush_logs(analysis_id, [("ts", "System", "msg")], [])
        entry = db.get_log_entries(analysis_id)[0]
        with pytest.raises(AttributeError):
            entry.content = "mutated"  # type: ignore[misc]

    def test_schema_includes_log_entries(self, db: HistoryDB) -> None:
        conn = db._connect()
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            names = [r["name"] for r in tables]
            assert "log_entries" in names
        finally:
            conn.close()
