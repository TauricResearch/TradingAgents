"""The ledger is the trader's core: it imports no feature module, keeps the file in
WAL mode so the web API's readers and the jobs' writers do not wait on each other,
and indexes what its queries filter on."""

import sqlite3
import subprocess
import sys

import pytest

from tests.test_trader_paper import BTC, T0
from trader.ledger import SCHEMA, Ledger

INDEXES = {"fills_ts", "attempts_ts", "attempts_trade_date_coin", "signals_ts", "signals_coin_id"}


def test_the_ledger_imports_nothing_of_the_intraday_account():
    code = (
        "import sys, trader.ledger;"
        " print(sorted(m for m in sys.modules if m.startswith('trader.intraday')))"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "[]"


def test_a_new_ledger_is_in_wal_mode_with_its_indexes(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    assert ledger.db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    names = {row[0] for row in ledger.db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert names >= INDEXES


def test_an_old_ledger_switches_to_wal_and_gains_the_indexes_when_a_writer_opens_it(tmp_path):
    path = tmp_path / "ledger.sqlite"
    old = sqlite3.connect(path)
    old.executescript("\n".join(line for line in SCHEMA.splitlines() if "CREATE INDEX" not in line))
    old.execute("INSERT INTO meta VALUES ('cash', '123.0')")
    old.commit()
    assert old.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    old.close()
    ledger = Ledger(path)
    assert ledger.db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert ledger.get("cash") == 123.0
    names = {row[0] for row in ledger.db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert names >= INDEXES


@pytest.mark.parametrize("sql, index", [
    ("SELECT ts FROM fills WHERE ts >= 1 ORDER BY ts, id", "fills_ts"),
    ("SELECT ts, cost_usd FROM attempts WHERE ts >= 1 ORDER BY ts", "attempts_ts"),
    (
        "SELECT rating, error FROM attempts WHERE trade_date = 'd' AND coin = 'c' ORDER BY id",
        "attempts_trade_date_coin",
    ),
    ("SELECT ts FROM signals WHERE ts >= 1 ORDER BY ts DESC, id DESC LIMIT 5", "signals_ts"),
    ("SELECT MAX(id) FROM signals GROUP BY coin", "signals_coin_id"),
])
def test_the_queries_use_their_indexes(tmp_path, sql, index):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    plan = " ".join(row[-1] for row in ledger.db.execute(f"EXPLAIN QUERY PLAN {sql}"))
    assert index in plan, plan


def test_a_reader_reads_a_wal_ledger_while_a_writer_holds_a_transaction(tmp_path):
    path = tmp_path / "ledger.sqlite"
    writer = Ledger(path)
    writer.initialize(10_000.0, T0)
    reader = Ledger(path, readonly=True)
    assert reader.db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    with writer.transaction():
        writer.record_attempt("2026-01-09", BTC.research, T0, rating="Buy", error=None)
        assert reader.get("cash") == 10_000.0  # the write in flight does not block it
        assert reader.attempts("2026-01-09", BTC.research) == []  # nor is it seen yet
    assert reader.attempts("2026-01-09", BTC.research) == [("Buy", None)]
    writer.db.close()
    # With the writer gone (and the WAL checkpointed into the file) the reader still reads.
    assert Ledger(path, readonly=True).get("cash") == 10_000.0
