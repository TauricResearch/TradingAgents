"""The hourly job and the reports of the intraday account.

The numbers follow tests/test_intraday_paper.py: a full unit is 0.1 BTC at 80,000 with the
hourly ATR of 400, bought at 80,040 with a stop at 79,040.
"""

from datetime import UTC, datetime, timedelta

import pytest
import typer

from tests.test_trader_jobs import Inbox
from tests.test_trader_paper import BTC, DAY0, T0, FakeOKX, minutes
from trader import __main__ as cli
from trader.intraday import job, report
from trader.intraday.paper import HOUR_MS, IntradayPaper
from trader.intraday.types import SignalResult
from trader.ledger import Ledger, Position
from trader.okx import DAY_MS, MINUTE_MS, Bar
from trader.paper import ReplayStalled
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


def clock(now):
    """A ``now_fn`` stuck at ``now``."""
    return lambda: now


def run(env, signaler, now=NOW, okx=None, watchlist=(BTC,)):
    settings, ledger = env
    paper, inbox = IntradayPaper(ledger, okx or FakeOKX(), watchlist), Inbox()
    job.run(settings, paper, inbox, signaler, now_fn=clock(now))
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
    assert ledger.get("fingerprint") == {**FINGERPRINT, "watchlist": ["BTC-USD"]}
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


@pytest.mark.parametrize("error, again", [
    ("AnthropicOverloadedError: Error code: 529 - {'error': {'type': 'overloaded_error'}}", True),
    ("AnthropicConnectionError: Connection error.", True),
    ("RateLimitError: Error code: 429 - too many requests", True),
    ("APITimeoutError: Request timed out.", True),
    ("InternalServerError: Error code: 500", True),
    ("ReadTimeout: HTTPSConnectionPool(host='www.okx.com'): Read timed out.", True),
    ("AuthenticationError: Error code: 401 - invalid x-api-key", False),
    ("BadRequestError: Error code: 400 - prompt is too long", False),
    ("ValueError: no signal in the answer", False),
    (None, False),
])
def test_which_failures_are_worth_another_try(error, again):
    assert job.transient(error) is again


class AnthropicOverloadedError(Exception):
    """Named like the SDK's: its text is what the job classifies as transient."""


def test_a_transient_failure_is_asked_again_within_the_hour(env):
    settings, ledger = env
    signaler = FakeSignaler({BTC.research: [AnthropicOverloadedError("Error code: 529"), "Long"]})
    paper, inbox, sleeps = IntradayPaper(ledger, FakeOKX(), (BTC,)), Inbox(), []
    job.run(settings, paper, inbox, signaler, now_fn=clock(NOW), sleep=sleeps.append)
    assert [call[0] for call in signaler.calls] == ["BTC-USD", "BTC-USD"]
    assert sleeps == [job.SIGNAL_RETRY_WAIT_SECONDS]
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.1)  # the second answer counts
    recorded = [(row[2], row[5]) for row in ledger.signals()]  # newest first: (signal, error)
    assert recorded == [("Long", None), (None, "AnthropicOverloadedError: Error code: 529")]
    assert ledger.get("outage_hours", 0) == 0


def test_retries_stop_at_the_limit_and_other_failures_are_not_retried(env):
    settings, ledger = env
    signaler = FakeSignaler({
        BTC.research: [AnthropicOverloadedError("Error code: 529")] * 3,
        ETH.research: [RuntimeError("boom")],
    })
    paper, inbox, sleeps = IntradayPaper(ledger, FakeOKX(), (BTC, ETH)), Inbox(), []
    job.run(settings, paper, inbox, signaler, now_fn=clock(NOW), sleep=sleeps.append)
    assert [call[0] for call in signaler.calls] == ["BTC-USD", "ETH-USD", "BTC-USD", "BTC-USD"]
    assert sleeps == [job.SIGNAL_RETRY_WAIT_SECONDS] * job.SIGNAL_RETRIES
    assert ledger.positions() == {} and len(ledger.signals()) == 4
    assert ledger.get("outage_hours") == 1  # every coin failed: counted, not yet alerted
    assert not any("日内信号" in text for text in inbox.sent)


def test_hours_of_total_failure_alert_once_and_the_recovery_is_announced(env):
    settings, ledger = env
    failing = [RuntimeError("boom")] * 3 + ["Flat"]
    signaler = FakeSignaler({BTC.research: failing})
    paper, inbox = IntradayPaper(ledger, FakeOKX(), (BTC,)), Inbox()
    for hours in range(4):
        job.run(settings, paper, inbox, signaler, now_fn=clock(NOW + timedelta(hours=hours)))
    outage = [text for text in inbox.sent if "日内信号" in text]
    # Hour 1 only counts; hour 2 alerts; hour 3 is within the alert interval; hour 4 recovers.
    assert len(outage) == 2
    assert outage[0].startswith("日内信号已连续 2 个整点全部失败") and "RuntimeError: boom" in outage[0]
    assert outage[1] == "日内信号已恢复，此前连续 3 个整点全部失败。"
    assert ledger.get("outage_hours") == 0
    assert ledger.get("intraday_alerted_at") == T0 + HOUR_MS
    kinds = [row[0] for row in ledger.db.execute("SELECT kind FROM events ORDER BY ts").fetchall()]
    assert kinds == ["signal_outage", "signal_recovered"]


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
    assert ledger.get("fingerprint") == {**changed, "watchlist": ["BTC-USD"]}
    # The execution of that hour restarted the period at its day, with a fresh baseline.
    assert ledger.get("validation_start") == DAY0 + DAY_MS
    assert ledger.get("baseline_ref") == {BTC.research: 82_000}
    kinds = ledger.db.execute("SELECT kind FROM events").fetchall()
    assert kinds == [("validation_restart",)]


def test_the_fingerprint_names_the_watchlist_and_a_pool_change_restarts_validation(env):
    ledger = env[1]
    current = job.fingerprint(FakeSignaler({}), (ETH, BTC))
    assert current == {**FINGERPRINT, "watchlist": ["BTC-USD", "ETH-USD"]}
    ledger.set("fingerprint", FINGERPRINT)  # recorded before the watchlist was part of it
    ledger.set("validation_start", 123)
    assert job.check_fingerprint(ledger, current, 0) == []
    assert ledger.get("fingerprint") == current and ledger.get("validation_start") == 123
    alert = job.check_fingerprint(ledger, job.fingerprint(FakeSignaler({}), (BTC,)), 1)[0]
    assert "自选池" in alert and ledger.get("validation_start") is None


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


def test_no_summary_goes_out_on_a_day_already_summarized(env):
    env[1].set("summarized_day", "2026-01-10")
    _, inbox = run(env, FakeSignaler({BTC.research: ["Flat"]}))
    assert summaries(inbox) == []
    _, next_day = run(env, FakeSignaler({BTC.research: ["Flat"]}), now=NOW + timedelta(days=1))
    assert [t.splitlines()[0] for t in summaries(next_day)] == ["日内盘日报 · 2026-01-10"]


def test_init_opens_the_account_with_its_day_already_summarized(tmp_path, monkeypatch):
    # python -m trader intraday init, without the command line: the settings and the
    # clock are patched, so the first run of that day sends no summary of an empty day.
    settings = Settings(home=tmp_path, capital=1_000.0)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(cli, "_now_ms", lambda: T0)
    cli.intraday_init()
    ledger = Ledger(settings.intraday_ledger_path)
    assert ledger.get("capital") == 1_000.0
    assert ledger.get("summarized_day") == "2026-01-10"
    with pytest.raises(typer.Exit):  # an account exists already
        cli.intraday_init()
    _, inbox = run((settings, ledger), FakeSignaler({BTC.research: ["Flat"]}))
    assert summaries(inbox) == []


def test_a_failing_run_alerts_at_most_every_six_hours(env):
    settings, ledger = env
    ledger.commit(positions={BTC.swap: Position(0.1, 80_000, 79_000)}, cash=10_000.0)
    # No 1-minute candles for the held contract: every replay stalls and raises.
    paper, inbox = IntradayPaper(ledger, FakeOKX(), (BTC,)), Inbox()
    signaler = FakeSignaler({BTC.research: ["Long"] * 3})
    for later in (30, 60, 400):
        with pytest.raises(ReplayStalled):
            job.run(settings, paper, inbox, signaler, now_fn=clock(NOW + timedelta(minutes=later)))
    assert [t.split("：")[0] for t in inbox.sent] == ["intraday 运行失败", "intraday 运行失败"]
    assert "ReplayStalled" in inbox.sent[0]
    assert ledger.get("intraday_alerted_at") == T0 + 400 * MINUTE_MS
    assert signaler.calls == []


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
