from __future__ import annotations

import pytest

from tradingagents.dashboard.storage import AnalysisRepository


@pytest.mark.unit
def test_repository_save_and_list_round_trip(tmp_path, sample_record):
    repository = AnalysisRepository(tmp_path)
    stored = repository.save(sample_record)

    runs = repository.list_runs()

    assert len(runs) == 1
    assert runs[0]["ticker"] == "NVDA"
    assert runs[0]["rating"] == "Hold"
    assert stored["structured_path"].endswith(f"{stored['run_id']}.json")
    assert repository.latest_generated_at() == "2026-04-29T23:00:00+00:00"


@pytest.mark.unit
def test_repository_get_run_returns_full_payload(tmp_path, sample_record):
    repository = AnalysisRepository(tmp_path)
    stored = repository.save(sample_record)

    fetched = repository.get_run(stored["run_id"])

    assert fetched is not None
    assert fetched["run_id"] == stored["run_id"]
    assert fetched["reports"]["final_trade_decision"].startswith("**Rating**: Hold")
