"""The layout of the accounts' Telegram messages (``trader.message``), and the labels
the paper accounts' messages go out with."""

from datetime import UTC, datetime

import pytest

from tests.test_trader_jobs import Inbox
from tests.test_trader_paper import FakeOKX
from trader import __main__ as cli, message
from trader.ledger import Fill, Ledger, Position
from trader.settings import Settings

T0 = int(datetime(2026, 11, 17, 7, 0, tzinfo=UTC).timestamp() * 1000)
HOUR_MS = 3_600_000
BTC = "BTC-USDT-SWAP"


def test_a_time_reads_in_beijing_first_with_the_utc_clock_in_brackets():
    assert message.when(T0) == "11-17 15:00 北京（07:00 UTC）"
    late = T0 + 10 * HOUR_MS  # 17:00 UTC is already the next day in Beijing
    assert message.when(late) == "11-18 01:00 北京（17:00 UTC）"
    assert message.beijing(late) == "11-18 01:00 北京"
    assert message.day("2026-11-16") == "11-16"


def test_a_coin_is_named_without_the_rest_of_its_contract_or_ticker():
    assert [message.coin(name) for name in (BTC, "BTC-USD", "BTC-USDT")] == ["BTC"] * 3


def test_the_fills_an_order_came_back_in_read_as_one_trade_at_their_average_price():
    fills = [
        Fill(T0, BTC, -0.0001, 64_659.70, 0.01, "trade"),
        Fill(T0 + 1, BTC, -0.0146, 64_658.60, 0.47, "trade"),
    ]
    assert message.trades(fills) == ["卖出 0.0147 @ 均价 64,658.61（2 笔）"]
    assert message.trades(fills[:1]) == ["卖出 0.0001 @ 64,659.70"]
    assert message.trades([]) == []


def test_fills_on_the_other_side_or_of_another_kind_are_trades_of_their_own():
    fills = [
        Fill(T0, BTC, 0.1, 81_000.0, 4.0, "stop"),
        Fill(T0 + 1, BTC, 0.02, 80_000.0, 0.8, "trade"),
        Fill(T0 + 2, BTC, 0.03, 80_100.0, 1.2, "trade"),
        Fill(T0 + 3, BTC, -0.05, 80_200.0, 2.0, "trade"),
        Fill(T0 + 4, BTC, -0.1, 80_300.0, 4.0, "kill"),
    ]
    assert message.trades(fills) == [
        "买入 0.1 @ 81,000.00（止损）",
        "买入 0.05 @ 均价 80,060.00（2 笔）",
        "卖出 0.05 @ 80,200.00",
        "卖出 0.1 @ 80,300.00（熔断）",
    ]


def test_a_position_is_told_with_its_stop():
    assert message.held(Position(-0.0539, 64_700.0, 65_701.4)) == "持仓 -0.0539 · 止损 65,701.40"
    assert message.held(Position(0.1, 80_000.0, None)) == "持仓 +0.1 · 止损 待挂"
    assert message.held(None) == "无持仓"


def test_a_stop_is_told_with_the_entry_it_closed_and_the_return_on_it():
    # A short of 3.119 ETH from 1,789.77 bought back at 1,828.74 loses 121.55 and 2.85 of
    # fee: 2.23% of the 5,582.29 the coins cost at the entry.
    assert message.stopped("ETH-USDT-SWAP", 3.119, 1_828.74, 1_789.77, -124.40) == (
        "止损平仓 · ETH\n买入 3.119 @ 1,828.74（开仓均价 1,789.77）\n盈亏 -124.40 USDT（-2.23%）"
    )
    # A long's stop that locked a profit in, filled in three pieces.
    assert message.stopped(BTC, -0.1, 82_000.0, 80_000.0, 195.9, 3) == (
        "止损平仓 · BTC\n卖出 0.1 @ 均价 82,000.00（3 笔 · 开仓均价 80,000.00）\n盈亏 +195.90 USDT（+2.45%）"
    )
    assert message.stopped(BTC, -0.1, 82_000.0, None, None).splitlines()[1:] == [
        "卖出 0.1 @ 82,000.00", "账本里没有它平掉的仓位，算不出盈亏",
    ]


def test_a_rating_update_says_whether_the_rating_changed():
    assert message.research_update("BTC-USD", "2026-11-16", "Hold", "Underweight") == (
        "研判更新 · BTC\n评级 Hold → Underweight\n研判日 11-16 · 用上了当天的日线"
    )
    same = message.research_update("BTC-USD", "2026-11-16", "Hold", "Hold")
    assert same.splitlines()[1] == "评级 Hold（重跑后不变）"
    # The ledger lets an update have no rating before it: the message does not print None.
    first = message.research_update("BTC-USD", "2026-11-16", None, "Hold")
    assert first.splitlines()[1] == "评级 Hold（重跑前没有评级）"
    assert message.rerun("Hold", "Buy") == "重跑前是 Hold"


def test_paragraphs_are_set_apart_by_a_blank_line_and_the_empty_ones_left_out():
    assert message.paragraphs(["a", "b"], [], ["c"]) == "a\nb\n\nc"


@pytest.mark.parametrize(
    ("opened", "path", "label"),
    [("_open", "ledger_path", "日频"), ("_open_intraday", "intraday_ledger_path", "日内")],
)
def test_what_a_paper_account_sends_is_labeled_with_the_account(tmp_path, monkeypatch, opened, path, label):
    # The four accounts share one chat: an alert without a label does not say whose it is.
    inbox = Inbox()
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "OKX", FakeOKX)
    monkeypatch.setattr(cli, "Notifier", lambda settings: inbox)
    Ledger(getattr(Settings(home=tmp_path), path)).initialize(10_000.0, T0)
    _, _, notifier = getattr(cli, opened)()
    notifier.send("止损平仓 · ETH")
    assert inbox.sent == [f"【{label}】止损平仓 · ETH"]
