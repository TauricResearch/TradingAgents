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


class TestPauseResume:
    def test_pause_blocks_iterations(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        fake_propagate.sleep_s = 0.02
        handle = background_runs.register_handle(
            "bgr_PAUSE1", "NVDA", "2024-01-01", "2024-01-10", "1d", parallel=1, total=10,
        )
        def _pause_after():
            time.sleep(0.05)
            handle.pause_event.set()
        threading.Thread(target=_pause_after).start()
        t0 = time.monotonic()
        background_runs._run(handle, [f"2024-01-{i:02d}" for i in range(1, 11)])
        elapsed = time.monotonic() - t0
        assert elapsed < 5.0


class TestTagRun:
    def test_tag_run_adds_fields_to_most_recent_run_json(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.record_in_storage = False
        background_runs._run_one("NVDA", "2024-01-05")
        from web.server.background_runs import _tag_run, BackgroundRunState
        state = BackgroundRunState(
            job_id="bgr_TAG1", ticker="NVDA", date_from="2024-01-05",
            date_to="2024-01-05", every="1d", parallel=1, total=1,
        )
        # _run_one with record_in_storage=False doesn't write a run.json,
        # so create one manually under DATA_ROOT for _tag_run to find.
        run_dir = background_runs.DATA_ROOT / "NVDA" / "2024-01-05" / "run_manual"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")

        _tag_run(state, "2024-01-05", iteration_index=7)
        target = background_runs.DATA_ROOT / "NVDA" / "2024-01-05" / "run_manual" / "run.json"
        assert target.exists()
        data = json.loads(target.read_text())
        assert data["background_run_id"] == "bgr_TAG1"
        assert data["background_run_iteration_index"] == 7

    def test_tag_run_no_op_when_no_run_json(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import _tag_run, BackgroundRunState
        state = BackgroundRunState(
            job_id="bgr_TAG2", ticker="ZZZZ", date_from="2024-01-05",
            date_to="2024-01-05", every="1d", parallel=1, total=1,
        )
        with caplog.at_level("WARNING"):
            _tag_run(state, "2024-01-05", iteration_index=0)
        # _tag_run uses DATA_ROOT which is tmp_path, and it does NOT create dirs
        assert not (background_runs.DATA_ROOT / "ZZZZ" / "2024-01-05").exists()


class TestHasDoneRun:
    def test_returns_true_when_done_run_exists(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        run_dir = tmp_path / "NVDA" / "2024-02-01" / "run_x"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")
        assert _has_done_run("NVDA", "2024-02-01") is True

    def test_returns_false_when_status_running(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        run_dir = tmp_path / "NVDA" / "2024-02-02" / "run_x"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "running"}', encoding="utf-8")
        assert _has_done_run("NVDA", "2024-02-02") is False

    def test_returns_false_when_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import _has_done_run
        assert _has_done_run("ZZZZ", "2024-02-03") is False

    def test_returns_false_when_malformed_json(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        run_dir = tmp_path / "NVDA" / "2024-02-04" / "run_x"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("not json", encoding="utf-8")
        assert _has_done_run("NVDA", "2024-02-04") is False


class TestRecordIterationError:
    def test_records_error_to_json(self, tmp_path, monkeypatch):
        from web.server.background_runs import _record_iteration_error, iteration_errors_path
        from web.server.background_runs import BackgroundRunState, job_dir
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_ERR1", ticker="X", date_from="2024-01-01",
            date_to="2024-01-01", every="1d", parallel=1, total=1,
        )
        job_dir(state.job_id).mkdir(parents=True, exist_ok=True)
        _record_iteration_error(state, "2024-01-01", "RuntimeError: boom")
        data = json.loads(iteration_errors_path(state.job_id).read_text())
        assert data["2024-01-01"] == "RuntimeError: boom"

    def test_appends_to_existing_errors(self, tmp_path, monkeypatch):
        from web.server.background_runs import _record_iteration_error, iteration_errors_path
        from web.server.background_runs import BackgroundRunState, job_dir
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_ERR2", ticker="X", date_from="2024-01-01",
            date_to="2024-01-02", every="1d", parallel=1, total=2,
        )
        job_dir(state.job_id).mkdir(parents=True, exist_ok=True)
        _record_iteration_error(state, "2024-01-01", "first")
        _record_iteration_error(state, "2024-01-02", "second")
        data = json.loads(iteration_errors_path(state.job_id).read_text())
        assert data == {"2024-01-01": "first", "2024-01-02": "second"}


class TestETA:
    def test_eta_zero_when_complete(self):
        from web.server.background_runs import BackgroundRunState
        s = BackgroundRunState(
            job_id="bgr_ETA1", ticker="X", date_from="2024-01-01",
            date_to="2024-01-10", every="1d", parallel=1, total=10,
        )
        s.current_index = 10
        s.avg_duration_s = 50.0
        s._recompute_eta()
        assert s.eta_s == 0

    def test_eta_uses_avg_times_remaining_over_parallel(self):
        from web.server.background_runs import BackgroundRunState
        s = BackgroundRunState(
            job_id="bgr_ETA2", ticker="X", date_from="2024-01-01",
            date_to="2024-01-10", every="1d", parallel=2, total=100,
        )
        s.current_index = 20
        s.avg_duration_s = 50.0
        s._recompute_eta()
        assert s.eta_s == 2000

    def test_record_duration_updates_avg_and_eta(self):
        from web.server.background_runs import BackgroundRunState
        s = BackgroundRunState(
            job_id="bgr_ETA3", ticker="X", date_from="2024-01-01",
            date_to="2024-01-10", every="1d", parallel=1, total=10,
        )
        s.record_duration(50.0)
        s.record_duration(60.0)
        s.record_duration(40.0)
        assert s.avg_duration_s == 50.0
        assert s.durations_s == [50.0, 60.0, 40.0]
        assert s.eta_s == 500


class TestLoadExistingJobs:
    def test_resumes_running_job(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        from web.server.background_runs import (
            job_dir, iteration_dates_path, BackgroundRunState, _load_existing_jobs,
        )
        job_id = "bgr_RESUME1"
        d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
        state = BackgroundRunState(
            job_id=job_id, ticker="NVDA", date_from="2024-03-01",
            date_to="2024-03-05", every="1d", parallel=1, total=5,
        )
        state.status = "running"
        state.current_index = 0
        state.persist()
        iteration_dates_path(job_id).write_text(
            "\n".join([f"2024-03-0{i}" for i in range(1, 6)]),
            encoding="utf-8",
        )
        _load_existing_jobs()
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        handle.thread.join(timeout=5.0)
        assert handle.state.status == "done"
        assert handle.state.current_index == 5
        assert len(fake_propagate.calls) == 5

    def test_resume_skips_already_done_dates(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import (
            job_dir, iteration_dates_path, BackgroundRunState, _load_existing_jobs,
        )
        run_dir = background_runs.DATA_ROOT / "NVDA" / "2024-03-02" / "run_pre"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")

        job_id = "bgr_RESUME2"
        d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
        state = BackgroundRunState(
            job_id=job_id, ticker="NVDA", date_from="2024-03-01",
            date_to="2024-03-05", every="1d", parallel=1, total=5,
        )
        state.status = "running"
        state.persist()
        iteration_dates_path(job_id).write_text(
            "\n".join([f"2024-03-0{i}" for i in range(1, 6)]),
            encoding="utf-8",
        )
        _load_existing_jobs()
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        handle.thread.join(timeout=5.0)
        assert len(fake_propagate.calls) == 4
        assert handle.state.current_index == 5

    def test_does_not_resume_paused_job(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        from web.server.background_runs import (
            job_dir, iteration_dates_path, BackgroundRunState, _load_existing_jobs,
        )
        job_id = "bgr_RESUME3"
        d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
        state = BackgroundRunState(
            job_id=job_id, ticker="NVDA", date_from="2024-04-01",
            date_to="2024-04-03", every="1d", parallel=1, total=3,
        )
        state.status = "paused"
        state.persist()
        iteration_dates_path(job_id).write_text(
            "\n".join(["2024-04-01", "2024-04-02", "2024-04-03"]),
            encoding="utf-8",
        )
        _load_existing_jobs()
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        assert handle.thread is None
        assert len(fake_propagate.calls) == 0

    def test_does_not_resume_terminal_jobs(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        from web.server.background_runs import job_dir, BackgroundRunState, _load_existing_jobs
        for terminal_status in ("done", "cancelled", "error"):
            job_id = f"bgr_TERM_{terminal_status}"
            d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
            state = BackgroundRunState(
                job_id=job_id, ticker="NVDA", date_from="2024-01-01",
                date_to="2024-01-01", every="1d", parallel=1, total=1,
            )
            state.status = terminal_status
            state.persist()
        _load_existing_jobs()
        for _status in ("done", "cancelled", "error"):
            job_id = f"bgr_TERM_{_status}"
            assert background_runs.get_handle(job_id) is None


class TestStart:
    def test_start_creates_job_and_returns_id(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        job_id = background_runs.start(
            ticker="NVDA", date_from="2024-05-01", date_to="2024-05-03",
            every="1d", parallel=1,
        )
        assert job_id.startswith("bgr_")
        assert "NVDA" in job_id
        state = background_runs.BackgroundRunState.load(job_id)
        assert state.ticker == "NVDA"
        assert state.total == 3
        dates = background_runs.iteration_dates_path(job_id).read_text().splitlines()
        assert dates == ["2024-05-01", "2024-05-02", "2024-05-03"]
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        handle.thread.join(timeout=5.0)
        assert handle.state.status == "done"
        assert handle.state.current_index == 3

    def test_start_rejects_invalid_inputs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        with pytest.raises(ValueError, match="date_from"):
            background_runs.start("NVDA", "2024-06-30", "2024-01-01", "1d", 1)
        with pytest.raises(ValueError, match="future"):
            background_runs.start("NVDA", "2024-01-01", "2099-01-01", "1d", 1)
        with pytest.raises(ValueError, match="every"):
            background_runs.start("NVDA", "2024-01-01", "2024-01-05", "5d", 1)
        with pytest.raises(ValueError, match="parallel"):
            background_runs.start("NVDA", "2024-01-01", "2024-01-05", "1d", 8)
        with pytest.raises(ValueError, match="ticker"):
            background_runs.start("lowercase", "2024-01-01", "2024-01-05", "1d", 1)


class TestGetAndList:
    def test_get_returns_state_dict(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        job_id = background_runs.start("MU", "2024-05-06", "2024-05-06", "1d", 1)
        h = background_runs.get_handle(job_id)
        if h and h.thread:
            h.thread.join(timeout=5.0)
        out = background_runs.get(job_id)
        assert out["job_id"] == job_id
        assert out["ticker"] == "MU"
        assert out["total"] == 1
        assert out["current_index"] >= 0

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            background_runs.get("bgr_DOES_NOT_EXIST")

    def test_list_jobs_returns_recent_first(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs, "_data_root", lambda: tmp_path)
        id1 = background_runs.start("AAPL", "2024-05-06", "2024-05-06", "1d", 1)
        h1 = background_runs.get_handle(id1)
        if h1 and h1.thread:
            h1.thread.join(timeout=5.0)
        time.sleep(0.01)
        id2 = background_runs.start("MSFT", "2024-05-06", "2024-05-06", "1d", 1)
        h2 = background_runs.get_handle(id2)
        if h2 and h2.thread:
            h2.thread.join(timeout=5.0)
        out = background_runs.list_jobs()
        assert len(out) == 2
        assert out[0]["job_id"] == id2
        assert out[1]["job_id"] == id1
        for entry in out:
            assert {"job_id", "ticker", "status", "current_index", "total"}.issubset(entry.keys())
