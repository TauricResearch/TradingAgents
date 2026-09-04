import sqlite3
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

import cli.main as cli_main
from tradingagents.automation import AutomationSettings, CycleResult, OptionCycleResult
from tradingagents.automation_state import AutomationState
from tradingagents.scheduler import AutomationScheduler

NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)


class FakeService:
    def __init__(self, settings):
        self.settings = settings
        self.analysis_calls = []
        self.position_calls = []
        self.option_calls = []
        self.analysis_error = None

    def run_analysis_cycle(self, due_time):
        self.analysis_calls.append(due_time)
        if self.analysis_error is not None:
            raise self.analysis_error

    def track_positions(self, due_time):
        self.position_calls.append(due_time)

    def manage_options(self, due_time):
        self.option_calls.append(due_time)


@pytest.fixture
def settings(tmp_path):
    return AutomationSettings(
        watchlist=("AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA"),
        batch_size=3,
        analysis_interval_minutes=30,
        position_interval_minutes=30,
        max_cash_allocation=0.30,
        decision_max_age_minutes=120,
        rebalance_threshold_usd=10.0,
        state_path=tmp_path / "state.db",
        auto_execute=False,
        alpaca_mode="paper",
        live_trading_ack="",
        options_enabled=False,
        options_auto_execute=False,
        options_max_equity_fraction=0.20,
        options_entry_time_et="10:00",
        options_earnings_path=tmp_path / "earnings.json",
        live_options_ack="",
    )


@pytest.fixture
def state(tmp_path):
    with AutomationState(tmp_path / "state.db") as automation_state:
        yield automation_state


@pytest.fixture
def fake_service(settings):
    return FakeService(settings)


def test_run_once_executes_only_due_tasks(fake_service, state):
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once()
    assert fake_service.analysis_calls == [NOW]
    assert fake_service.position_calls == [NOW]

    scheduler.run_once(now=NOW + timedelta(minutes=15))
    assert fake_service.analysis_calls == [NOW]
    assert fake_service.position_calls == [NOW]

    scheduler.run_once(now=NOW + timedelta(minutes=30))
    assert fake_service.analysis_calls[-1] == NOW + timedelta(minutes=30)
    assert fake_service.position_calls[-1] == NOW + timedelta(minutes=30)


def test_scheduler_runs_options_on_fifteen_minute_deadline(fake_service, state):
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once(NOW)
    assert state.last_task_run("analysis") == NOW
    assert state.last_task_run("positions") == NOW
    assert state.last_task_run("options") == NOW
    scheduler.run_once(NOW + timedelta(minutes=14))
    assert state.last_task_run("analysis") == NOW
    assert state.last_task_run("positions") == NOW
    assert state.last_task_run("options") == NOW
    scheduler.run_once(NOW + timedelta(minutes=15))
    assert fake_service.option_calls == [NOW, NOW + timedelta(minutes=15)]
    assert state.last_task_run("options") == NOW + timedelta(minutes=15)
    assert state.last_task_run("analysis") == NOW
    assert state.last_task_run("positions") == NOW


def test_position_interval_can_be_due_before_analysis(fake_service, state):
    state.mark_task_run("analysis", NOW)
    state.mark_task_run("positions", NOW - timedelta(minutes=30))
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once()
    assert fake_service.analysis_calls == []
    assert fake_service.position_calls == [NOW]


def test_long_analysis_uses_fresh_lease_time_for_following_positions(settings, state):
    current = {"value": NOW}
    long_settings = replace(
        settings,
        analysis_interval_minutes=60,
        position_interval_minutes=30,
    )

    class ClockAdvancingService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            current["value"] += timedelta(minutes=31)

    service = ClockAdvancingService(long_settings)
    scheduler = AutomationScheduler(
        service,
        state,
        now=lambda: current["value"],
        sleep=lambda _: None,
    )

    scheduler.run_once(now=NOW)

    assert service.position_calls == [NOW]
    assert state.last_task_run("positions") == NOW


def test_position_deadline_failure_after_long_analysis_defers_from_fresh_time(
    settings, state, monkeypatch
):
    current = {"value": NOW}
    long_settings = replace(
        settings,
        analysis_interval_minutes=60,
        position_interval_minutes=30,
    )

    class ClockAdvancingService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            current["value"] += timedelta(minutes=31)

    real_last_task_run = state.last_task_run
    failed = False

    def flaky_last_task_run(task):
        nonlocal failed
        if task == "positions" and not failed:
            failed = True
            raise sqlite3.OperationalError("late positions deadline failure")
        return real_last_task_run(task)

    monkeypatch.setattr(state, "last_task_run", flaky_last_task_run)
    service = ClockAdvancingService(long_settings)
    scheduler = AutomationScheduler(
        service,
        state,
        now=lambda: current["value"],
        sleep=lambda _: None,
    )

    scheduler.run_once(now=NOW)

    assert service.position_calls == []
    assert scheduler._deferred_until["positions"] == NOW + timedelta(minutes=61)
    assert scheduler._sleep_seconds(current["value"]) == 60


def test_held_lease_prevents_duplicate_analysis(fake_service, state):
    assert state.try_acquire_lease("analysis", "other", NOW, 900)
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once(force_analysis=True)
    assert fake_service.analysis_calls == []


def test_renewing_owner_blocks_forced_scheduler_past_initial_ttl(tmp_path, settings, monkeypatch):
    from tradingagents import scheduler as scheduler_module

    path = tmp_path / "shared-state.db"
    short_settings = replace(
        settings,
        analysis_interval_minutes=1,
        state_path=path,
    )
    current = {"value": NOW}
    started = threading.Event()
    release = threading.Event()
    errors = []

    class BlockingService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            started.set()
            if not release.wait(timeout=2):
                raise TimeoutError("test did not release blocking analysis")

    first_service = BlockingService(short_settings)

    def run_first():
        try:
            with AutomationState(path) as first_state:
                AutomationScheduler(
                    first_service,
                    first_state,
                    now=lambda: current["value"],
                    sleep=lambda _: None,
                ).run_once(now=NOW)
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(scheduler_module, "MAX_HEARTBEAT_SECONDS", 0.01)
    first_thread = threading.Thread(target=run_first)
    first_thread.start()
    assert started.wait(timeout=1)

    for elapsed_seconds in (30, 60, 90, 120):
        current["value"] = NOW + timedelta(seconds=elapsed_seconds)
        expected_expiry = current["value"] + timedelta(minutes=1)
        renewal_deadline = time.monotonic() + 2
        while True:
            with sqlite3.connect(path) as connection:
                row = connection.execute(
                    "SELECT expires_at FROM leases WHERE task = 'analysis'"
                ).fetchone()
            if row is not None and datetime.fromisoformat(row[0]) >= expected_expiry:
                break
            if time.monotonic() >= renewal_deadline:
                raise AssertionError("analysis lease heartbeat did not extend ownership")
            time.sleep(0.01)

    second_service = FakeService(short_settings)
    with AutomationState(path) as second_state:
        second_scheduler = AutomationScheduler(
            second_service,
            second_state,
            now=lambda: current["value"],
            sleep=lambda _: None,
        )
        second_scheduler.run_once(now=current["value"], force_analysis=True)
        assert second_service.analysis_calls == []

        release.set()
        first_thread.join(timeout=2)
        assert not first_thread.is_alive()
        assert errors == []

        second_scheduler.run_once(now=current["value"], force_analysis=True)
        assert second_service.analysis_calls == [current["value"]]


def test_heartbeat_clock_programming_error_is_reraised_without_completion(
    fake_service, state, monkeypatch
):
    from tradingagents import scheduler as scheduler_module

    scheduler_thread = threading.current_thread()
    heartbeat_called = threading.Event()

    def clock():
        if threading.current_thread() is not scheduler_thread:
            heartbeat_called.set()
            raise ValueError("invalid heartbeat clock")
        return NOW

    class WaitingService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            assert heartbeat_called.wait(timeout=1)

    service = WaitingService(fake_service.settings)
    scheduler = AutomationScheduler(service, state, now=clock, sleep=lambda _: None)
    monkeypatch.setattr(scheduler_module, "MAX_HEARTBEAT_SECONDS", 0.01)

    with pytest.raises(ValueError, match="invalid heartbeat clock"):
        scheduler.run_once(now=NOW)

    assert state.last_task_run("analysis") is None
    assert "analysis" not in scheduler._deferred_until


def test_heartbeat_programming_error_wins_without_deferral_when_service_also_fails(
    fake_service, state, monkeypatch
):
    from tradingagents import scheduler as scheduler_module

    scheduler_thread = threading.current_thread()
    heartbeat_called = threading.Event()

    def clock():
        if threading.current_thread() is not scheduler_thread:
            heartbeat_called.set()
            raise ValueError("invalid heartbeat clock")
        return NOW

    class FailingService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            assert heartbeat_called.wait(timeout=1)
            raise RuntimeError("service also failed")

    service = FailingService(fake_service.settings)
    scheduler = AutomationScheduler(service, state, now=clock, sleep=lambda _: None)
    monkeypatch.setattr(scheduler_module, "MAX_HEARTBEAT_SECONDS", 0.01)

    with pytest.raises(ValueError, match="invalid heartbeat clock"):
        scheduler.run_once(now=NOW)

    assert state.last_task_run("analysis") is None
    assert "analysis" not in scheduler._deferred_until


def test_short_configured_interval_is_not_stretched_by_lease(settings, state):
    service = FakeService(replace(settings, analysis_interval_minutes=5))
    scheduler = AutomationScheduler(service, state, now=lambda: NOW, sleep=lambda _: None)

    scheduler.run_once()
    scheduler.run_once(now=NOW + timedelta(minutes=5))

    assert service.analysis_calls == [NOW, NOW + timedelta(minutes=5)]


def test_failed_analysis_is_not_marked_and_does_not_block_positions(fake_service, state, caplog):
    fake_service.analysis_error = RuntimeError("temporary failure")
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)

    scheduler.run_once()

    assert state.last_task_run("analysis") is None
    assert state.last_task_run("positions") == NOW
    assert fake_service.position_calls == [NOW]
    assert "temporary failure" in caplog.text


def test_analysis_cycle_result_is_logged_concisely(settings, state, caplog):
    class ResultService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            return CycleResult(
                "cycle-1",
                ("BTC-USD",),
                ("ETH-USD",),
                (),
                ("order-1",),
                "submission errors: ETH-USD",
            )

    scheduler = AutomationScheduler(ResultService(settings), state, now=lambda: NOW)
    with caplog.at_level("INFO"):
        scheduler.run_once()

    assert "cycle=cycle-1" in caplog.text
    assert "analyzed=BTC-USD" in caplog.text
    assert "failed=ETH-USD" in caplog.text
    assert "submitted=order-1" in caplog.text
    assert "submission errors: ETH-USD" in caplog.text


def test_scheduler_persists_latest_suppression_outcomes_with_completion(settings, tmp_path):
    path = tmp_path / "durable-state.db"

    class ResultService(FakeService):
        def run_analysis_cycle(self, due_time):
            return CycleResult("equity-cycle", (), (), (), (), "waiting for fresh decisions")

        def manage_options(self, due_time):
            return OptionCycleResult("option-cycle", (), (), "earnings blackout: NVDA")

    with AutomationState(path) as state:
        AutomationScheduler(ResultService(settings), state, now=lambda: NOW).run_once(NOW)

    with AutomationState(path) as reopened:
        assert reopened.last_task_outcome("analysis") == (
            NOW,
            "waiting for fresh decisions",
        )
        assert reopened.last_task_outcome("options") == (
            NOW,
            "earnings blackout: NVDA",
        )


def test_failed_analysis_is_deferred_to_its_next_interval(fake_service, state):
    fake_service.analysis_error = RuntimeError("temporary failure")
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)

    scheduler.run_once()
    scheduler.run_once(now=NOW + timedelta(minutes=15))
    fake_service.analysis_error = None
    scheduler.run_once(now=NOW + timedelta(minutes=30))

    assert fake_service.analysis_calls == [NOW, NOW + timedelta(minutes=30)]
    assert state.last_task_run("analysis") == NOW + timedelta(minutes=30)


def test_long_failed_task_defers_from_failure_time(settings, state):
    current = {"value": NOW}

    class LongFailingService(FakeService):
        def run_analysis_cycle(self, due_time):
            self.analysis_calls.append(due_time)
            current["value"] += timedelta(minutes=31)
            if len(self.analysis_calls) == 1:
                raise RuntimeError("late failure")

    service = LongFailingService(settings)
    scheduler = AutomationScheduler(
        service,
        state,
        now=lambda: current["value"],
        sleep=lambda _: None,
    )

    scheduler.run_once(now=NOW)
    scheduler.run_once(now=current["value"])
    scheduler.run_once(now=NOW + timedelta(minutes=61))

    assert service.analysis_calls == [NOW, NOW + timedelta(minutes=61)]


def test_invalid_scheduler_timestamp_is_not_treated_as_transient_state_io(fake_service, state):
    scheduler = AutomationScheduler(fake_service, state, sleep=lambda _: None)

    with pytest.raises(ValueError, match="timezone-aware"):
        scheduler.run_once(now=datetime(2026, 8, 11, 14, 0))


def test_failed_analysis_remains_deferred_after_scheduler_restart(settings, state):
    failed_service = FakeService(settings)
    failed_service.analysis_error = RuntimeError("temporary failure")
    AutomationScheduler(failed_service, state, now=lambda: NOW, sleep=lambda _: None).run_once()

    restarted_service = FakeService(settings)
    restarted = AutomationScheduler(
        restarted_service,
        state,
        now=lambda: NOW + timedelta(minutes=15),
        sleep=lambda _: None,
    )
    restarted.run_once()
    restarted.run_once(now=NOW + timedelta(minutes=30))

    assert restarted_service.analysis_calls == [NOW + timedelta(minutes=30)]


def test_run_once_deadline_read_failure_logs_and_defers_task(
    fake_service, state, monkeypatch, caplog
):
    real_last_task_run = state.last_task_run
    failed = False

    def flaky_last_task_run(task):
        nonlocal failed
        if task == "analysis" and not failed:
            failed = True
            raise sqlite3.OperationalError("temporary deadline read failure")
        return real_last_task_run(task)

    monkeypatch.setattr(state, "last_task_run", flaky_last_task_run)
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)

    scheduler.run_once()
    scheduler.run_once(now=NOW + timedelta(minutes=15))
    scheduler.run_once(now=NOW + timedelta(minutes=30))

    assert fake_service.analysis_calls == [NOW + timedelta(minutes=30)]
    assert fake_service.position_calls == [NOW, NOW + timedelta(minutes=30)]
    assert "temporary deadline read failure" in caplog.text


def test_foreground_loop_stops_cleanly_on_keyboard_interrupt(fake_service, state):
    sleeps = []

    def interrupt(seconds):
        sleeps.append(seconds)
        raise KeyboardInterrupt

    scheduler = AutomationScheduler(
        fake_service,
        state,
        now=lambda: NOW,
        sleep=interrupt,
    )
    scheduler.run_forever()

    assert sleeps == [60]


def test_foreground_sleep_uses_fresh_time_after_cycle(fake_service, state):
    times = iter(
        (
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW + timedelta(minutes=29, seconds=30),
        )
    )
    sleeps = []

    def interrupt(seconds):
        sleeps.append(seconds)
        raise KeyboardInterrupt

    scheduler = AutomationScheduler(
        fake_service,
        state,
        now=lambda: next(times),
        sleep=interrupt,
    )
    scheduler.run_forever()

    assert sleeps == [1]


def test_foreground_sleep_deadline_read_failure_defers_without_busy_loop(
    fake_service, state, monkeypatch, caplog
):
    real_last_task_run = state.last_task_run
    reads = 0

    def flaky_last_task_run(task):
        nonlocal reads
        reads += 1
        if reads == 3:
            raise sqlite3.OperationalError("temporary sleep deadline failure")
        return real_last_task_run(task)

    current = {"value": NOW}
    sleeps = []

    def advance_then_interrupt(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:
            current["value"] += timedelta(minutes=30)
            return
        raise KeyboardInterrupt

    monkeypatch.setattr(state, "last_task_run", flaky_last_task_run)
    scheduler = AutomationScheduler(
        fake_service,
        state,
        now=lambda: current["value"],
        sleep=advance_then_interrupt,
    )

    scheduler.run_forever()

    assert fake_service.analysis_calls == [NOW, NOW + timedelta(minutes=30)]
    assert all(0 < seconds <= 60 for seconds in sleeps)
    assert "temporary sleep deadline failure" in caplog.text


def test_batch_cli_lazily_delegates_without_prompting(monkeypatch):
    calls = []
    monkeypatch.setattr("tradingagents.scheduler.run_batch_from_config", lambda: calls.append(True))
    result = CliRunner().invoke(cli_main.app, ["batch"])
    assert result.exit_code == 0
    assert calls == [True]


def test_automate_cli_lazily_delegates(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tradingagents.scheduler.run_automation_from_config", lambda: calls.append(True)
    )
    result = CliRunner().invoke(cli_main.app, ["automate"])
    assert result.exit_code == 0
    assert calls == [True]


def test_bare_cli_still_invokes_interactive_analysis_once(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_main, "run_analysis", lambda checkpoint=None: calls.append(checkpoint))

    result = CliRunner().invoke(cli_main.app, [])

    assert result.exit_code == 0
    assert calls == [None]


def test_explicit_analyze_command_keeps_existing_delegate(monkeypatch):
    calls = []
    monkeypatch.setattr(cli_main, "run_analysis", lambda checkpoint=None: calls.append(checkpoint))

    result = CliRunner().invoke(cli_main.app, ["analyze", "--checkpoint"])

    assert result.exit_code == 0
    assert calls == [True]


def test_invalid_batch_config_exits_without_prompting(monkeypatch):
    def invalid_config():
        raise ValueError("bad watchlist")

    monkeypatch.setattr("tradingagents.scheduler.build_service_from_config", invalid_config)

    result = CliRunner().invoke(cli_main.app, ["batch"])

    assert result.exit_code != 0
    assert "bad watchlist" in result.output
    assert "Enter" not in result.output
    assert "Select" not in result.output


def test_missing_alpaca_credentials_name_variables_without_values(monkeypatch):
    from tradingagents import scheduler

    monkeypatch.setattr(
        scheduler,
        "DEFAULT_CONFIG",
        dict(
            scheduler.DEFAULT_CONFIG,
            watchlist="AAPL,MSFT,NVDA,AMZN,META,GOOG,TSLA",
            automation_state_path="unused.db",
        ),
    )
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    with pytest.raises(ValueError) as error:
        scheduler.build_service_from_config()

    assert "ALPACA_API_KEY" in str(error.value)
    assert "ALPACA_SECRET_KEY" in str(error.value)


def test_missing_credential_error_does_not_echo_present_secret(monkeypatch):
    from tradingagents import scheduler

    monkeypatch.setattr(
        scheduler,
        "DEFAULT_CONFIG",
        dict(
            scheduler.DEFAULT_CONFIG,
            watchlist="AAPL,MSFT,NVDA,AMZN,META,GOOG,TSLA",
            automation_state_path="unused.db",
        ),
    )
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.setenv("ALPACA_SECRET_KEY", "sentinel-must-not-appear")

    with pytest.raises(ValueError) as error:
        scheduler.build_service_from_config()

    assert "ALPACA_API_KEY" in str(error.value)
    assert "sentinel-must-not-appear" not in str(error.value)
