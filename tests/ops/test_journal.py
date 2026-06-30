import pytest
from datetime import datetime, timezone
from decimal import Decimal
from ops.journal import Journal


def test_journal_records_and_reads_event(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    j.record_event("test_kind", {"foo": "bar", "n": 1})
    events = j.read_events()
    assert len(events) == 1
    assert events[0]["kind"] == "test_kind"
    assert events[0]["payload"] == {"foo": "bar", "n": 1}
    assert isinstance(events[0]["at"], datetime)


def test_journal_records_order_and_fill(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    j.record_order(
        client_order_id="cid-1", symbol="AAPL", side="BUY",
        notional_dollars=Decimal("25.00"), stop_loss_price=Decimal("180.00"),
    )
    j.record_fill(
        order_id="oid-1", client_order_id="cid-1", symbol="AAPL", side="BUY",
        quantity=Decimal("0.1245"), price=Decimal("200.80"),
        filled_at=datetime(2026, 6, 30, 14, 30, tzinfo=timezone.utc),
    )
    orders = j.read_orders()
    fills = j.read_fills()
    assert orders[0]["symbol"] == "AAPL"
    assert orders[0]["notional_dollars"] == Decimal("25.00")
    assert fills[0]["price"] == Decimal("200.80")


def test_journal_records_equity_snapshot(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    j.record_equity_snapshot(
        at=datetime(2026, 6, 30, 13, 30, tzinfo=timezone.utc),
        equity=Decimal("250.00"), cash=Decimal("250.00"),
    )
    snaps = j.read_equity_snapshots()
    assert snaps[0]["equity"] == Decimal("250.00")


def test_record_fill_rejects_naive_datetime(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    naive = datetime(2026, 6, 30, 14, 30)
    with pytest.raises(ValueError, match="naive"):
        j.record_fill(
            order_id="oid", client_order_id="cid", symbol="AAPL", side="BUY",
            quantity=Decimal("1"), price=Decimal("100"),
            filled_at=naive,
        )


def test_record_equity_snapshot_rejects_naive_datetime(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    naive = datetime(2026, 6, 30, 13, 30)
    with pytest.raises(ValueError, match="naive"):
        j.record_equity_snapshot(at=naive, equity=Decimal("250"), cash=Decimal("250"))


def test_context_manager_closes_connection(tmp_path):
    path = str(tmp_path / "j.sqlite")
    with Journal(path) as j:
        j.record_event("k", {})
    # After exiting, a second connection should still be able to open and read
    j2 = Journal(path)
    assert len(j2.read_events()) == 1
    j2.close()
