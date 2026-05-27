import pytest
from tradingagents.persistence.db import connect, schema_tables


@pytest.mark.unit
def test_f3_tables_present(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    rows = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"ingest_cursor", "tickers", "event_fingerprints",
            "event_embeddings"} <= rows


@pytest.mark.unit
def test_expected_tables_set_includes_f3():
    assert {"ingest_cursor", "tickers", "event_fingerprints",
            "event_embeddings"} <= schema_tables()


@pytest.mark.unit
def test_event_fingerprints_pk_is_composite(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    cols = list(conn.execute("PRAGMA table_info(event_fingerprints)"))
    pk_cols = [c[1] for c in cols if c[5] > 0]
    assert set(pk_cols) == {"fingerprint", "kind"}


@pytest.mark.unit
def test_tickers_active_index(tmp_path):
    conn = connect(str(tmp_path / "iic.db"))
    idx_names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )]
    assert "idx_tickers_active" in idx_names


@pytest.mark.unit
def test_status_enum_comment_extended_with_duplicate():
    from pathlib import Path
    text = Path("tradingagents/persistence/schema.sql").read_text()
    # Status comment line for `events.status` now documents the four-value enum.
    assert '"new" | "triaged" | "discarded" | "duplicate"' in text
