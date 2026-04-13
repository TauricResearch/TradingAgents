import json
import asyncio

from services.analysis_service import AnalysisService
from services.job_service import JobService
from services.migration_flags import load_migration_flags
from services.request_context import build_request_context
from services.result_store import ResultStore


class DummyPortfolioGateway:
    def __init__(self):
        self.saved = []

    def get_watchlist(self):
        return [{"ticker": "AAPL", "name": "Apple"}]

    async def get_positions(self, account=None):
        return [{"ticker": "AAPL", "account": account or "默认账户"}]

    def get_accounts(self):
        return {"accounts": {"默认账户": {}}}

    def get_recommendations(self, date=None, limit=50, offset=0):
        return {"recommendations": [], "total": 0, "limit": limit, "offset": offset}

    def get_recommendation(self, date, ticker):
        return None

    def save_recommendation(self, date, ticker, data):
        self.saved.append((date, ticker, data))


def test_load_migration_flags_from_env(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_USE_APPLICATION_SERVICES", "1")
    monkeypatch.setenv("TRADINGAGENTS_USE_RESULT_STORE", "true")
    monkeypatch.setenv("TRADINGAGENTS_USE_REQUEST_CONTEXT", "0")

    flags = load_migration_flags()

    assert flags.use_application_services is True
    assert flags.use_result_store is True
    assert flags.use_request_context is False


def test_build_request_context_defaults():
    context = build_request_context(api_key="secret", metadata={"source": "test"})

    assert context.api_key == "secret"
    assert context.request_id
    assert context.metadata == {"source": "test"}


def test_result_store_round_trip(tmp_path):
    gateway = DummyPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)

    store.save_task_status("task-1", {"task_id": "task-1", "status": "running"})

    restored = store.restore_task_results()
    positions = asyncio.run(store.get_positions("模拟账户"))

    assert restored["task-1"]["status"] == "running"
    assert positions == [{"ticker": "AAPL", "account": "模拟账户"}]


def test_job_service_create_and_fail_job():
    task_results = {}
    analysis_tasks = {}
    processes = {}
    persisted = {}

    service = JobService(
        task_results=task_results,
        analysis_tasks=analysis_tasks,
        processes=processes,
        persist_task=lambda task_id, data: persisted.setdefault(task_id, json.loads(json.dumps(data))),
        delete_task=lambda task_id: persisted.pop(task_id, None),
    )

    state = service.create_portfolio_job(task_id="port_1", total=2)
    assert state["total"] == 2
    assert processes["port_1"] is None

    failed = service.fail_job("port_1", "boom")
    assert failed["status"] == "failed"
    assert persisted["port_1"]["error"] == "boom"


def test_analysis_service_build_recommendation_record():
    rec = AnalysisService._build_recommendation_record(
        stdout='\n'.join([
            'SIGNAL_DETAIL:{"quant_signal":"BUY","llm_signal":"HOLD","confidence":0.75}',
            "ANALYSIS_COMPLETE:OVERWEIGHT",
        ]),
        ticker="AAPL",
        stock={"name": "Apple"},
        date="2026-04-13",
    )

    assert rec["ticker"] == "AAPL"
    assert rec["decision"] == "OVERWEIGHT"
    assert rec["quant_signal"] == "BUY"
    assert rec["llm_signal"] == "HOLD"
    assert rec["confidence"] == 0.75
