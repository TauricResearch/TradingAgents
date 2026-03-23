import pytest
from api.store.runs_store import RunsStore
from api.models.run import RunConfig, RunStatus


def test_create_and_get_run():
    store = RunsStore()
    config = RunConfig(ticker="NVDA", date="2024-05-10")
    run = store.create(config)
    assert run.id is not None
    assert run.status == RunStatus.QUEUED
    fetched = store.get(run.id)
    assert fetched.ticker == "NVDA"


def test_list_runs():
    store = RunsStore()
    store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.create(RunConfig(ticker="AAPL", date="2024-05-09"))
    runs = store.list_all()
    assert len(runs) == 2


def test_update_run_status():
    store = RunsStore()
    run = store.create(RunConfig(ticker="NVDA", date="2024-05-10"))
    store.update_status(run.id, RunStatus.RUNNING)
    assert store.get(run.id).status == RunStatus.RUNNING
