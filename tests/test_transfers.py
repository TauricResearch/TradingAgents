"""Money a person moves into an account on the exchange or out of it (#40).

A transfer is no PnL: the sync books it apart from the fills and the funding, it buys
or sells the account's units at the equity per unit of the moment
(``trader.ledger.Snapshot``), and the peak grows with the units. The drawdown, the kill
switch and the returns then see the trading alone, and the reports name the transfers
beside it. A bill the sync does not take for a transfer still pauses the account
(ADR 0010); so does a transfer that leaves the account empty, or finds it so.

The account opens at 23:30 with 10,000 USDT (``Env``); 10 contracts are 0.1 BTC."""

import sqlite3

import pytest

from tests.test_demo_account import BTC, HOUR, HOUR_ID
from tests.test_demo_job import Env
from tests.test_trader_paper import DAY0
from trader import rules
from trader.demo import report
from trader.intraday.paper import HOUR_MS
from trader.ledger import Ledger, Snapshot
from trader.okx import DAY_MS
from trader.okx_private import TRANSFER_BILL, Bill

MINUTE = 60_000


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def bought(env, contracts, at):
    """The program's order fills on the exchange at ``at``, at 80,000."""
    env.exchange.now = at
    env.exchange._fill(BTC.swap, contracts, f"trd{HOUR_ID}btc")


def marked(env, price):
    env.exchange.mark[BTC.swap] = env.exchange.prices[BTC.swap] = price


def moved(env, amount, at):
    env.exchange.now = at
    env.exchange.transfer(amount)


def synced(env, now):
    env.exchange.now = now
    return env.account.sync(now)


def drawdown(env):
    return rules.drawdown(env.ledger.get("equity"), env.ledger.get("peak"))


def value(env):
    """The equity per unit."""
    return env.ledger.get("equity") / env.ledger.units()


def reasons(env):
    return [r["text"] for r in env.account.pause_reasons]


def test_a_transfer_moves_neither_the_drawdown_nor_the_value_per_unit_and_pauses_nothing(env):
    bought(env, 10, HOUR + MINUTE)
    marked(env, 76_000.0)  # 400 down, after a fee of 4
    synced(env, HOUR + 2 * MINUTE)
    assert (env.ledger.get("equity"), env.ledger.get("peak")) == (9_596.0, 10_000.0)
    down = drawdown(env)
    moved(env, -3_000.0, HOUR + 3 * MINUTE)  # as a loss, 34% down: past the kill line
    result = synced(env, HOUR + 4 * MINUTE)
    peak = 10_000.0 * 6_596.0 / 9_596.0
    assert result.alerts == [
        f"出入金已记账：转出 -3,000.00 USDT。投入本金合计 7,000.00 USDT，峰值按比例调为 {peak:,.2f}，"
        "收益率和回撤不算这笔钱"
    ]
    assert not env.account.paused and env.ledger.get("halted") is False and not result.killed
    assert env.ledger.get("peak") == pytest.approx(peak) and drawdown(env) == pytest.approx(down)
    assert value(env) == pytest.approx(0.9596)
    moved(env, 10_000.0, HOUR + 5 * MINUTE)  # as a gain, a new peak
    result = synced(env, HOUR + 6 * MINUTE)
    assert result.alerts[0].startswith("出入金已记账：转入 +10,000.00 USDT。投入本金合计 17,000.00 USDT")
    assert not env.account.paused and drawdown(env) == pytest.approx(down)
    assert value(env) == pytest.approx(0.9596) and env.ledger.contributed() == 17_000.0
    assert env.ledger.transfers() == [(HOUR + 3 * MINUTE, -3_000.0), (HOUR + 5 * MINUTE, 10_000.0)]
    assert [text for _, kind, text in env.ledger.events() if kind == "transfer"] == [
        "转出 -3,000.00 USDT", "转入 +10,000.00 USDT",
    ]


def test_a_deposit_does_not_lift_the_peak_the_kill_switch_measures_from(env):
    bought(env, 10, HOUR + MINUTE)
    marked(env, 76_000.0)
    synced(env, HOUR + 2 * MINUTE)
    moved(env, 2_000.0, HOUR + 3 * MINUTE)  # 11,596: past the peak of 10,000, were it a gain
    synced(env, HOUR + 4 * MINUTE)
    assert drawdown(env) == pytest.approx(1 - 9_596.0 / 10_000.0)
    marked(env, 56_000.0)  # 9,596: 17% under the 11,596, over a fifth under the value's peak
    result = synced(env, HOUR + 5 * MINUTE)
    assert result.killed and env.ledger.get("halted") is True


def test_the_returns_and_the_reports_leave_the_transfers_out(env):
    bought(env, 10, HOUR + MINUTE)
    synced(env, HOUR + 2 * MINUTE)  # 2026-01-10's snapshot: 9,996
    env.ledger.set("validation_start", HOUR)
    marked(env, 82_000.0)
    synced(env, HOUR + 6 * HOUR_MS)  # 10,196: up 2%
    moved(env, 10_196.0, HOUR + 12 * HOUR_MS)
    synced(env, HOUR + 12 * HOUR_MS + MINUTE)  # 20,392 on twice the units
    marked(env, 84_000.0)
    synced(env, HOUR + DAY_MS + MINUTE)  # 2026-01-11's snapshot: 20,592, up 1% more
    first, second = env.ledger.snapshots()
    assert first == Snapshot(HOUR, 9_996.0, 10_000.0, 10_000.0)
    assert (second.ts, second.equity, second.units, second.contributed) == (
        HOUR + DAY_MS, pytest.approx(20_592.0), pytest.approx(20_000.0), 20_196.0
    )
    assert env.ledger.adjusted_series() == [(HOUR, 9_996.0), (HOUR + DAY_MS, pytest.approx(10_296.0))]
    daily = report.daily(env.account, "2026-01-10", HOUR + DAY_MS + MINUTE).splitlines()
    assert daily[2:4] == ["权益 20,592.00 USDT", "较 01-10 零点 +3.00% · 回撤 0.0%（峰值 20,592.00）"]
    assert "出入金 转入 1 笔 +10,196.00 USDT，投入本金合计 20,196.00，不算收益" in daily
    full = report.full(env.account).splitlines()
    assert full[1].startswith("demo（交易所权益）：累计 +3.00%")
    assert full[-1] == "出入金 转入 1 笔 +10,196.00 USDT，投入本金合计 20,196.00：收益按时间加权，不算出入金"


def test_the_reports_name_money_moved_each_way(env):
    synced(env, HOUR + MINUTE)
    env.ledger.set("validation_start", HOUR)
    moved(env, 1_000.0, HOUR + 2 * MINUTE)
    moved(env, -400.0, HOUR + 3 * MINUTE)
    moved(env, -100.0, HOUR + 4 * MINUTE)
    synced(env, HOUR + DAY_MS + MINUTE)
    daily = report.daily(env.account, "2026-01-10", HOUR + DAY_MS + MINUTE).splitlines()
    assert "出入金 转入 1 笔 +1,000.00，转出 2 笔 -500.00 USDT，投入本金合计 10,500.00，不算收益" in daily
    assert daily[3].startswith("较 01-10 零点 +0.00% · ")
    assert report.daily(env.account, "2026-01-11", HOUR + 2 * DAY_MS).count("出入金") == 0
    moved(env, 300.0, HOUR + DAY_MS + 2 * MINUTE)  # past the day: the next day's
    synced(env, HOUR + DAY_MS + 3 * MINUTE)
    daily = report.daily(env.account, "2026-01-10", HOUR + DAY_MS + 3 * MINUTE).splitlines()
    assert "出入金 转入 1 笔 +1,000.00，转出 2 笔 -500.00 USDT，投入本金合计 10,800.00，不算收益" in daily
    daily = report.daily(env.account, "2026-01-11", HOUR + 2 * DAY_MS).splitlines()
    assert "出入金 转入 1 笔 +300.00 USDT，投入本金合计 10,800.00，不算收益" in daily


def test_the_report_of_the_day_the_account_opened_measures_from_the_capital_without_the_transfers(env):
    moved(env, 5_000.0, HOUR - 10 * MINUTE)  # 23:50, before any snapshot
    synced(env, HOUR + MINUTE)
    daily = report.daily(env.account, "2026-01-09", HOUR + MINUTE).splitlines()
    assert daily[2:4] == ["权益 15,000.00 USDT", "较本金 +0.00% · 回撤 0.0%（峰值 15,000.00）"]
    assert "出入金 转入 1 笔 +5,000.00 USDT，投入本金合计 15,000.00，不算收益" in daily


@pytest.mark.parametrize("bill, text", [
    (Bill("b1", "7", "9", "", -1.5, HOUR + MINUTE), "账单类型 7（子类型 9） -1.50 USDT"),
    (Bill("b2", TRANSFER_BILL, "11", "", -100.0, HOUR + MINUTE), "转入 -100.00 USDT"),
    (Bill("b3", TRANSFER_BILL, "12", "", 100.0, HOUR + MINUTE), "转出 +100.00 USDT"),
    (Bill("b4", TRANSFER_BILL, "13", "", 100.0, HOUR + MINUTE), "账单类型 1（子类型 13） +100.00 USDT"),
    # A transfer's subtype on a bill of another type is no transfer.
    (Bill("b5", "12", "11", "", 100.0, HOUR + MINUTE), "账单类型 12（子类型 11） +100.00 USDT"),
])
def test_a_bill_that_is_no_transfer_in_or_out_still_pauses_and_holds_the_peak(env, bill, text):
    env.exchange.other_bills.append(bill)
    env.exchange.cash += bill.amount
    result = synced(env, HOUR + 2 * MINUTE)
    assert reasons(env) == [f"余额有成交和资金费以外的变动：{text}"] and len(result.paused) == 1
    assert env.ledger.transfers() == [] and env.ledger.units() == env.ledger.contributed() == 10_000.0
    assert env.ledger.get("peak") == 10_000.0


def test_a_transfer_that_empties_the_account_or_refills_an_empty_one_measures_nothing_and_pauses(env):
    moved(env, -10_000.0, HOUR + MINUTE)
    synced(env, HOUR + 2 * MINUTE)
    out = "余额有成交和资金费以外的变动：转出 -10,000.00 USDT"
    assert reasons(env) == [out]
    moved(env, 5_000.0, HOUR + 3 * MINUTE)
    synced(env, HOUR + 4 * MINUTE)
    assert reasons(env) == [out, "余额有成交和资金费以外的变动：转入 +5,000.00 USDT"]
    assert env.ledger.transfers() == [] and env.ledger.units() == env.ledger.contributed() == 10_000.0


def test_a_ledger_from_before_the_transfers_reads_as_its_capital_and_gains_their_columns(tmp_path):
    path = tmp_path / "old.sqlite"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);"
        "CREATE TABLE equity (ts INTEGER PRIMARY KEY, equity REAL NOT NULL);"
        "INSERT INTO meta VALUES ('capital', '10000.0');"
        f"INSERT INTO equity VALUES ({DAY0}, 9000.0);"
    )
    old.close()
    as_capital = [Snapshot(DAY0, 9_000.0, 10_000.0, 10_000.0)]
    reader = Ledger(path, readonly=True)  # the web API, before a job has opened it
    assert reader.snapshots() == as_capital and reader.transfers() == []
    assert reader.adjusted_series() == [(DAY0, 9_000.0)]
    reader.db.close()
    Ledger(path).db.close()
    writer = Ledger(path)  # finds the columns the first added
    assert {"units", "contributed"} <= {row[1] for row in writer.db.execute("PRAGMA table_info(equity)")}
    assert writer.snapshots() == as_capital and writer.transfers() == []
    assert Ledger(path, readonly=True).snapshots() == as_capital
