"""python -m trader backup: a consistent copy of the account directory (Issue #15)."""

import sqlite3
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from tests.test_trader_paper import BTC, T0
from trader import __main__ as cli
from trader.backup import backup
from trader.ledger import Ledger

WHEN = datetime(2026, 1, 10, 8, 30, tzinfo=UTC)


def test_the_copy_holds_what_was_committed_while_a_writer_is_mid_transaction(tmp_path):
    home, dest = tmp_path / "home", tmp_path / "backups"
    writer = Ledger(home / "ledger.sqlite")
    writer.initialize(10_000.0, T0)
    writer.record_attempt("2026-01-09", BTC.research, T0, rating="Buy", error=None)
    with writer.transaction():
        writer.record_attempt("2026-01-09", BTC.research, T0 + 1, rating="Sell", error=None)
        target, copied = backup(home, dest, now=WHEN)  # returns: the writer did not block it
    assert target == dest / "20260110T083000Z"
    assert [rel for rel, _ in copied] == ["ledger.sqlite"]
    assert [p.name for p in target.iterdir()] == ["ledger.sqlite"]  # one file, nothing pending
    copy = sqlite3.connect(target / "ledger.sqlite")
    assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert copy.execute("PRAGMA journal_mode").fetchone() == ("delete",)  # self-contained
    assert copy.execute("SELECT rating FROM attempts ORDER BY id").fetchall() == [("Buy",)]
    copy.close()
    assert Ledger(target / "ledger.sqlite", readonly=True).get("cash") == 10_000.0
    assert writer.attempts("2026-01-09", BTC.research) == [("Buy", None), ("Sell", None)]
    with pytest.raises(FileExistsError):  # a backup is never overwritten
        backup(home, dest, now=WHEN)


def test_both_accounts_settings_and_memory_are_copied_and_the_logs_only_when_asked(tmp_path):
    home, dest = tmp_path / "home", tmp_path / "backups"
    Ledger(home / "ledger.sqlite").initialize(10_000.0, T0)
    Ledger(home / "intraday" / "ledger.sqlite").initialize(5_000.0, T0)
    (home / "settings.json").write_text('{"llm": {}}')
    (home / "memory").mkdir()
    (home / "memory" / "trading_memory.md").write_text("# memory\n")
    (home / "logs" / "BTC-USD").mkdir(parents=True)
    (home / "logs" / "BTC-USD" / "full_states_log_2026-01-09.json").write_text("{}")

    target, copied = backup(home, dest, now=WHEN)
    assert [rel for rel, _ in copied] == [
        "ledger.sqlite", "intraday/ledger.sqlite", "settings.json", "memory",
    ]
    assert Ledger(target / "intraday" / "ledger.sqlite", readonly=True).get("cash") == 5_000.0
    assert (target / "settings.json").read_text() == '{"llm": {}}'
    assert (target / "memory" / "trading_memory.md").read_text() == "# memory\n"
    assert not (target / "logs").exists()
    assert dict(copied)["memory"] == len("# memory\n")

    target, copied = backup(home, dest, with_logs=True, now=WHEN.replace(minute=31))
    assert [rel for rel, _ in copied][-1] == "logs"
    assert (target / "logs" / "BTC-USD" / "full_states_log_2026-01-09.json").read_text() == "{}"


def test_the_command_names_the_copy_and_what_it_skipped(tmp_path, monkeypatch):
    home, dest = tmp_path / "home", tmp_path / "backups" / "nested"
    Ledger(home / "ledger.sqlite").initialize(10_000.0, T0)
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("TRADER_HOME", str(home))
    result = CliRunner().invoke(cli.app, ["backup", str(dest)])
    assert result.exit_code == 0, result.output
    assert result.output.startswith(f"已备份到 {dest}/")
    assert "  ledger.sqlite  " in result.output and "没有日内账本，跳过" in result.output
    assert len(list(dest.iterdir())) == 1  # the time-stamped directory was created under DEST

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("TRADER_HOME", str(empty))
    result = CliRunner().invoke(cli.app, ["backup", str(dest)])
    assert result.exit_code == 1 and "没有可备份的账户文件" in result.output
