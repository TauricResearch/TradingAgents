import dataclasses
import json
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
from tradingagents.memory.log import TradingMemoryLog

ETH = Coin("ETH-USD", "ETH-USDT-SWAP", "ETH-USDT")
NOW = datetime.fromtimestamp(T0 / 1000, UTC)  # 2026-01-10 00:30 UTC: trade date 2026-01-09
LATE = NOW + timedelta(hours=7)  # 07:30 UTC: Yahoo has published the daily candle of 2026-01-09


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
    configured = True

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


def candle_out(coin, trade_date):
    return True


def run(env, researcher, watchlist=(BTC,), now=NOW, sleeps=None, published=candle_out, rerun=None):
    settings, ledger = env
    paper, inbox = Paper(ledger, FakeOKX(), watchlist), Inbox()
    jobs.daily(
        settings, paper, inbox, lambda: researcher, now_fn=lambda: now,
        sleep=sleeps.append if sleeps is not None else lambda seconds: None,
        published=published, rerun_factory=rerun and (lambda: rerun),
    )
    return paper, inbox


def test_a_buy_is_researched_traded_and_reported(env):
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    paper, inbox = run(env, researcher)
    assert researcher.calls == [("BTC-USD", "2026-01-09")]
    assert paper.ledger.positions()[BTC.swap].qty == pytest.approx(0.04)
    assert inbox.sent[-1].startswith("日报 · 研判日 01-09\n")
    assert "BTC · Buy\n买入 0.04 @ 80,040.00\n" in inbox.sent[-1]
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
    jobs.daily(
        settings, paper, inbox, lambda: FakeResearcher({BTC.research: ["Buy"]}), now_fn=lambda: NOW,
        published=candle_out,
    )
    assert paper.ledger.positions()[BTC.swap].qty == pytest.approx(0.04)
    assert inbox.sent[-1].startswith("日报 · 研判日 01-09\n")
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
    assert "BTC · REVIEW\n不调仓 · 无持仓" in inbox.sent[-1]


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
    assert "未研判（本月 AI 预算已用完）" in inbox.sent[-1]


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
    assert inbox.sent[-1].startswith("日报 · 研判日 01-09\n\n⚠ 熔断中")


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
        jobs.daily(
            settings, paper, inbox, Crashing, now_fn=lambda: NOW + timedelta(minutes=2),
            published=candle_out,
        )
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
    assert [text.splitlines()[0] for text in inbox.sent] == ["日报 · 研判日 01-09"]


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


# -- the trade date's daily candle (#53) ------------------------------------------


class Yahoo:
    """``published``: Yahoo has the trade date's daily candle of the coins named only."""

    def __init__(self, *coins):
        self.coins = set(coins)

    def __call__(self, coin, trade_date):
        return coin in self.coins


class Rerun(FakeResearcher):
    """FakeResearcher that, on a rating, writes the record and decides as the library does."""

    def __init__(self, settings, script):
        super().__init__(script)
        self.settings = settings

    def run(self, ticker, trade_date):
        result = super().run(ticker, trade_date)
        if result.rating is None:
            return result
        write_record(self.settings, ticker, trade_date, result.rating)
        return dataclasses.replace(result, decision=f"{result.rating}, on the full candles")


def write_record(settings, coin, trade_date, rating):
    path = settings.home / "logs" / coin / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"trade_date": trade_date, "final_rating": rating}))
    return path


def test_a_coin_researched_before_its_daily_candle_waits_and_nothing_trades(env):
    ledger = env[1]
    researcher = FakeResearcher({BTC.research: ["Buy"], ETH.research: ["Hold"]})
    _, inbox = run(env, researcher, watchlist=(BTC, ETH), published=Yahoo(ETH.research))
    assert ledger.get("bar_waiting") == {"trade_date": "2026-01-09", "coins": ["BTC-USD"]}
    assert ledger.positions() == {} and not ledger.executed("2026-01-09")
    assert not any("模拟盘日报" in text for text in inbox.sent)
    # An hour on, Yahoo still lacks it: nothing is researched, traded or sent.
    later = NOW + timedelta(hours=1)
    _, inbox = run(env, researcher, watchlist=(BTC, ETH), now=later, published=Yahoo(ETH.research))
    assert len(researcher.calls) == 2 and inbox.sent == []
    assert not ledger.executed("2026-01-09")


def test_once_the_candle_is_out_a_rerun_replaces_the_first_research_and_the_account_trades(env):
    settings, ledger = env
    first = FakeResearcher({BTC.research: ["Hold"], ETH.research: ["Hold"]})
    run(env, first, watchlist=(BTC, ETH), published=Yahoo(ETH.research))
    record = write_record(settings, BTC.research, "2026-01-09", "Hold")
    settings.memory_log_path.parent.mkdir(parents=True, exist_ok=True)
    memory = TradingMemoryLog({"memory_log_path": str(settings.memory_log_path)})
    memory.store_decision(BTC.research, "2026-01-09", "Hold, without the day's candle", "Hold")
    rerun = Rerun(settings, {BTC.research: ["Buy"]})

    _, inbox = run(
        env, first, watchlist=(BTC, ETH), now=LATE, published=Yahoo(BTC.research, ETH.research),
        rerun=rerun,
    )
    assert rerun.calls == [("BTC-USD", "2026-01-09")] and len(first.calls) == 2
    assert jobs.coin_state(ledger, "2026-01-09", BTC.research) == ("done", "Buy")
    assert ledger.get("bar_waiting")["coins"] == []
    assert ledger.cost_of("2026-01-09") == (3.0, False)  # the rerun is paid for too
    late_ms = int(LATE.timestamp() * 1000)
    assert ledger.updates() == [("2026-01-09", "BTC-USD", late_ms, "Hold", "Buy")]
    text = "BTC 研判已更新：Hold → Buy（研判日 2026-01-09，用上了当天的日线）"
    assert ledger.events(kinds=("research_update",)) == [(late_ms, "research_update", text)]
    assert inbox.sent[0] == "研判更新 · BTC\n评级 Hold → Buy\n研判日 01-09 · 用上了当天的日线"
    # The new record replaced the old one, kept under a name the readers skip.
    assert json.loads(record.read_text())["final_rating"] == "Buy"
    kept = record.with_name("superseded_20260110T0730Z_full_states_log_2026-01-09.json")
    assert json.loads(kept.read_text())["final_rating"] == "Hold"
    # The memory log's pending decision is the rerun's.
    log = settings.memory_log_path.read_text(encoding="utf-8")
    assert "[2026-01-09 | BTC-USD | Buy | pending]" in log and "without the day's candle" not in log
    # The account traded on it, and the report says so.
    assert ledger.positions()[BTC.swap].qty > 0 and ledger.executed("2026-01-09")
    assert "BTC · Buy（重跑前是 Hold）\n买入 " in inbox.sent[-1]
    assert "ETH · Hold\n不调仓 · 无持仓" in inbox.sent[-1]


def test_a_failed_rerun_leaves_the_first_research_and_the_next_hour_tries_again(env):
    settings, ledger = env
    first = FakeResearcher({BTC.research: ["Hold"]})
    run(env, first, published=Yahoo())
    record = write_record(settings, BTC.research, "2026-01-09", "Hold")
    rerun = Rerun(settings, {BTC.research: [RuntimeError("boom"), "Buy"]})

    _, inbox = run(env, first, now=LATE, published=Yahoo(BTC.research), rerun=rerun)
    assert jobs.coin_state(ledger, "2026-01-09", BTC.research) == ("done", "Hold")
    assert [p.name for p in record.parent.iterdir()] == [record.name]
    assert json.loads(record.read_text())["final_rating"] == "Hold"
    assert ledger.updates() == [] and ledger.get("bar_waiting")["coins"] == ["BTC-USD"]
    assert not ledger.executed("2026-01-09") and inbox.sent == []

    _, inbox = run(env, first, now=LATE + timedelta(hours=1), published=Yahoo(BTC.research), rerun=rerun)
    assert jobs.coin_state(ledger, "2026-01-09", BTC.research) == ("done", "Buy")
    assert "BTC · Buy（重跑前是 Hold）\n买入 0.04 @ 80,040.00\n" in inbox.sent[-1]


def test_a_rerun_failing_after_it_wrote_its_record_puts_the_first_record_back(env):
    settings, ledger = env
    run(env, FakeResearcher({BTC.research: ["Hold"]}), published=Yahoo())
    record = write_record(settings, BTC.research, "2026-01-09", "Hold")

    class Broken:
        def run(self, ticker, trade_date):
            write_record(settings, ticker, trade_date, "Buy")
            return ResearchResult(None, "RuntimeError: after the record", 10, 5, 0.5)

    run(env, FakeResearcher({}), now=LATE, published=Yahoo(BTC.research), rerun=Broken())
    assert [p.name for p in record.parent.iterdir()] == [record.name]
    assert json.loads(record.read_text())["final_rating"] == "Hold"
    assert jobs.coin_state(ledger, "2026-01-09", BTC.research) == ("done", "Hold")


def test_from_the_cutoff_hour_the_account_trades_on_the_first_rating_with_an_alert(env):
    ledger = env[1]
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    run(env, researcher, published=Yahoo())
    _, inbox = run(env, researcher, now=NOW.replace(hour=11, minute=5), published=Yahoo())
    assert not ledger.executed("2026-01-09") and inbox.sent == []

    _, inbox = run(env, researcher, now=NOW.replace(hour=12, minute=5), published=Yahoo())
    alert = (
        "研判日 2026-01-09：BTC 到 12:00 UTC 还没能用当天的日线重跑（Yahoo 没给出，或重跑失败），"
        "按先前的研判执行。"
    )
    assert inbox.sent[0] == alert
    assert [text for _, _, text in ledger.events(kinds=("bar_cutoff",))] == [alert]
    assert len(researcher.calls) == 1
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.04)
    assert "BTC · Buy\n买入 0.04 @ 80,040.00\n" in inbox.sent[-1]


def test_with_the_monthly_budget_spent_no_coin_waits_for_a_rerun(env):
    ledger = env[1]
    ledger.set("budget_cap", 1.0)  # the first research spends it
    researcher = FakeResearcher({BTC.research: ["Buy"]})
    run(env, researcher, published=Yahoo())
    _, inbox = run(env, researcher, now=LATE, published=Yahoo(BTC.research))
    assert len(researcher.calls) == 1
    assert inbox.sent[0] == "本月 LLM 预算已用完，研判日 2026-01-09 不再用当天的日线重跑，按先前的研判执行。"
    assert ledger.positions()[BTC.swap].qty == pytest.approx(0.04)


def test_a_trade_dates_rating_is_that_of_its_last_successful_research(env):
    ledger = env[1]
    for rating, error in [("Hold", None), (None, "RuntimeError: boom"), ("Buy", None), (None, "x")]:
        ledger.record_attempt("2026-01-09", BTC.research, T0, rating=rating, error=error)
    assert jobs.coin_state(ledger, "2026-01-09", BTC.research) == ("done", "Buy")
