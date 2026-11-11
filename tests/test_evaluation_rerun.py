"""Rerunning the intraday signal over history (Issue #28): the prompt's inputs from
the history store, the rerun's cache, budget and stops, and the CLI command."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner

from tests.test_evaluation import BTC, DAY0, T0, FakeOKX, load, price_path
from tests.test_intraday_signal import USAGE, FakeLLM
from trader.__main__ import app
from trader.evaluation import cli as evaluation_cli
from trader.evaluation.history import HOUR_MS, MINUTE_MS, HistoryStore
from trader.evaluation.market import HistoricalOKX
from trader.evaluation.replay import signals_from_ledger
from trader.evaluation.rerun import (
    MAX_EMPTY_HOURS,
    RETRIES,
    RETRY_PAUSE,
    Rerun,
    cache_summary,
    rerun,
)
from trader.intraday.signal import NO_RESEARCH, Signaler
from trader.ledger import Ledger
from trader.okx import Bar, FundingEvent, FundingRate, OKXError, OpenInterest
from trader.settings import WATCHLIST, Settings
from tradingagents.default_config import DEFAULT_CONFIG

PRICE = (2.0, 10.0)  # USD per million tokens in and out: a FakeLLM call costs 0.003
CALL_COST = USAGE["input_tokens"] * PRICE[0] / 1e6 + USAGE["output_tokens"] * PRICE[1] / 1e6


@pytest.fixture
def store(tmp_path) -> HistoryStore:
    return HistoryStore(tmp_path / "history.sqlite")


def load_prompt_inputs(store: HistoryStore, hours: int, inst: str = BTC.swap) -> None:
    """What the prompt reads on top of what ``load`` fills: 15-minute candles, hourly
    open interest from DAY0, and the funding settlements through the end."""
    end = DAY0 + hours * HOUR_MS
    store.put_funding(
        inst, [FundingEvent(DAY0 + 8 * HOUR_MS * k, 0.0001) for k in range(1, hours // 8 + 2)],
        DAY0, end + 8 * HOUR_MS,
    )
    minutes = store.bars(inst, "1m", DAY0, end)
    quarters = []
    for q in range(hours * 4):
        chunk = minutes[q * 15:(q + 1) * 15]
        quarters.append(Bar(
            DAY0 + q * 15 * MINUTE_MS, chunk[0].open, max(b.high for b in chunk),
            min(b.low for b in chunk), chunk[-1].close,
        ))
    store.put_bars(inst, "15m", quarters, DAY0, end)
    store.put_open_interest(
        inst, [OpenInterest(DAY0 + h * HOUR_MS, 1e9 + h * 1e6) for h in range(hours)], DAY0, end
    )


def signaler(tmp_path, market: HistoricalOKX, llm=None) -> Signaler:
    settings = Settings(home=tmp_path, price_deep=PRICE)
    return Signaler(settings, market, llm=llm or FakeLLM(), results_dir=tmp_path / "logs")


# -- the prompt's inputs from history -----------------------------------------

def test_the_historical_funding_rate_is_the_settlement_the_hour_ran_into(store):
    settles = DAY0 + 16 * HOUR_MS
    store.put_funding(BTC.swap, [FundingEvent(DAY0 + 8 * HOUR_MS, 0.0001), FundingEvent(settles, -0.0002)],
                      DAY0, DAY0 + 24 * HOUR_MS)
    market = HistoricalOKX(store, DAY0 + 9 * HOUR_MS + 3 * MINUTE_MS)
    assert market.funding_rate(BTC.swap) == FundingRate(
        rate=-0.0002, time=settles, next_rate=None, next_time=settles + 8 * HOUR_MS
    )
    # Exactly at a settlement the next period has begun.
    market.at(DAY0 + 8 * HOUR_MS)
    assert market.funding_rate(BTC.swap).time == settles
    market.at(settles)
    with pytest.raises(OKXError, match="no funding settlement"):
        market.funding_rate(BTC.swap)


def test_the_historical_open_interest_is_the_last_hourly_point(store):
    store.put_open_interest(
        BTC.swap, [OpenInterest(DAY0, 1e9), OpenInterest(DAY0 + HOUR_MS, 2e9)], DAY0, DAY0 + 2 * HOUR_MS
    )
    market = HistoricalOKX(store, DAY0 + HOUR_MS + 3 * MINUTE_MS)
    assert market.open_interest(BTC.swap) == 2e9
    market.at(DAY0 + 59 * MINUTE_MS)
    assert market.open_interest(BTC.swap) == 1e9
    market.at(DAY0 + 5 * HOUR_MS)  # the last point is stale by then
    with pytest.raises(OKXError, match="no open interest"):
        market.open_interest(BTC.swap)


class FakeOKXWithOI(FakeOKX):
    def open_interest_history(self, inst, period, start_ms, end_ms):
        self.calls.append(("oi", inst, period, start_ms, end_ms))
        return [OpenInterest(t, 5e8) for t in range(start_ms, end_ms, HOUR_MS)]


def test_the_store_fetches_the_open_interest_of_closed_hours_only(store):
    okx = FakeOKXWithOI()
    now = DAY0 + 3 * HOUR_MS + 20 * MINUTE_MS
    assert store.ensure_open_interest(okx, BTC.swap, DAY0, DAY0 + 6 * HOUR_MS, now) == 3
    assert okx.calls == [("oi", BTC.swap, "1H", DAY0, DAY0 + 3 * HOUR_MS)]
    assert store.coverage(BTC.swap, "oi") == [(DAY0, DAY0 + 3 * HOUR_MS)]
    assert [p.ts for p in store.open_interest(BTC.swap, DAY0, DAY0 + 6 * HOUR_MS)] == [
        DAY0, DAY0 + HOUR_MS, DAY0 + 2 * HOUR_MS
    ]
    okx.calls.clear()
    assert store.ensure_open_interest(okx, BTC.swap, DAY0, DAY0 + 3 * HOUR_MS, now) == 0
    assert okx.calls == []


# -- the rerun ----------------------------------------------------------------

def test_a_rerun_asks_the_model_each_hour_and_trades_its_answers(store, tmp_path):
    load(store, price_path(30), 30)
    load_prompt_inputs(store, 30)
    market = HistoricalOKX(store)
    llm = FakeLLM()
    cache = Ledger(tmp_path / "cache.sqlite")
    made = signaler(tmp_path, market, llm)
    result, stats, stopped = rerun(
        store, cache, made, market, T0, T0 + 3 * HOUR_MS, watchlist=(BTC,), workers=1,
    )
    assert stopped is None and result is not None
    assert (stats.hours, stats.calls, stats.cached, stats.failures) == (3, 3, 0, 0)
    assert stats.spent == pytest.approx(3 * CALL_COST)
    # The model answered Long 2 every hour: the engine opened a long in the first.
    assert result.fills and result.fills[0].qty > 0
    assert [s.ts for s in signals_from_ledger(cache.path)] == [T0 + 3 * MINUTE_MS + h * HOUR_MS for h in range(3)]
    assert all(s.signal == "Long" and s.conviction == 2 for s in signals_from_ledger(cache.path))
    # The prompt saw the history as of each hour: no research, no funding forecast, a
    # flat book first and the position the engine then held.
    first, second = (calls[-1].content for calls in llm.calls[:2])
    assert NO_RESEARCH in first and "Current position: flat" in first
    assert "Current position: long" in second
    assert cache.get("fingerprint") == made.fingerprint()
    summary = cache_summary(cache)
    assert (summary["hours"], summary["signals"], summary["failures"]) == (3, 3, 0)
    assert summary["cost_usd"] == pytest.approx(3 * CALL_COST)


def test_a_rerun_resumes_from_its_cache_without_paying_again(store, tmp_path):
    load(store, price_path(30), 30)
    load_prompt_inputs(store, 30)
    market = HistoricalOKX(store)
    cache = Ledger(tmp_path / "cache.sqlite")
    rerun(store, cache, signaler(tmp_path, market), market, T0, T0 + 2 * HOUR_MS, watchlist=(BTC,), workers=1)
    llm = FakeLLM()
    result, stats, stopped = rerun(
        store, cache, signaler(tmp_path, market, llm), market, T0, T0 + 4 * HOUR_MS,
        watchlist=(BTC,), workers=1,
    )
    assert stopped is None and result is not None
    assert (stats.hours, stats.calls, stats.cached) == (4, 2, 2)
    assert len(llm.calls) == 2
    assert stats.spent == pytest.approx(2 * CALL_COST)
    assert cache_summary(cache)["signals"] == 4


def test_a_rerun_stops_at_its_budget_and_can_go_on_later(store, tmp_path):
    load(store, price_path(30), 30)
    load_prompt_inputs(store, 30)
    market = HistoricalOKX(store)
    cache = Ledger(tmp_path / "cache.sqlite")
    result, stats, stopped = rerun(
        store, cache, signaler(tmp_path, market), market, T0, T0 + 5 * HOUR_MS,
        watchlist=(BTC,), workers=1, budget_usd=2.5 * CALL_COST,
    )
    assert result is None and stopped.startswith("BudgetExhausted")
    assert stats.calls == 3  # the third call crossed the budget; the fourth hour was not paid for
    assert cache_summary(cache)["signals"] == 3
    result, stats, stopped = rerun(
        store, cache, signaler(tmp_path, market), market, T0, T0 + 5 * HOUR_MS,
        watchlist=(BTC,), workers=1, budget_usd=2.5 * CALL_COST,
    )
    assert stopped is None and (stats.calls, stats.cached) == (2, 3)


def test_hours_that_cost_nothing_and_gave_nothing_are_not_cached_and_stop_the_run(store, tmp_path):
    load(store, price_path(30), 30)
    load_prompt_inputs(store, 30)
    market = HistoricalOKX(store)
    cache = Ledger(tmp_path / "cache.sqlite")
    llm = FakeLLM(error=RuntimeError("the model is down"))
    pauses = []
    result, stats, stopped = rerun(
        store, cache, signaler(tmp_path, market, llm), market, T0, T0 + 10 * HOUR_MS,
        watchlist=(BTC,), workers=1, sleep=pauses.append,
    )
    assert result is None and stopped.startswith("NothingWorks") and "the model is down" in stopped
    assert stats.hours == MAX_EMPTY_HOURS and stats.failures == MAX_EMPTY_HOURS
    # Every hour was tried RETRIES more times, pausing longer each time, before giving up.
    assert stats.calls == MAX_EMPTY_HOURS * (RETRIES + 1)
    assert pauses == [RETRY_PAUSE * 2 ** i for i in range(RETRIES)] * MAX_EMPTY_HOURS
    assert cache_summary(cache)["signals"] == 0


class FlakyLLM(FakeLLM):
    """Fails the first ``outages`` calls, then answers like FakeLLM."""

    def __init__(self, outages: int):
        super().__init__()
        self.outages = outages

    def invoke(self, messages):
        if len(self.calls) < self.outages:
            self.calls.append(messages)
            raise RuntimeError("overloaded")
        return super().invoke(messages)


def test_an_hour_whose_calls_failed_for_nothing_is_asked_again_after_a_pause(store, tmp_path):
    load(store, price_path(30), 30)
    load_prompt_inputs(store, 30)
    market = HistoricalOKX(store)
    cache = Ledger(tmp_path / "cache.sqlite")
    pauses, lines = [], []
    result, stats, stopped = rerun(
        store, cache, signaler(tmp_path, market, FlakyLLM(outages=2)), market, T0, T0 + 2 * HOUR_MS,
        watchlist=(BTC,), workers=1, sleep=pauses.append, log=lines.append,
    )
    assert stopped is None and result is not None
    assert (stats.hours, stats.calls, stats.failures) == (2, 4, 0)
    assert stats.spent == pytest.approx(2 * CALL_COST)  # the failed calls cost nothing
    assert pauses == [RETRY_PAUSE, RETRY_PAUSE * 2]
    assert sum("retrying in" in line for line in lines) == 2
    assert cache_summary(cache)["signals"] == 2


def test_a_paid_answer_without_a_signal_is_cached_as_a_failure(store, tmp_path):
    load(store, price_path(30), 30)
    load_prompt_inputs(store, 30)
    market = HistoricalOKX(store)
    cache = Ledger(tmp_path / "cache.sqlite")
    llm = FakeLLM(AIMessage(content="I cannot say.", usage_metadata=dict(USAGE)))
    result, stats, stopped = rerun(
        store, cache, signaler(tmp_path, market, llm), market, T0, T0 + 2 * HOUR_MS,
        watchlist=(BTC,), workers=1,
    )
    assert stopped is None and stats.failures == 2 and stats.spent == pytest.approx(2 * CALL_COST)
    assert cache_summary(cache) | {"fingerprint": None} == {
        "fingerprint": None, "hours": 2, "signals": 2, "failures": 2,
        "cost_usd": pytest.approx(2 * CALL_COST), "first": T0 + 3 * MINUTE_MS, "last": T0 + HOUR_MS + 3 * MINUTE_MS,
    }


def test_a_cache_belongs_to_one_model_and_prompt(store, tmp_path):
    market = HistoricalOKX(store)
    cache = Ledger(tmp_path / "cache.sqlite")
    cache.set("fingerprint", {"model": "other-model", "prompt": "v0"})
    with pytest.raises(ValueError, match="other-model"):
        Rerun(signaler(tmp_path, market), market, cache, watchlist=(BTC,))


def test_the_signaler_must_read_the_engines_market(store, tmp_path):
    market = HistoricalOKX(store)
    with pytest.raises(ValueError, match="same historical market"):
        Rerun(signaler(tmp_path, HistoricalOKX(store)), market, Ledger(tmp_path / "cache.sqlite"))


# -- the command --------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """A TRADER_HOME whose history store holds 30 hours of every watched coin."""
    monkeypatch.setenv("TRADER_HOME", str(tmp_path))
    monkeypatch.delenv("TRADER_CAPITAL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "live-key")
    monkeypatch.setenv(evaluation_cli.EVAL_BACKEND_URL, "https://eval.example/v1")
    monkeypatch.setenv(evaluation_cli.EVAL_API_KEY, "eval-key")
    store = HistoryStore(evaluation_cli.store_path(Settings.from_env()))
    for coin in WATCHLIST:
        load(store, price_path(30), 30, inst=coin.swap)
        load_prompt_inputs(store, 30, inst=coin.swap)
    return tmp_path


def use_fake_llm(monkeypatch, home, fake) -> None:
    monkeypatch.setattr(evaluation_cli, "evaluation_llm", lambda settings, url, key: None)
    monkeypatch.setattr(
        evaluation_cli, "Signaler",
        lambda settings, okx, llm=None: Signaler(settings, okx, llm=fake, results_dir=home / "logs"),
    )


def test_the_rerun_command_fills_a_cache_the_replay_command_reads(home, monkeypatch):
    llm = FakeLLM()
    use_fake_llm(monkeypatch, home, llm)
    cache = home / "rerun.sqlite"
    runner = CliRunner()
    done = runner.invoke(app, [
        "evaluate", "rerun", "2026-01-02", "2026-01-02T03:00", "--no-fetch", "--cache", str(cache),
        "--budget", "5",
    ])
    assert done.exit_code == 0, done.output
    assert "本次：3 小时，9 次调用（0 次失败），复用 0 条" in done.output
    assert len(llm.calls) == 9
    replayed = runner.invoke(app, [
        "evaluate", "replay", "2026-01-02", "2026-01-02T03:00", "--no-fetch", "--ledger", str(cache),
    ])
    assert replayed.exit_code == 0, replayed.output
    assert "| 默认 |" in replayed.output


def test_the_rerun_command_reports_an_early_stop(home, monkeypatch):
    use_fake_llm(monkeypatch, home, FakeLLM())
    done = CliRunner().invoke(app, [
        "evaluate", "rerun", "2026-01-02", "2026-01-02T05:00", "--no-fetch",
        "--cache", str(home / "rerun.sqlite"), "--budget", str(4.5 * CALL_COST),
    ])
    assert done.exit_code == 2, done.output
    assert "提前停止：BudgetExhausted" in done.output
    # The budget is the cache's total: what the first run spent is gone from it.
    again = CliRunner().invoke(app, [
        "evaluate", "rerun", "2026-01-02", "2026-01-02T05:00", "--no-fetch",
        "--cache", str(home / "rerun.sqlite"), "--budget", str(4.5 * CALL_COST),
    ])
    assert again.exit_code == 2, again.output
    assert "本次还可花 0.00" in again.output and "0 次调用" in again.output


# -- the evaluation's own endpoint and key --------------------------------------

RERUN = ["evaluate", "rerun", "2026-01-02", "2026-01-02T03:00", "--no-fetch"]


@pytest.mark.parametrize("unset", [evaluation_cli.EVAL_BACKEND_URL, evaluation_cli.EVAL_API_KEY])
def test_the_rerun_command_needs_the_evaluations_endpoint_and_key(home, monkeypatch, unset):
    llm = FakeLLM()
    use_fake_llm(monkeypatch, home, llm)
    monkeypatch.delenv(unset)
    done = CliRunner().invoke(app, [*RERUN, "--cache", str(home / "rerun.sqlite")])
    assert done.exit_code == 2, done.output
    assert unset in done.output
    assert not llm.calls and not (home / "rerun.sqlite").exists()


def test_the_rerun_command_refuses_a_key_the_live_jobs_use(home, monkeypatch):
    llm = FakeLLM()
    use_fake_llm(monkeypatch, home, llm)
    monkeypatch.setenv(evaluation_cli.EVAL_API_KEY, "live-key")
    done = CliRunner().invoke(app, [*RERUN, "--cache", str(home / "rerun.sqlite")])
    assert done.exit_code == 2, done.output
    assert evaluation_cli.EVAL_API_KEY in done.output and "live-key" not in done.output
    assert not llm.calls and not (home / "rerun.sqlite").exists()


def test_the_rerun_command_warns_when_the_evaluations_endpoint_is_the_live_one(home, monkeypatch):
    use_fake_llm(monkeypatch, home, FakeLLM())
    monkeypatch.setitem(DEFAULT_CONFIG, "deep_think_backend_url", None)
    monkeypatch.setitem(DEFAULT_CONFIG, "backend_url", "https://EVAL.example/v1/")
    done = CliRunner().invoke(app, [*RERUN, "--cache", str(home / "rerun.sqlite")])
    assert done.exit_code == 0, done.output
    assert evaluation_cli.EVAL_BACKEND_URL in done.output


@pytest.mark.filterwarnings("ignore:Model 'claude-sonnet-5.5' is not in the known model list")
def test_the_evaluations_model_is_the_live_one_on_its_own_endpoint_and_key(tmp_path, monkeypatch):
    live = {
        "llm_provider": "anthropic", "deep_think_provider": None, "deep_think_llm": "claude-sonnet-5.5",
        "backend_url": "https://live.example", "deep_think_backend_url": None,
    }
    for name, value in live.items():
        monkeypatch.setitem(DEFAULT_CONFIG, name, value)
    settings = Settings.with_overrides(tmp_path)
    llm = evaluation_cli.evaluation_llm(settings, "https://eval.example", "eval-key")
    assert llm.model == "claude-sonnet-5.5"
    assert llm.anthropic_api_url == "https://eval.example"
    assert llm.anthropic_api_key.get_secret_value() == "eval-key"
    assert evaluation_cli.live_endpoint(settings) == "https://live.example"
