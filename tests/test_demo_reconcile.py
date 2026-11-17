"""Repairing a ledger that no longer agrees with the exchange (#37): ``reconcile.plan``
reads the exchange again over a longer window than a sync's and finds what the syncs
missed, ``reconcile.apply`` books it, and what still differs as an adjustment. Only a
paused or halted account is repaired; the commands that ask a person first are tested
with the other demo and live commands.

The account opens at 23:30 (``Env``); a sync re-reads ten minutes before the last one,
so a fill the exchange reports after that has passed it is never read again."""

import pytest

from tests.test_demo_account import BTC, HOUR, HOUR_ID
from tests.test_demo_job import Clock, Env
from trader.demo import job, reconcile, report
from trader.demo.settings import MISMATCH_GRACE_MS
from trader.intraday.paper import HOUR_MS
from trader.ledger import Fill
from trader.okx import DAY_MS
from web.api.data import _replayed

MINUTE = 60_000
DAY = "2026-01-10"


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def bought(env, contracts, at, price=80_000.0, client_id=f"trd{HOUR_ID}btc"):
    """A fill of the program's order on the exchange at ``at``; its row, as the exchange reports it."""
    env.exchange.now, env.exchange.price = at, price
    env.exchange._fill(BTC.swap, contracts, client_id)
    return env.exchange.fill_rows[-1]


def synced(env, now):
    env.exchange.now = now
    return env.account.sync(now)


def unexplained(have, want):
    return f"账本与交易所持仓不一致：BTC-USDT-SWAP 账本推算 {have}，交易所 {want}，已按交易所为准"


def paused_long(env, exchange_book):
    """0.1 BTC bought at 80,000 at 00:05 and booked; then the exchange holds
    ``exchange_book`` (contracts, average price) with no fill to say why, and the account
    is paused for it by the sync of 01:10."""
    bought(env, 10.0, HOUR + 5 * MINUTE)
    synced(env, HOUR + 10 * MINUTE)
    env.exchange.book[BTC.swap] = list(exchange_book)
    synced(env, HOUR + 40 * MINUTE)
    later = synced(env, HOUR + 40 * MINUTE + MISMATCH_GRACE_MS)
    assert later.paused and env.account.paused


def test_a_fill_the_exchange_reported_after_the_syncs_passed_it_is_booked_and_the_account_resumes(env):
    bought(env, 10.0, HOUR + 5 * MINUTE)
    synced(env, HOUR + 10 * MINUTE)
    row = bought(env, 5.0, HOUR + 20 * MINUTE)
    env.exchange.fill_rows.remove(row)  # not reported yet
    text = unexplained("+0.1", "+0.15")
    assert synced(env, HOUR + 40 * MINUTE).problems == [text]
    env.exchange.fill_rows.append(row)  # reported now, ten minutes too late for the next sync
    assert synced(env, HOUR + 40 * MINUTE + MISMATCH_GRACE_MS).paused == [text]
    now = HOUR + 2 * HOUR_MS

    repair = reconcile.plan(env.account, now)
    assert repair.fills == (
        Fill(HOUR + 20 * MINUTE, BTC.swap, 0.05, 80_000.0, pytest.approx(2.0), "trade", DAY),
    )
    assert repair.funding == () and repair.adjustments == () and not repair.clipped
    assert repair.bills == {row.bill_id: row.ts}
    assert reconcile.describe(repair) == [
        "重读了 2026-01-09 23:30 到 2026-01-10 01:11 UTC 的成交和资金费",
        "补记漏掉的成交 1 笔：",
        "  2026-01-10 00:20 BTC-USDT-SWAP +0.05 @ 80,000.00，手续费 2.00，调仓",
    ]
    cash = env.ledger.get("cash")
    text = reconcile.apply(env.account, repair, now, "OKX 晚报了这笔成交")
    assert text == "修复账本（python -m trader demo reconcile）：补记漏掉的成交 1 笔；说明：OKX 晚报了这笔成交"
    assert env.ledger.events()[-1] == (now, "reconcile", text)
    assert env.ledger.net_fills() == {BTC.swap: pytest.approx(0.15)}
    assert env.ledger.get("cash") == cash  # the wallet had the fee all along
    assert env.account.paused  # the pause is the person's to lift

    reasons, result = job.resume(env.settings, env.account, env.intraday, now_fn=Clock(now + MINUTE).now)
    assert result.holding == [] and not env.account.paused
    assert [r["text"] for r in reasons] == [unexplained("+0.1", "+0.15")]


def test_what_no_fill_explains_is_adjusted_at_the_exchanges_price_and_the_syncs_agree_after(env):
    paused_long(env, [30.0, 80_500.0])
    now = HOUR + 2 * HOUR_MS
    synced_to = HOUR + 70 * MINUTE

    repair = reconcile.plan(env.account, now)
    assert repair.fills == () and repair.funding == ()
    adjustment = Fill(synced_to, BTC.swap, 0.2, 80_500.0, 0.0, "adjust", DAY)
    assert repair.adjustments == (reconcile.Adjustment(BTC.swap, 0.1, 0.3, (adjustment,)),)
    assert reconcile.describe(repair) == [
        "重读了 2026-01-09 23:30 到 2026-01-10 01:11 UTC 的成交和资金费",
        "补记之后仍对不上的持仓，按 2026-01-10 01:10 UTC 那次对账读到的交易所持仓记成调整，不收手续费：",
        "  BTC-USDT-SWAP 账本推算 +0.1，交易所 +0.3：调整 +0.2 @ 80,500.00",
        "  账本多出来的部分按账本里的开仓均价平掉，不算盈亏；交易所多出来的部分按交易所的持仓均价记开仓。",
    ]
    assert env.ledger.get("mismatched") == {BTC.swap: HOUR + 40 * MINUTE}

    def day_line():
        lines = report.daily(env.account, DAY, HOUR + DAY_MS + 10 * MINUTE).splitlines()
        return next(line for line in lines if line.startswith("昨日成交"))

    assert day_line().startswith("昨日成交 1 笔（调仓 1，止损 0，熔断 0，非程序 0），")
    text = reconcile.apply(env.account, repair, now)
    assert text == "修复账本（python -m trader demo reconcile）：BTC-USDT-SWAP 账本推算 +0.1，交易所 +0.3，记调整 +0.2 @ 80,500.00"
    assert env.ledger.fills()[-1] == adjustment
    assert env.ledger.net_fills() == {BTC.swap: pytest.approx(0.3)}
    assert env.ledger.get("mismatched") == {}
    after = synced(env, now + MINUTE)
    assert after.holding == [] and after.paused == []
    # The day's summary counts the adjustment apart from the trades.
    assert day_line().startswith("昨日成交 2 笔（调仓 1，止损 0，熔断 0，非程序 0，调整 1），")


@pytest.mark.parametrize("book, left", [([0.0, 0.0], 0.0), ([5.0, 79_000.0], 0.05)])
def test_what_the_exchange_no_longer_holds_is_closed_at_the_entry_the_fills_give_it(env, book, left):
    bought(env, 10.0, HOUR + 5 * MINUTE)
    bought(env, 10.0, HOUR + 6 * MINUTE, price=82_000.0)
    synced(env, HOUR + 10 * MINUTE)
    env.exchange.book[BTC.swap] = book  # less, or none, with no fill to say how
    env.account.pause(HOUR + 15 * MINUTE, "对不上账")
    synced(env, HOUR + 20 * MINUTE)

    repair = reconcile.plan(env.account, HOUR + 30 * MINUTE)
    (adjustment,) = repair.adjustments
    (fill,) = adjustment.fills
    assert (adjustment.have, adjustment.want) == (0.2, pytest.approx(left))
    assert (fill.qty, fill.price) == (pytest.approx(left - 0.2), pytest.approx(81_000.0))
    reconcile.apply(env.account, repair, HOUR + 30 * MINUTE)
    # The dashboard's replay of the fills realizes nothing on it.
    *_, (last, realized, after, _) = _replayed(env.ledger)
    assert (last.reason, realized, after) == ("adjust", pytest.approx(0.0), pytest.approx(left))
    assert synced(env, HOUR + 31 * MINUTE).holding == []


def test_a_position_on_the_other_side_is_closed_at_the_ledgers_entry_and_opened_at_the_exchanges(env):
    paused_long(env, [-5.0, 81_000.0])
    repair = reconcile.plan(env.account, HOUR + 2 * HOUR_MS)
    (adjustment,) = repair.adjustments
    assert [(f.qty, f.price, f.fee, f.reason) for f in adjustment.fills] == [
        (-0.1, 80_000.0, 0.0, "adjust"), (-0.05, 81_000.0, 0.0, "adjust"),
    ]
    assert reconcile.describe(repair)[2] == "  BTC-USDT-SWAP 账本推算 +0.1，交易所 -0.05：调整 -0.1 @ 80,000.00、-0.05 @ 81,000.00"
    reconcile.apply(env.account, repair, HOUR + 2 * HOUR_MS)
    assert [(realized, after) for f, realized, after, _ in _replayed(env.ledger) if f.reason == "adjust"] == [
        (pytest.approx(0.0), 0.0), (pytest.approx(0.0), -0.05),
    ]
    assert synced(env, HOUR + 2 * HOUR_MS + MINUTE).holding == []


def test_a_ledger_that_changed_after_the_plan_is_not_written(env):
    paused_long(env, [30.0, 80_000.0])
    repair = reconcile.plan(env.account, HOUR + 2 * HOUR_MS)
    synced(env, HOUR + 2 * HOUR_MS)  # the hourly run synced while the person read the plan
    fills = env.ledger.fills()
    with pytest.raises(reconcile.Refused, match="账本在确认期间变了"):
        reconcile.apply(env.account, repair, HOUR + 2 * HOUR_MS)
    assert env.ledger.fills() == fills
    assert env.ledger.events(kinds=("reconcile",)) == []


def test_only_a_paused_or_halted_account_is_repaired(env):
    refusal = "demo 账户没有暂停也没有熔断：只有暂停或熔断时才能修复账本"
    with pytest.raises(reconcile.Refused, match=refusal):
        reconcile.plan(env.account, HOUR)
    env.ledger.set("halted", True)
    assert reconcile.plan(env.account, HOUR).empty
    env.ledger.set("halted", False)
    env.account.pause(HOUR, "对不上账")
    repair = reconcile.plan(env.account, HOUR)
    assert repair.empty
    assert reconcile.describe(repair) == [
        "重读了 2026-01-09 23:30 到 2026-01-09 23:31 UTC 的成交和资金费",
        "账本和交易所对得上：没有漏记的成交和资金费，持仓也一致，不用修复。",
    ]
    env.account.unpause(HOUR, "解除")  # lifted while the person read the plan
    with pytest.raises(reconcile.Refused, match=refusal):
        reconcile.apply(env.account, repair, HOUR)
    assert env.ledger.events(kinds=("reconcile",)) == []


def test_a_funding_fee_reported_late_is_booked_once_and_the_next_sync_does_not_book_it_again(env):
    bought(env, 10.0, HOUR + 5 * MINUTE)
    synced(env, HOUR + 10 * MINUTE)
    synced(env, HOUR + HOUR_MS)
    env.exchange.now = HOUR + 55 * MINUTE
    env.exchange.settle_funding(BTC.swap, -0.8)  # reported after the sync of 01:00
    bill = env.exchange.funding[-1]
    env.account.pause(HOUR + HOUR_MS, "对不上账")

    repair = reconcile.plan(env.account, HOUR + HOUR_MS + 2 * MINUTE)
    assert repair.funding == ((HOUR + 55 * MINUTE, BTC.swap, 0.0, -0.8),)
    assert repair.fills == () and repair.adjustments == () and repair.bills == {bill.bill_id: bill.ts}
    assert reconcile.describe(repair)[1:] == ["补记漏掉的资金费 1 笔：", "  2026-01-10 00:55 BTC-USDT-SWAP -0.8000 USDT"]
    text = reconcile.apply(env.account, repair, HOUR + HOUR_MS + 2 * MINUTE)
    assert text == "修复账本（python -m trader demo reconcile）：补记漏掉的资金费 1 笔"
    # The next sync's window holds the bill again: it is among the booked ones.
    synced(env, HOUR + HOUR_MS + 5 * MINUTE)
    assert env.ledger.funding() == [(HOUR + 55 * MINUTE, BTC.swap, 0.0, -0.8)]
    env.ledger.set("booked_bills", {})  # what the ledger holds decides, not the bill ids kept
    assert reconcile.plan(env.account, HOUR + HOUR_MS + 6 * MINUTE).empty


def test_a_fill_booked_by_the_repair_is_not_booked_again_by_the_next_sync(env):
    bought(env, 10.0, HOUR + 5 * MINUTE)
    synced(env, HOUR + 10 * MINUTE)
    row = bought(env, 5.0, HOUR + 55 * MINUTE)
    env.exchange.fill_rows.remove(row)
    bought(env, 1.0, HOUR + 58 * MINUTE)  # booked by the sync, as are those the repair books
    assert synced(env, HOUR + HOUR_MS).problems == [unexplained("+0.11", "+0.16")]
    env.exchange.fill_rows.append(row)
    env.account.pause(HOUR + HOUR_MS, "对不上账")

    repair = reconcile.plan(env.account, HOUR + HOUR_MS + 2 * MINUTE)
    assert [f.ts for f in repair.fills] == [HOUR + 55 * MINUTE] and repair.adjustments == ()
    reconcile.apply(env.account, repair, HOUR + HOUR_MS + 2 * MINUTE)
    result = synced(env, HOUR + HOUR_MS + 5 * MINUTE)
    assert result.fills == [] and result.holding == []
    assert env.ledger.net_fills() == {BTC.swap: pytest.approx(0.16)}


def test_the_entry_an_adjustment_closes_at_is_replayed_in_time_order_with_the_fills_booked_late(env):
    bought(env, 10.0, HOUR + 5 * MINUTE)
    row = bought(env, 5.0, HOUR + 20 * MINUTE, price=81_000.0)
    env.exchange.fill_rows.remove(row)
    bought(env, -10.0, HOUR + 30 * MINUTE, price=82_000.0)
    synced(env, HOUR + 35 * MINUTE)
    env.exchange.fill_rows.append(row)
    env.exchange.book[BTC.swap] = [0.0, 0.0]  # what was left is gone, with no fill to say how
    env.account.pause(HOUR + 40 * MINUTE, "对不上账")
    synced(env, HOUR + 40 * MINUTE)
    repair = reconcile.plan(env.account, HOUR + 45 * MINUTE)
    assert [f.ts for f in repair.fills] == [HOUR + 20 * MINUTE]
    (adjustment,) = repair.adjustments
    # 0.1 at 80,000 and 0.05 at 81,000, of which 0.1 sold: what is left entered at 80,333.33.
    assert [(f.qty, f.price) for f in adjustment.fills] == [(-0.05, pytest.approx(80_333.333333))]


def test_of_two_alike_fills_the_one_the_ledger_lacks_is_booked(env):
    # Two fills of one order, alike in time, size and price, under two bill ids.
    bought(env, 5.0, HOUR + 5 * MINUTE)
    row = bought(env, 5.0, HOUR + 5 * MINUTE)
    env.exchange.fill_rows.remove(row)
    synced(env, HOUR + 10 * MINUTE)
    env.exchange.fill_rows.append(row)
    env.account.pause(HOUR + 10 * MINUTE, "对不上账")
    alike = Fill(HOUR + 5 * MINUTE, BTC.swap, 0.05, 80_000.0, pytest.approx(2.0), "trade", DAY)
    repair = reconcile.plan(env.account, HOUR + 20 * MINUTE)
    assert (repair.fills, repair.bills, repair.adjustments) == ((alike,), {row.bill_id: row.ts}, ())
    # The same once the booked bill ids no longer reach back that far.
    env.ledger.set("booked_bills", {})
    repair = reconcile.plan(env.account, HOUR + 20 * MINUTE)
    assert repair.fills == (alike,) and repair.adjustments == ()


def test_the_window_starts_at_the_opening_or_as_far_back_as_the_exchange_keeps(env):
    opened = HOUR - 30 * MINUTE
    # Before the account opened: not its fills.
    env.exchange.now = opened - HOUR_MS
    env.exchange.manual_fill(BTC.swap, 5)
    env.exchange.manual_fill(BTC.swap, -5)
    env.account.pause(opened, "对不上账")
    assert reconcile.plan(env.account, HOUR).empty
    # A hundred days on, a fill of the account's second day is older than the exchange keeps.
    row = bought(env, 5.0, opened + DAY_MS, client_id="")
    env.exchange.fill_rows.remove(row)
    now = opened + 100 * DAY_MS
    synced(env, now - HOUR_MS)
    env.exchange.fill_rows.append(row)
    repair = reconcile.plan(env.account, now)
    assert repair.clipped and repair.begin == now - reconcile.HISTORY_MS and repair.fills == ()
    (adjustment,) = repair.adjustments
    assert [(f.qty, f.price) for f in adjustment.fills] == [(0.05, 80_000.0)]
    assert reconcile.describe(repair)[0] == (
        "重读了 2026-01-19 23:30 到 2026-04-19 22:31 UTC 的成交和资金费"
        "（交易所只保留三个月：开户之后、这之前漏记的只能记成调整）"
    )
