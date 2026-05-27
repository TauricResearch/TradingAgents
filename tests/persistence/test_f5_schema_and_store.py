import sqlite3
import pytest

from tradingagents.persistence.db import connect as iic_connect


@pytest.mark.unit
def test_f5_schema_adds_columns(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))

    # deliveries.skip_reason + channel_ref
    cols = {row[1] for row in conn.execute("PRAGMA table_info(deliveries)").fetchall()}
    assert "skip_reason" in cols
    assert "channel_ref" in cols

    # briefs.refine_depth + refine_overrides
    cols = {row[1] for row in conn.execute("PRAGMA table_info(briefs)").fetchall()}
    assert "refine_depth" in cols
    assert "refine_overrides" in cols


@pytest.mark.unit
def test_f5_indexes_present(tmp_path):
    conn = iic_connect(str(tmp_path / "iic.db"))
    indexes = {row[1] for row in conn.execute(
        "SELECT type, name FROM sqlite_master WHERE type='index'"
    ).fetchall()}
    assert "idx_deliveries_brief" in indexes
    assert "idx_brief_actions_pending_expires" in indexes


@pytest.mark.unit
def test_schema_is_idempotent(tmp_path):
    # Calling connect twice on the same path must not raise duplicate-column.
    p = str(tmp_path / "iic.db")
    iic_connect(p)
    iic_connect(p)
