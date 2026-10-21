"""Cancellation is always a separate, auditable operator action."""

from tradingagents.paper.cli import main, read_book, write_book
from tradingagents.paper.engine import Book


def test_cancel_pending_records_audit_and_preserves_paper_funds(tmp_path):
    path = tmp_path / "book.json"
    book = Book.new("2026-10-21")
    book.last_session = "2026-10-21"
    assert book.submit_signal("NVDA", "Overweight", 221.97, "2026-10-21")
    assert book.submit_signal("META", "Overweight", 697.52, "2026-10-21")
    write_book(path, book)
    assert main(["--state", str(path), "cancel-pending"]) == 0
    after = read_book(path)
    assert not after.orders
    assert after.equity() == 10000
    assert after.cash_gbp == 10000
    assert len([e for e in after.events if e["type"] == "ORDER_CANCELLED"]) == 2
    assert {e["ticker"] for e in after.events if e["type"] == "ORDER_CANCELLED"} == {"NVDA", "META"}
    assert len([e for e in after.events if e["type"] == "AGENT_RATING"]) == 0
    assert len([e for e in after.events if e["type"] == "ORDER_QUEUED"]) == 2


def test_cancel_pending_is_idempotent_and_does_not_touch_marked_equity(tmp_path):
    path = tmp_path / "book.json"
    book = Book.new("2026-10-21")
    book.last_session = "2026-10-21"
    write_book(path, book)
    before = path.read_bytes()
    assert main(["--state", str(path), "cancel-pending"]) == 0
    assert path.read_bytes() == before
    assert main(["--state", str(path), "cancel-pending"]) == 0
