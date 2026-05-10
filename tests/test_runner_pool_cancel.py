from __future__ import annotations

from gui import storage
from service.runner_pool import ManagedRun, RunnerPool


class FakeHandle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def test_cancel_persists_run_error(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "gui.db")
    storage.init_db()
    storage.create_run(
        run_id="run-cancel",
        ticker="NVDA",
        trade_date="2026-05-10",
        provider="openai",
        deep_model="gpt-5.4",
        quick_model="gpt-5.4-mini",
        debate_rounds=1,
        risk_rounds=1,
        vendors={"core_stock_apis": "yfinance"},
    )

    handle = FakeHandle()
    pool = RunnerPool()
    managed = ManagedRun(run_id="run-cancel", handle=handle)  # type: ignore[arg-type]
    pool._runs["run-cancel"] = managed

    assert pool.cancel("run-cancel") is True

    row = storage.get_run("run-cancel")
    assert handle.cancelled is True
    assert row is not None
    assert row["status"] == "error"
    assert row["error_message"] == "Cancelled by user."
