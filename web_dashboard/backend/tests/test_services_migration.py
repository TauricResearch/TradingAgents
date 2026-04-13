import json
import asyncio

from services.analysis_service import AnalysisService
from services.executor import AnalysisExecutionOutput
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
    assert context.contract_version == "v1alpha1"
    assert context.executor_type == "legacy_subprocess"
    assert context.metadata == {"source": "test"}


def test_result_store_round_trip(tmp_path):
    gateway = DummyPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)

    store.save_task_status("task-1", {"task_id": "task-1", "status": "running"})

    restored = store.restore_task_results()
    positions = asyncio.run(store.get_positions("模拟账户"))

    assert restored["task-1"]["status"] == "running"
    assert positions == [{"ticker": "AAPL", "account": "模拟账户"}]


def test_result_store_saves_result_contract(tmp_path):
    gateway = DummyPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)

    result_ref = store.save_result_contract(
        "task-2",
        {"status": "completed", "result": {"decision": "BUY"}},
    )

    saved = json.loads((tmp_path / "task_status" / result_ref).read_text())

    assert result_ref == "results/task-2/result.v1alpha1.json"
    assert saved["task_id"] == "task-2"
    assert saved["contract_version"] == "v1alpha1"
    assert saved["result"]["decision"] == "BUY"

    loaded = store.load_result_contract(result_ref=result_ref, task_id="task-2")
    assert loaded == saved


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

    state = service.create_portfolio_job(
        task_id="port_1",
        total=2,
        request_id="req-1",
        executor_type="analysis_executor",
    )
    assert state["total"] == 2
    assert processes["port_1"] is None
    assert state["request_id"] == "req-1"
    assert state["executor_type"] == "analysis_executor"
    assert state["contract_version"] == "v1alpha1"
    assert state["result_ref"] is None
    assert state["compat"] == {}

    attached = service.attach_result_contract(
        "port_1",
        result_ref="results/port_1/result.v1alpha1.json",
    )
    assert attached["result_ref"] == "results/port_1/result.v1alpha1.json"

    failed = service.fail_job("port_1", "boom")
    assert failed["status"] == "failed"
    assert persisted["port_1"]["error"] == "boom"


def test_job_service_restores_legacy_tasks_with_contract_metadata():
    service = JobService(
        task_results={},
        analysis_tasks={},
        processes={},
        persist_task=lambda task_id, data: None,
        delete_task=lambda task_id: None,
    )

    service.restore_task_results({"legacy-task": {"task_id": "legacy-task", "status": "running"}})

    restored = service.task_results["legacy-task"]
    assert restored["request_id"] == "legacy-task"
    assert restored["executor_type"] == "legacy_subprocess"
    assert restored["contract_version"] == "v1alpha1"
    assert restored["result_ref"] is None
    assert restored["compat"] == {}


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
    assert rec["contract_version"] == "v1alpha1"
    assert rec["result"]["decision"] == "OVERWEIGHT"
    assert rec["result"]["signals"]["quant"]["rating"] == "BUY"
    assert rec["result"]["signals"]["llm"]["rating"] == "HOLD"
    assert rec["compat"]["confidence"] == 0.75


class FakeExecutor:
    async def execute(self, *, task_id, ticker, date, request_context, on_stage=None):
        if on_stage is not None:
            await on_stage("analysts")
            await on_stage("research")
            await on_stage("trading")
            await on_stage("risk")
            await on_stage("portfolio")
        return AnalysisExecutionOutput(
            decision="BUY",
            quant_signal="OVERWEIGHT",
            llm_signal="BUY",
            confidence=0.82,
            report_path=f"results/{ticker}/{date}/complete_report.md",
        )


def test_analysis_service_start_analysis_uses_executor(tmp_path):
    gateway = DummyPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)
    task_results = {}
    analysis_tasks = {}
    processes = {}
    service = JobService(
        task_results=task_results,
        analysis_tasks=analysis_tasks,
        processes=processes,
        persist_task=store.save_task_status,
        delete_task=store.delete_task_status,
    )
    analysis_service = AnalysisService(
        executor=FakeExecutor(),
        result_store=store,
        job_service=service,
    )
    broadcasts = []

    async def _broadcast(task_id, payload):
        broadcasts.append((task_id, payload["status"], payload.get("current_stage")))

    async def scenario():
        response = await analysis_service.start_analysis(
            task_id="task-1",
            ticker="AAPL",
            date="2026-04-13",
            request_context=build_request_context(api_key="secret"),
            broadcast_progress=_broadcast,
        )
        await analysis_tasks["task-1"]
        return response

    response = asyncio.run(scenario())

    assert response == {
        "contract_version": "v1alpha1",
        "task_id": "task-1",
        "ticker": "AAPL",
        "date": "2026-04-13",
        "status": "running",
    }
    assert task_results["task-1"]["status"] == "completed"
    assert task_results["task-1"]["compat"]["decision"] == "BUY"
    assert task_results["task-1"]["result_ref"] == "results/task-1/result.v1alpha1.json"
    assert task_results["task-1"]["result"]["signals"]["llm"]["rating"] == "BUY"
    public_payload = service.to_public_task_payload("task-1", contract=store.load_result_contract(task_id="task-1"))
    assert public_payload["result_ref"] == "results/task-1/result.v1alpha1.json"
    assert public_payload["compat"]["decision"] == "BUY"
    saved_contract = json.loads((tmp_path / "task_status" / "results" / "task-1" / "result.v1alpha1.json").read_text())
    assert saved_contract["status"] == "completed"
    assert saved_contract["result"]["signals"]["merged"]["rating"] == "BUY"
    assert broadcasts[0] == ("task-1", "running", "analysts")
    assert broadcasts[-1][1] == "completed"
