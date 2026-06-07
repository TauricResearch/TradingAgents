"""Unit tests for web.server.background_runs."""
from __future__ import annotations

import json
import threading
import time

import pytest

from web.server import background_runs


class TestDates:
    def test_1d_simple_range(self):
        out = background_runs.dates("2024-01-01", "2024-01-05", "1d")
        assert out == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    def test_1d_skips_weekends(self):
        # Jan 5, 2024 was a Friday; Jan 6-7 were Sat/Sun; Jan 8 was a Monday.
        out = background_runs.dates("2024-01-05", "2024-01-08", "1d")
        assert out == ["2024-01-05", "2024-01-08"]

    def test_1w_lands_on_mondays(self):
        out = background_runs.dates("2024-01-01", "2024-01-29", "1w")
        # 2024-01-01 is a Monday; subsequent Mondays.
        assert out == ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29"]

    def test_2w_lands_every_other_monday(self):
        out = background_runs.dates("2024-01-01", "2024-01-29", "2w")
        assert out == ["2024-01-01", "2024-01-15", "2024-01-29"]

    def test_1mo_lands_same_day_of_month(self):
        out = background_runs.dates("2024-01-15", "2024-05-15", "1mo")
        assert out == ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15", "2024-05-15"]

    def test_1mo_caps_to_last_day_for_short_months(self):
        # 2024 is a leap year; Feb caps at 29.
        out = background_runs.dates("2024-01-31", "2024-04-30", "1mo")
        assert out == ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"]

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError, match="date_from"):
            background_runs.dates("2024-06-30", "2024-01-01", "1d")

    def test_invalid_every_raises(self):
        with pytest.raises(ValueError, match="every"):
            background_runs.dates("2024-01-01", "2024-01-05", "5d")

    def test_invalid_date_format_raises(self):
        with pytest.raises(ValueError):
            background_runs.dates("not-a-date", "2024-01-05", "1d")

    def test_same_from_and_to_returns_single_date(self):
        out = background_runs.dates("2024-01-15", "2024-01-15", "1d")
        assert out == ["2024-01-15"]


class TestBackgroundRunState:
    def test_persist_creates_file_with_full_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = background_runs.BackgroundRunState(
            job_id="bgr_TEST", ticker="NVDA", date_from="2024-01-01",
            date_to="2024-01-05", every="1d", parallel=1, total=5,
        )
        state.current_index = 2
        state.avg_duration_s = 47.3
        state.durations_s = [50.0, 44.6]
        state.eta_s = 150
        state.status = "running"
        state.persist()
        data = json.loads(background_runs.state_path(state.job_id).read_text())
        assert data["ticker"] == "NVDA"
        assert data["current_index"] == 2
        assert data["avg_duration_s"] == 47.3
        assert data["durations_s"] == [50.0, 44.6]
        assert data["eta_s"] == 150
        assert data["status"] == "running"
        assert data["finished_at"] is None

    def test_persist_writes_atomically(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = background_runs.BackgroundRunState(
            job_id="bgr_TEST2", ticker="MU", date_from="2024-01-01",
            date_to="2024-01-05", every="1d", parallel=1, total=5,
        )
        state.status = "running"
        state.persist()
        state.status = "done"
        state.finished_at = "2024-01-01T15:00:00Z"
        state.persist()
        data = json.loads(background_runs.state_path(state.job_id).read_text())
        assert data["status"] == "done"
        assert data["finished_at"] == "2024-01-01T15:00:00Z"

    def test_load_returns_parsed_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = background_runs.BackgroundRunState(
            job_id="bgr_TEST3", ticker="AAPL", date_from="2024-02-01",
            date_to="2024-02-05", every="1d", parallel=1, total=5,
        )
        state.status = "paused"
        state.persist()
        loaded = background_runs.BackgroundRunState.load("bgr_TEST3")
        assert loaded.ticker == "AAPL"
        assert loaded.status == "paused"
        assert loaded.total == 5

    def test_load_missing_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        with pytest.raises(FileNotFoundError):
            background_runs.BackgroundRunState.load("bgr_MISSING")


class TestJobHandleRegistry:
    def test_register_and_get_handle(self):
        from web.server.background_runs import _jobs, register_handle, get_handle
        h = register_handle(
            job_id="bgr_REG1", ticker="X", date_from="2024-01-01",
            date_to="2024-01-02", every="1d", parallel=1, total=2,
        )
        assert h.job_id == "bgr_REG1"
        assert h.state.ticker == "X"
        assert _jobs["bgr_REG1"] is h
        assert get_handle("bgr_REG1") is h

    def test_get_handle_missing_returns_none(self):
        from web.server.background_runs import get_handle
        assert get_handle("bgr_DOES_NOT_EXIST") is None

    def test_unregister_removes_handle(self):
        from web.server.background_runs import _jobs, register_handle, unregister_handle
        register_handle("bgr_REG2", "X", "2024-01-01", "2024-01-02", "1d", 1, 2)
        assert "bgr_REG2" in _jobs
        unregister_handle("bgr_REG2")
        assert "bgr_REG2" not in _jobs


class TestRunOne:
    def test_run_one_returns_duration_and_decision(self, tmp_path, monkeypatch, fake_propagate):
        fake_propagate.record_in_storage = False
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        result = background_runs._run_one("NVDA", "2024-01-02")
        assert result.duration_s >= 0
        assert result.ticker == "NVDA"
        assert result.date_iso == "2024-01-02"
        assert result.decision is not None

    def test_run_one_records_call(self, tmp_path, monkeypatch, fake_propagate):
        fake_propagate.record_in_storage = False
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        background_runs._run_one("MU", "2024-01-03")
        assert ("MU", "2024-01-03") in [(c[0], c[1]) for c in fake_propagate.calls]

    def test_run_one_raises_on_failure(self, tmp_path, monkeypatch, fake_propagate):
        fake_propagate.record_in_storage = False
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.fail_on_dates.add("2024-01-04")
        with pytest.raises(RuntimeError):
            background_runs._run_one("AAPL", "2024-01-04")


class TestRunSequential:
    def _setup_root(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)

    def test_run_processes_all_dates(self, tmp_path, monkeypatch, fake_propagate):
        self._setup_root(tmp_path, monkeypatch)
        handle = background_runs.register_handle(
            "bgr_SEQ1", "NVDA", "2024-01-01", "2024-01-03", "1d", parallel=1, total=3,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(fake_propagate.calls) == 3
        assert handle.state.status == "done"
        assert handle.state.current_index == 3
        assert handle.state.finished_at is not None

    def test_run_skips_dates_already_done_on_disk(self, tmp_path, monkeypatch, fake_propagate):
        """Resume-safety: dates with a done run.json are skipped."""
        self._setup_root(tmp_path, monkeypatch)
        run_dir = background_runs.DATA_ROOT / "NVDA" / "2024-01-02" / "run_pre"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")

        handle = background_runs.register_handle(
            "bgr_SEQ2", "NVDA", "2024-01-01", "2024-01-03", "1d", parallel=1, total=3,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(fake_propagate.calls) == 2
        assert handle.state.current_index == 3

    def test_run_records_iteration_error_continues(self, tmp_path, monkeypatch, fake_propagate):
        self._setup_root(tmp_path, monkeypatch)
        fake_propagate.fail_on_dates.add("2024-01-02")
        handle = background_runs.register_handle(
            "bgr_SEQ3", "NVDA", "2024-01-01", "2024-01-03", "1d", parallel=1, total=3,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(fake_propagate.calls) == 3
        assert handle.state.status == "done"
        errors = json.loads(background_runs.iteration_errors_path(handle.job_id).read_text())
        assert "2024-01-02" in errors


class TestRunParallel:
    def test_parallel_runs_concurrently(self, tmp_path, monkeypatch, fake_propagate):
        """With parallel=2 and sleep=100ms, total wall-clock for 4 dates
        should be roughly 200ms (not 400ms). Use a loose bound."""
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        fake_propagate.sleep_s = 0.1
        handle = background_runs.register_handle(
            "bgr_PAR1", "NVDA", "2024-01-01", "2024-01-04", "1d", parallel=2, total=4,
        )
        t0 = time.monotonic()
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
        elapsed = time.monotonic() - t0
        assert elapsed < 0.35, f"expected <350ms, got {elapsed*1000:.0f}ms"
        assert len(fake_propagate.calls) == 4
        assert handle.state.current_index == 4

    def test_parallel_does_not_double_process(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        fake_propagate.sleep_s = 0.05
        handle = background_runs.register_handle(
            "bgr_PAR2", "NVDA", "2024-01-01", "2024-01-04", "1d", parallel=4, total=4,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
        assert len(fake_propagate.calls) == 4
        assert handle.state.current_index == 4


class TestCancel:
    def test_cancel_stops_within_one_iteration(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        fake_propagate.sleep_s = 0.05
        handle = background_runs.register_handle(
            "bgr_CAN1", "NVDA", "2024-01-01", "2024-01-10", "1d", parallel=1, total=10,
        )
        def _trigger():
            time.sleep(0.12)
            handle.cancel_event.set()
        t = threading.Thread(target=_trigger); t.start()
        background_runs._run(handle, [f"2024-01-{i:02d}" for i in range(1, 11)])
        t.join()
        assert handle.state.current_index < 10
        assert handle.state.status == "cancelled"
        assert handle.state.finished_at is not None
