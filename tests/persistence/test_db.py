import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.mark.unit
def test_connect_creates_tables_idempotently(tmp_db):
    from tradingagents.persistence.db import connect, schema_tables

    # First call: creates the schema.
    conn = connect(tmp_db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    expected = schema_tables()
    assert expected.issubset(tables), f"missing: {expected - tables}"

    # Second call on the same path: must not error.
    conn2 = connect(tmp_db)
    tables2 = {row[0] for row in conn2.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert tables == tables2

    conn.close()
    conn2.close()


@pytest.mark.unit
def test_connect_enables_wal_mode(tmp_db):
    from tradingagents.persistence.db import connect
    conn = connect(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


@pytest.mark.unit
def test_connect_enables_foreign_keys(tmp_db):
    from tradingagents.persistence.db import connect
    conn = connect(tmp_db)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1
    conn.close()


@pytest.mark.unit
def test_vec_index_virtual_table_exists(tmp_db):
    from tradingagents.persistence.db import connect
    conn = connect(tmp_db)
    rows = list(conn.execute(
        "SELECT name FROM sqlite_master WHERE name='vec_index'"
    ))
    assert rows, "vec_index virtual table must be created at connect-time"
    conn.close()


@pytest.mark.unit
def test_concurrent_connect_does_not_race_on_vec_index(tmp_db):
    """Regression: F1's deepdive opens three connections in parallel threads.
    Two of them used to race on CREATE VIRTUAL TABLE vec_index, with the
    loser crashing as `sqlite3.OperationalError: table vec_index already
    exists`. The fix wraps the CREATE in try/except 'already exists'."""
    from concurrent.futures import ThreadPoolExecutor
    from tradingagents.persistence.db import connect

    def _open():
        c = connect(tmp_db)
        c.close()
        return True

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = [f.result() for f in [ex.submit(_open) for _ in range(8)]]

    assert all(results), "every concurrent connect() must succeed"
