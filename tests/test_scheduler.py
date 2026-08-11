from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

import cli.main as cli_main
from tradingagents.automation import AutomationSettings
from tradingagents.automation_state import AutomationState
from tradingagents.scheduler import AutomationScheduler

NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)


class FakeService:
    def __init__(self, settings):
        self.settings = settings
        self.analysis_calls = []
        self.position_calls = []
        self.analysis_error = None

    def run_analysis_cycle(self, due_time):
        self.analysis_calls.append(due_time)
        if self.analysis_error is not None:
            raise self.analysis_error

    def track_positions(self, due_time):
        self.position_calls.append(due_time)


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


def test_position_interval_can_be_due_before_analysis(fake_service, state):
    state.mark_task_run("analysis", NOW)
    state.mark_task_run("positions", NOW - timedelta(minutes=30))
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once()
    assert fake_service.analysis_calls == []
    assert fake_service.position_calls == [NOW]


def test_held_lease_prevents_duplicate_analysis(fake_service, state):
    assert state.try_acquire_lease("analysis", "other", NOW, 900)
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)
    scheduler.run_once(force_analysis=True)
    assert fake_service.analysis_calls == []


def test_failed_analysis_is_not_marked_and_does_not_block_positions(fake_service, state, caplog):
    fake_service.analysis_error = RuntimeError("temporary failure")
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)

    scheduler.run_once()

    assert state.last_task_run("analysis") is None
    assert state.last_task_run("positions") == NOW
    assert fake_service.position_calls == [NOW]
    assert "temporary failure" in caplog.text


def test_failed_analysis_is_deferred_to_its_next_interval(fake_service, state):
    fake_service.analysis_error = RuntimeError("temporary failure")
    scheduler = AutomationScheduler(fake_service, state, now=lambda: NOW, sleep=lambda _: None)

    scheduler.run_once()
    scheduler.run_once(now=NOW + timedelta(minutes=15))
    fake_service.analysis_error = None
    scheduler.run_once(now=NOW + timedelta(minutes=30))

    assert fake_service.analysis_calls == [NOW, NOW + timedelta(minutes=30)]
    assert state.last_task_run("analysis") == NOW + timedelta(minutes=30)


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
