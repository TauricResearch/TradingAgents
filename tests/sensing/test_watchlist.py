import json
import pytest
from datetime import datetime, timezone, timedelta

from tradingagents.persistence.db import connect


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "iic.db"))


@pytest.mark.unit
def test_add_user_never_expires(conn):
    from tradingagents.sensing.watchlist import add_user
    add_user(conn, ticker="AAPL")
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='AAPL'").fetchone()
    assert row["ttl_until"] is None
    assert "user" in json.loads(row["tags"])


@pytest.mark.unit
def test_auto_promote_below_threshold_no_op(conn):
    from tradingagents.sensing.watchlist import auto_promote
    n = auto_promote(conn, ticker="NVDA", event_id="e-1",
                     salience=0.5, confidence=0.95,
                     salience_threshold=0.7, confidence_threshold=0.8,
                     ttl_days=7)
    assert n == 0
    assert conn.execute("SELECT 1 FROM watchlist WHERE ticker='NVDA'").fetchone() is None


@pytest.mark.unit
def test_auto_promote_above_threshold_upserts(conn):
    from tradingagents.sensing.watchlist import auto_promote
    n = auto_promote(conn, ticker="NVDA", event_id="e-1",
                     salience=0.9, confidence=0.9,
                     salience_threshold=0.7, confidence_threshold=0.8,
                     ttl_days=7)
    assert n == 1
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='NVDA'").fetchone()
    tags = json.loads(row["tags"])
    assert "auto" in tags
    assert "event:e-1" in tags
    assert row["ttl_until"] is not None


@pytest.mark.unit
def test_auto_promote_does_not_overwrite_user_curated(conn):
    """User entry must remain ttl=None; auto must not steal control of it."""
    from tradingagents.sensing.watchlist import add_user, auto_promote
    add_user(conn, ticker="AAPL")
    auto_promote(conn, ticker="AAPL", event_id="e-2",
                 salience=0.95, confidence=0.95,
                 salience_threshold=0.7, confidence_threshold=0.8,
                 ttl_days=7)
    row = conn.execute("SELECT * FROM watchlist WHERE ticker='AAPL'").fetchone()
    assert row["ttl_until"] is None  # still user-curated
    tags = set(json.loads(row["tags"]))
    assert "user" in tags  # user tag preserved


@pytest.mark.unit
def test_sweep_removes_only_expired_auto(conn):
    from tradingagents.sensing.watchlist import add_user, auto_promote, sweep_expired
    add_user(conn, ticker="AAPL")  # never expires
    auto_promote(conn, ticker="OLD", event_id="e-old",
                 salience=0.9, confidence=0.9,
                 salience_threshold=0.7, confidence_threshold=0.8,
                 ttl_days=7)
    # Manually backdate OLD's ttl_until.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn.execute("UPDATE watchlist SET ttl_until = ? WHERE ticker='OLD'", (past,))
    conn.commit()
    auto_promote(conn, ticker="FRESH", event_id="e-fresh",
                 salience=0.9, confidence=0.9,
                 salience_threshold=0.7, confidence_threshold=0.8,
                 ttl_days=7)
    pruned = sweep_expired(conn)
    rows = [r["ticker"] for r in conn.execute("SELECT ticker FROM watchlist")]
    assert pruned == 1
    assert set(rows) == {"AAPL", "FRESH"}
