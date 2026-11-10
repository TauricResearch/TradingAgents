from datetime import UTC, datetime, timedelta, timezone

import pytest
import requests

from tests.test_trader_paper import BTC, T0, FakeOKX, minutes as candles
from trader import jobs
from trader.ledger import BUDGET_ERROR, Ledger, Position
from trader.okx import MINUTE_MS
from trader.paper import Paper, ReplayStalled
from trader.research import ResearchResult
from trader.settings import Coin, Settings

ETH = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
NOW = datetime.fromtimestamp(T0 / 1000, UTC)  # 2026-01-10 00:30 UTC: trade date 2026-01-09


class FakeResearcher:
    """Plays each coin's scripted outcomes in order: a rating, or an exception's error."""

    def __init__(self, script):
        self.script = {coin: list(outcomes) for coin, outcomes in script.items()}
        self.calls = []

    def run(self, ticker, trade_date):
        self.calls.append((ticker, trade_date))
        outcome = self.script[ticker].pop(0)
        if isinstance(outcome, Exception):
            return ResearchResult(None, f"{type(outcome).__name__}: {outcome}", 10, 5, 0.5)
        return ResearchResult(outcome, None, 100, 50, 1.0)


class Inbox:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return True


@pytest.fixture(autouse=True)
def _fixed_config(monkeypatch):
    monkeypatch.setattr(
        jobs, "build_config", lambda settings: {"deep_think_llm": "d", "quick_think_llm": "q"}
    )


@pytest.fixture
def env(tmp_path):
    settings = Settings(home=tmp_path)
    ledger = Ledger(settings.ledger_path)
    ledger.initialize(10_000.0, T0)
    return settings, ledger


def run(env, researcher, watchlist=(BTC,), now=NOW, sleeps=None):
    settings, ledger = env
    paper, inbox = Paper(ledger, FakeOKX(), watchlist), Inbox()
    jobs.daily(
        settings, paper, inbox, lambda: researcher, now_fn=lambda: now,
        sleep=sleeps.append if sleeps is not None else lambda seconds: None,
    )
    return paper, inbox


def test_a_buy_is_researched_traded_and_reported(env):
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    paper, inbox = run(env, researcher)
    assert researcher.calls == [("BTC-USD", "2026-01-09")]
    assert paper.ledger.positions()[BTC.swap].qty == pytest.approx(0.04)
    assert "研判日 2026-01-09" in inbox.sent[-1]
    assert "BTC：Buy → 买入 0.04" in inbox.sent[-1]
    assert "上限未定（已观察 0/7 天）" in inbox.sent[-1]


def test_the_report_goes_out_when_okx_fails_after_the_trades(env):
    class SpotDown(FakeOKX):
        """Swaps quote; the spot tickers the report prices the baseline with do not."""

        def last_price(self, inst):
            if not inst.endswith("-SWAP"):
                raise requests.ConnectionError("Host is down")
            return super().last_price(inst)

    settings, ledger = env
    paper, inbox = Paper(ledger, SpotDown(), (BTC,)), Inbox()
    jobs.daily(settings, paper, inbox, lambda: FakeResearcher({BTC.research: ["Buy"]}), now_fn=lambda: NOW)
    assert paper.ledger.positions()[BTC.swap].qty == pytest.approx(0.04)
    assert "研判日 2026-01-09" in inbox.sent[-1]
    assert inbox.sent[-1].splitlines()[-1].startswith("⚠ 行情暂不可用")
    assert ledger.get("reported") == ["2026-01-09", True]


def test_a_rerun_does_not_research_trade_or_report_again(env):
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    run(env, researcher)
    _, inbox = run(env, researcher)
    assert len(researcher.calls) == 1
    assert len(env[1].fills()) == 1
    assert inbox.sent == []


def test_a_failing_coin_is_retried_in_later_rounds(env):
    researcher = FakeResearcher({
        BTC.research: [RuntimeError("boom"), RuntimeError("boom"), "Buy"],
        ETH.research: ["Hold"],
    })
    sleeps = []
    run(env, researcher, watchlist=(BTC, ETH), sleeps=sleeps)
    assert [ticker for ticker, _ in researcher.calls] == ["BTC-USD", "ETH-USD", "BTC-USD", "BTC-USD"]
    assert sleeps == [1800, 1800]
    assert jobs.coin_state(env[1], "2026-01-09", BTC.research) == ("done", "Buy")


def test_review_is_a_result_and_is_not_retried(env):
    researcher = FakeResearcher({BTC.research: ["REVIEW"]})
    _, inbox = run(env, researcher)
    assert len(researcher.calls) == 1
    assert env[1].positions() == {}
    assert "BTC：REVIEW → 不调仓；无持仓" in inbox.sent[-1]


def test_a_coin_failing_every_attempt_keeps_its_position(env):
    ledger = env[1]
    ledger.commit(positions={BTC.swap: Position(0.04, 80_000, 75_000)}, cash=10_000.0)
    researcher = FakeResearcher({BTC.research: [RuntimeError("boom")] * 3})
    _, inbox = run(env, researcher)
    assert len(researcher.calls) == 3
    assert ledger.positions()[BTC.swap].qty == 0.04
    assert "研判失败（RuntimeError: boom）" in inbox.sent[-1]


def test_research_stops_when_the_monthly_budget_is_spent(env):
    ledger = env[1]
    # Seven earlier days at $1 set a $45 cap, and $50 is already spent this month.
    for day in range(1, 8):
        ledger.record_attempt(
            f"2026-01-0{day}", BTC.research, T0 - 1, rating="Hold", error=None, cost_usd=1.0
        )
    ledger.record_attempt("2026-01-08", BTC.research, T0 - 1, rating="Hold", error=None, cost_usd=43.0)
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    _, inbox = run(env, researcher)
    assert researcher.calls == []
    assert jobs.coin_state(ledger, "2026-01-09", BTC.research) == ("failed", BUDGET_ERROR)
    assert ledger.get("budget_cap") == pytest.approx(45.0)
    assert "未研判（本月 LLM 预算已用完）" in inbox.sent[-1]


def test_the_cap_is_learned_from_days_with_known_costs(env):
    ledger = env[1]
    for day in range(1, 10):
        cost = None if day == 2 else float(day)
        ledger.record_attempt(f"2026-01-0{day}", BTC.research, 0, rating="Hold", error=None, cost_usd=cost)
    assert jobs.budget_cap(ledger, "2026-01-05") is None  # three known days so far
    # 2026-01-02's cost is unknown, so the first seven known days are 1, 3, 4, 5, 6, 7, 8.
    assert jobs.budget_cap(ledger, "2026-01-10") == pytest.approx(34 / 7 * 30 * 1.5)


def test_research_runs_but_nothing_trades_while_halted(env):
    ledger = env[1]
    ledger.set("halted", True)
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    _, inbox = run(env, researcher)
    assert len(researcher.calls) == 1
    assert ledger.positions() == {}
    assert not ledger.executed("2026-01-09")
    assert inbox.sent[-1].splitlines()[1].startswith("⚠ 熔断中")


def test_a_second_day_with_failures_alerts(env):
    researcher = FakeResearcher({BTC.research: [RuntimeError("boom")] * 6})
    _, first = run(env, researcher)
    assert not any("连续" in text for text in first.sent)
    _, second = run(env, researcher, now=NOW + timedelta(days=1))
    assert any("连续 2 天" in text for text in second.sent)


def test_alerts_from_the_first_replay_are_sent_before_research(env):
    settings, ledger = env
    ledger.commit(positions={BTC.swap: Position(0.04, 80_000, 75_000)}, cash=10_000.0)
    # The minute after T0 gaps through the stop; the research then crashes the run.
    okx = FakeOKX(minute=candles(T0 - MINUTE_MS, [80_000, 74_000]))
    paper, inbox = Paper(ledger, okx, (BTC,)), Inbox()

    class Crashing:
        def run(self, ticker, trade_date):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        jobs.daily(settings, paper, inbox, Crashing, now_fn=lambda: NOW + timedelta(minutes=2))
    assert ledger.positions() == {}
    assert "止损" in inbox.sent[0]


def test_unset_model_prices_alert_once_per_trade_date(env):
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    _, first = run(env, researcher)
    assert first.sent[0].startswith("TRADER_PRICE_DEEP / TRADER_PRICE_QUICK 没有配置")
    _, rerun = run(env, researcher)
    assert rerun.sent == []


def test_configured_model_prices_do_not_alert(env):
    settings, ledger = env
    priced = Settings(home=settings.home, price_deep=(3.0, 15.0), price_quick=(0.15, 0.6))
    _, inbox = run((priced, ledger), FakeResearcher({BTC.research: ["Buy"]}))
    assert [text.splitlines()[0] for text in inbox.sent] == ["模拟盘日报 · 研判日 2026-01-09"]


def test_a_new_model_or_version_restarts_validation_and_a_code_change_does_not(env):
    ledger = env[1]
    base = {"version": "0.7.1", "deep": "d", "quick": "q", "code": "aaa"}
    assert jobs.check_fingerprint(ledger, base, 0) == []
    assert jobs.check_fingerprint(ledger, base, 0) == []
    ledger.set("validation_start", 123)
    patch = {**base, "version": "0.7.2", "code": "bbb"}
    assert "不重新计时" in jobs.check_fingerprint(ledger, patch, 1)[0]
    assert ledger.get("validation_start") == 123
    alert = jobs.check_fingerprint(ledger, {**patch, "version": "0.8.0"}, 2)[0]
    assert "从下一次执行起重新计时" in alert
    assert ledger.get("validation_start") is None


def test_the_fingerprint_names_the_watchlist_and_a_pool_change_restarts_validation(env):
    ledger = env[1]
    config = {"deep_think_llm": "d", "quick_think_llm": "q"}
    current = jobs.fingerprint(config, (ETH, BTC))
    assert current["watchlist"] == ["BTC-USD", "ETH-USD"]  # order does not count
    # A fingerprint recorded before the watchlist was part of it: recorded, no alert, no restart.
    ledger.set("fingerprint", {k: v for k, v in current.items() if k != "watchlist"})
    ledger.set("validation_start", 123)
    assert jobs.check_fingerprint(ledger, current, 0) == []
    assert ledger.get("fingerprint") == current and ledger.get("validation_start") == 123
    # The pool changes: the period restarts like it does for a new model.
    alert = jobs.check_fingerprint(ledger, jobs.fingerprint(config, (BTC,)), 1)[0]
    assert "自选池" in alert and "从下一次执行起重新计时" in alert
    assert ledger.get("validation_start") is None and ledger.get("baseline_ref") is None


def test_the_trade_date_is_the_previous_utc_day():
    assert jobs.trade_date_for(datetime(2026, 1, 10, 0, 5, tzinfo=UTC)) == "2026-01-09"
    singapore = timezone(timedelta(hours=8))
    assert jobs.trade_date_for(datetime(2026, 1, 10, 7, 59, tzinfo=singapore)) == "2026-01-08"


def test_a_failing_mark_alerts_at_most_every_six_hours(env):
    settings, ledger = env
    ledger.commit(positions={BTC.swap: Position(0.04, 80_000, 75_000)}, cash=10_000.0)
    paper, inbox = Paper(ledger, FakeOKX(), (BTC,)), Inbox()
    for minutes in (30, 60, 400):
        with pytest.raises(ReplayStalled):
            jobs.mark(settings, paper, inbox, now_fn=lambda m=minutes: NOW + timedelta(minutes=m))
    assert len(inbox.sent) == 2
