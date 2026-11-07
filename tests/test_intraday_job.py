"""The hourly job and the reports of the intraday account.

The numbers follow tests/test_intraday_paper.py: a full unit is 0.1 BTC at 80,000 with the
hourly ATR of 400, bought at 80,040 with a stop at 79,040.
"""

from datetime import UTC, datetime, timedelta

import pytest

from tests.test_trader_jobs import Inbox
from tests.test_trader_paper import BTC, DAY0, T0, FakeOKX, minutes
from trader.intraday import job, report
from trader.intraday.paper import HOUR_MS, IntradayPaper
from trader.intraday.types import SignalResult
from trader.ledger import Ledger, Position
from trader.okx import DAY_MS, MINUTE_MS, Bar
from trader.settings import Coin, Settings

ETH = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
NOW = datetime.fromtimestamp(T0 / 1000, UTC)  # 2026-01-10 00:30 UTC
FINGERPRINT = {"model": "m", "prompt": "v1"}


class FakeSignaler:
    """Plays each coin's scripted outcomes in order: a signal (or None), or an exception
    to raise; records the calls."""

    def __init__(self, script, fingerprint=FINGERPRINT):
        self.script = {coin: list(outcomes) for coin, outcomes in script.items()}
        self.fp = fingerprint
        self.calls = []

    def run(self, coin, now_ms, position=None):
        self.calls.append((coin.research, now_ms, position))
        outcome = self.script[coin.research].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SignalResult(outcome, 2, "because", None, 100, 20, 0.01)

    def fingerprint(self):
        return self.fp


@pytest.fixture
def env(tmp_path):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.intraday_ledger_path)
    ledger.initialize(10_000.0, T0)
    return settings, ledger


def run(env, signaler, now=NOW, okx=None, watchlist=(BTC,)):
    settings, ledger = env
    paper, inbox = IntradayPaper(ledger, okx or FakeOKX(), watchlist), Inbox()
    job.run(settings, paper, inbox, signaler, now_fn=lambda: now)
    return paper, inbox


def flat_market(start, count):
    """A FakeOKX with ``count`` flat 1-minute candles at 80,000 from ``start``, so a replay
    over them with a position neither stops out nor stalls."""
    return FakeOKX(minute=minutes(start, [80_000] * count))


def test_a_long_signal_is_recorded_traded_and_messaged(env):
    signaler = FakeSignaler({BTC.research: ["Long"]})
    paper, inbox = run(env, signaler)
    ledger = paper.ledger
    assert signaler.calls == [("BTC-USD", T0, None)]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.1)
    assert ledger.get("decided_hour") == DAY0
    assert ledger.get("fingerprint") == FINGERPRINT
    assert ledger.signals() == [(T0, "BTC-USD", "Long", 2, "because", None, 100, 20, 0.01)]
    assert ledger.signal_cost_since(0) == (pytest.approx(0.01), False)
    # Cash 10,000 - 4.002 of fee, the position marked 4 under its entry: 9,992.00.
    assert [t for t in inbox.sent if t.startswith("日内 · ")] == [
        "日内 · 01-10 00:00 UTC\n"
        "BTC：Long → 买入 0.1 @ 80,040.00；持仓 +0.1，止损 79,040.00\n"
        "净值 9,992.00 USDT"
    ]


def test_a_rerun_in_the_same_hour_neither_asks_nor_trades_again(env):
    signaler = FakeSignaler({BTC.research: ["Long", "Short"]})
    run(env, signaler)
    _, inbox = run(env, signaler, now=NOW + timedelta(minutes=5))
    assert len(signaler.calls) == 1
    assert len(env[1].fills()) == 1
    assert env[1].positions()[BTC.swap].qty == pytest.approx(0.1)
    assert inbox.sent == []


def test_an_hour_without_fills_sends_no_message(env):
    run(env, FakeSignaler({BTC.research: ["Long"]}))
    signaler = FakeSignaler({BTC.research: ["Long"]})
    _, inbox = run(env, signaler, now=NOW + timedelta(hours=1), okx=flat_market(T0 - MINUTE_MS, 61))
    # The signaler saw the position; Long on a full long changes nothing.
    assert signaler.calls[0][2].qty == pytest.approx(0.1)
    assert len(env[1].fills()) == 1
    assert env[1].get("decided_hour") == DAY0 + HOUR_MS
    assert inbox.sent == []


def test_a_signal_that_fails_is_recorded_and_keeps_the_position(env):
    env[1].commit(positions={BTC.swap: Position(0.1, 80_000, 79_000)}, cash=10_000.0)
    _, inbox = run(env, FakeSignaler({BTC.research: [RuntimeError("boom")]}))
    assert env[1].positions()[BTC.swap].qty == 0.1
    assert env[1].fills() == []
    ts, coin, signal, conviction, reason, error, *_ = env[1].signals()[0]
    assert (coin, signal, conviction, reason) == ("BTC-USD", None, None, "")
    assert error == "RuntimeError: boom"
    assert not any(t.startswith("日内 · ") for t in inbox.sent)


def test_two_coins_are_decided_and_messaged_together(env):
    signaler = FakeSignaler({BTC.research: ["Long"], ETH.research: ["Short"]})
    paper, inbox = run(env, signaler, watchlist=(BTC, ETH))
    assert [call[0] for call in signaler.calls] == ["BTC-USD", "ETH-USD"]
    assert paper.ledger.positions()[BTC.swap].qty == pytest.approx(0.1)
    assert paper.ledger.positions()[ETH.swap].qty == pytest.approx(-0.1)
    message = [t for t in inbox.sent if t.startswith("日内 · ")][0]
    assert message.splitlines()[1:3] == [
        "BTC：Long → 买入 0.1 @ 80,040.00；持仓 +0.1，止损 79,040.00",
        "ETH：Short → 卖出 0.1 @ 79,960.00；持仓 -0.1，止损 80,960.00",
    ]


def test_nothing_is_asked_while_halted(env):
    env[1].set("halted", True)
    signaler = FakeSignaler({BTC.research: ["Long"]})
    _, inbox = run(env, signaler)
    assert signaler.calls == []
    assert env[1].get("decided_hour") is None
    assert env[1].signals() == []
    assert "⚠ 熔断中" in inbox.sent[-1]


def test_a_kill_in_the_opening_replay_stops_the_hour_from_asking(env):
    env[1].commit(positions={BTC.swap: Position(1.0, 80_000, 1.0)}, cash=10_000.0)
    # Equity 7,900 at the third candle is 21% below the 10,000 peak: flatten and halt.
    okx = FakeOKX(minute=minutes(T0 - MINUTE_MS, [80_000, 79_000, 77_900, 77_900]))
    signaler = FakeSignaler({BTC.research: ["Long"]})
    _, inbox = run(env, signaler, now=NOW + timedelta(minutes=3), okx=okx)
    assert env[1].get("halted") is True
    assert env[1].positions() == {}
    assert signaler.calls == []
    assert inbox.sent[0].startswith("熔断：")
    assert [f.reason for f in env[1].fills()] == ["kill"]


def test_a_changed_fingerprint_restarts_the_validation_period(env):
    ledger = env[1]
    run(env, FakeSignaler({BTC.research: ["Flat"]}))
    assert ledger.get("validation_start") == DAY0
    assert ledger.get("baseline_ref") == {BTC.research: 80_000}
    changed = {"model": "m", "prompt": "v2"}
    okx = FakeOKX()
    okx.daily.append(Bar(DAY0, 80_000, 83_000, 79_000, 82_000))  # 01-10 closes at 82,000
    signaler = FakeSignaler({BTC.research: ["Flat"]}, changed)
    _, inbox = run(env, signaler, now=NOW + timedelta(days=1), okx=okx)
    assert "验证期从下一次执行起重新计时" in inbox.sent[0]
    assert "'v1'" in inbox.sent[0] and "'v2'" in inbox.sent[0]
    assert ledger.get("fingerprint") == changed
    # The execution of that hour restarted the period at its day, with a fresh baseline.
    assert ledger.get("validation_start") == DAY0 + DAY_MS
    assert ledger.get("baseline_ref") == {BTC.research: 82_000}
    kinds = ledger.db.execute("SELECT kind FROM events").fetchall()
    assert kinds == [("validation_restart",)]


def test_check_fingerprint_records_and_resets(env):
    ledger = env[1]
    assert job.check_fingerprint(ledger, FINGERPRINT, 0) == []
    assert job.check_fingerprint(ledger, FINGERPRINT, 0) == []
    ledger.set("validation_start", 123)
    ledger.set("baseline_ref", {BTC.research: 1.0})
    assert len(job.check_fingerprint(ledger, {**FINGERPRINT, "model": "n"}, 1)) == 1
    assert ledger.get("validation_start") is None
    assert ledger.get("baseline_ref") is None


def summaries(inbox):
    return [t for t in inbox.sent if t.startswith("日内盘日报")]


def test_the_daily_summary_goes_out_once_on_the_first_run_of_a_day(env):
    _, first = run(env, FakeSignaler({BTC.research: ["Long"]}))
    assert [t.splitlines()[0] for t in summaries(first)] == ["日内盘日报 · 2026-01-09"]
    _, later = run(
        env, FakeSignaler({BTC.research: ["Long"]}), now=NOW + timedelta(hours=1),
        okx=flat_market(T0 - MINUTE_MS, 61),
    )
    assert later.sent == []
    _, next_day = run(
        env, FakeSignaler({BTC.research: ["Flat"]}), now=NOW + timedelta(days=1),
        okx=flat_market(T0 - MINUTE_MS, DAY_MS // MINUTE_MS + 1),
    )
    assert len(summaries(next_day)) == 1
    lines = summaries(next_day)[0].splitlines()
    assert lines[0] == "日内盘日报 · 2026-01-10"
    # Flat closed the long at 79,960: cash 9,995.998 - 8 - 3.998 = 9,984.00, from 10,000 at the
    # 01-10 midnight snapshot; the peak is the 10,000 the replay marked.
    assert lines[1] == "净值 9,984.00 USDT，较 2026-01-10 零点 -0.16%，回撤 0.2%（峰值 10,000.00）"
    assert lines[2] == "昨日成交 1 笔（调仓 1，止损 0，熔断 0）"
    assert lines[3] == "昨日信号 2 次：Long 2，Short 0，Flat 0，失败 0"
    # Today's Flat signal counts toward the month, not toward yesterday.
    assert lines[4] == "LLM 费用：昨日 $0.02，本月 $0.03（已从绩效扣除，没有预算上限）"
    _, again = run(
        env, FakeSignaler({BTC.research: ["Flat"]}), now=NOW + timedelta(days=1, hours=1)
    )
    assert summaries(again) == []


def test_the_daily_summary_notes_unknown_costs_and_counts_failures(env):
    ledger = env[1]
    day = DAY0 - DAY_MS
    ledger.record_signal(day + HOUR_MS, BTC.research, SignalResult("Short", 1, "", None, 1, 1))
    ledger.record_signal(day + 2 * HOUR_MS, BTC.research, SignalResult(None, None, "", "boom"))
    text = report.daily(IntradayPaper(ledger, FakeOKX(), (BTC,)), "2026-01-09", T0)
    assert "净值 10,000.00 USDT，较本金 +0.00%" in text
    assert "昨日信号 2 次：Long 0，Short 1，Flat 0，失败 1" in text
    assert text.splitlines()[-1].endswith("；有调用费用未知，没算进去")


def test_the_full_report_nets_the_signals_cost_and_sets_the_baselines(env):
    ledger = env[1]
    paper = IntradayPaper(ledger, FakeOKX(), (BTC,))
    assert report.full(paper).startswith("日内盘验证期还没开始")
    ledger.commit(
        positions={}, cash=10_000.0, meta={"validation_start": DAY0},
        snapshots=[(DAY0, 10_000.0), (DAY0 + DAY_MS, 10_100.0), (DAY0 + 2 * DAY_MS, 10_200.0)],
    )
    # $100 of signals after the second midnight comes off the third.
    costly = SignalResult("Long", 3, "", None, 1, 1, 100.0)
    ledger.record_signal(DAY0 + DAY_MS + 1, BTC.research, costly)
    paper.okx.daily = [
        Bar(DAY0 + (i - 1) * DAY_MS, 0, 0, 0, c) for i, c in enumerate((80_000, 80_800, 81_600))
    ]
    text = report.full(paper)
    assert "日内盘绩效：验证期自 2026-01-10 起，共 2 天" in text
    assert "策略（扣 LLM 费用）：累计 +1.00%" in text
    assert "三币等权买入持有：累计 +2.00%" in text
    assert "BTC 买入持有：累计 +2.00%" in text
    assert "LLM 费用 $100.00，已从策略曲线扣除，没有月度预算上限；" in text
    assert "评级准确度" not in text
