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
