import json
import asyncio
from pathlib import Path

from services.analysis_service import AnalysisService
from services.executor import AnalysisExecutionOutput, AnalysisExecutorError
from services.job_service import JobService
from services.migration_flags import load_migration_flags
from services.request_context import build_request_context
from services.result_store import ResultStore
from services.task_command_service import TaskCommandService
from services.task_query_service import TaskQueryService


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
    context = build_request_context(
        auth_key="dashboard-secret",
        provider_api_key="provider-secret",
        llm_provider="anthropic",
        backend_url="https://api.minimaxi.com/anthropic",
        deep_think_llm="MiniMax-M2.7-highspeed",
        quick_think_llm="MiniMax-M2.7-highspeed",
        selected_analysts=["market"],
        analysis_prompt_style="compact",
        llm_timeout=45,
        llm_max_retries=0,
        metadata={"source": "test"},
    )

    assert context.auth_key == "dashboard-secret"
    assert context.provider_api_key == "provider-secret"
    assert context.llm_provider == "anthropic"
    assert context.backend_url == "https://api.minimaxi.com/anthropic"
    assert context.selected_analysts == ("market",)
    assert context.analysis_prompt_style == "compact"
    assert context.llm_timeout == 45
    assert context.llm_max_retries == 0
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
            'SIGNAL_DETAIL:{"quant_signal":"BUY","llm_signal":"HOLD","confidence":0.75,"llm_decision_structured":{"rating":"HOLD","hold_subtype":"DEFENSIVE_HOLD"}}',
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
    assert rec["result"]["signals"]["llm"]["structured"]["hold_subtype"] == "DEFENSIVE_HOLD"
    assert rec["compat"]["confidence"] == 0.75
    assert rec["compat"]["llm_decision_structured"]["rating"] == "HOLD"


class RichPortfolioGateway(DummyPortfolioGateway):
    async def get_positions(self, account=None):
        return [
            {
                "ticker": "AAPL",
                "account": account or "默认账户",
                "shares": 10,
                "cost_price": 100.0,
                "current_price": 110.0,
                "unrealized_pnl_pct": 10.0,
            },
            {
                "ticker": "TSLA",
                "account": account or "默认账户",
                "shares": 5,
                "cost_price": 200.0,
                "current_price": 170.0,
                "unrealized_pnl_pct": -15.0,
            },
        ]

    def get_watchlist(self):
        return [
            {"ticker": "AAPL", "name": "Apple"},
            {"ticker": "TSLA", "name": "Tesla"},
            {"ticker": "MSFT", "name": "Microsoft"},
        ]

    def get_recommendations(self, date=None, limit=50, offset=0):
        return {
            "recommendations": [
                {
                    "ticker": "MSFT",
                    "result": {"decision": "BUY", "confidence": 0.8},
                },
                {
                    "ticker": "TSLA",
                    "result": {"decision": "SELL", "confidence": 0.9},
                },
            ],
            "total": 2,
            "limit": limit,
            "offset": offset,
        }


def test_analysis_service_enriches_missing_decision_context(tmp_path):
    gateway = RichPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)
    service = AnalysisService(
        executor=FakeExecutor(),
        result_store=store,
        job_service=JobService(
            task_results={},
            analysis_tasks={},
            processes={},
            persist_task=lambda task_id, data: None,
            delete_task=lambda task_id: None,
        ),
    )
    context = build_request_context(metadata={})

    enriched = asyncio.run(
        service._enrich_request_context(
            context,
            ticker="AAPL",
            date="2026-04-13",
        )
    )

    assert "Current portfolio has 2 open position(s)." in enriched.metadata["portfolio_context"]
    assert "Existing position in target: AAPL" in enriched.metadata["portfolio_context"]
    assert "MSFT:BUY" in enriched.metadata["peer_context"]
    assert "TSLA:SELL" in enriched.metadata["peer_context"]
    assert enriched.metadata["peer_context_mode"] == "PORTFOLIO_SNAPSHOT"


def test_analysis_service_preserves_explicit_decision_context(tmp_path):
    gateway = RichPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)
    service = AnalysisService(
        executor=FakeExecutor(),
        result_store=store,
        job_service=JobService(
            task_results={},
            analysis_tasks={},
            processes={},
            persist_task=lambda task_id, data: None,
            delete_task=lambda task_id: None,
        ),
    )
    context = build_request_context(
        metadata={
            "portfolio_context": "manual portfolio context",
            "peer_context": "manual peer context",
        }
    )

    enriched = asyncio.run(
        service._enrich_request_context(
            context,
            ticker="AAPL",
            date="2026-04-13",
        )
    )

    assert enriched.metadata["portfolio_context"] == "manual portfolio context"
    assert enriched.metadata["peer_context"] == "manual peer context"
    assert enriched.metadata["peer_context_mode"] == "CALLER_PROVIDED"


def test_freeze_batch_peer_snapshot_uses_stable_recommendation_source(tmp_path):
    gateway = RichPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)
    service = AnalysisService(
        executor=FakeExecutor(),
        result_store=store,
        job_service=JobService(
            task_results={},
            analysis_tasks={},
            processes={},
            persist_task=lambda task_id, data: None,
            delete_task=lambda task_id: None,
        ),
    )
    context = build_request_context(metadata={})

    frozen = service._freeze_batch_peer_snapshot(
        context,
        date="2026-04-13",
        watchlist=gateway.get_watchlist(),
    )

    assert len(frozen.metadata["peer_recommendation_snapshot"]) == 2
    assert frozen.metadata["peer_context_mode"] == "PORTFOLIO_SNAPSHOT"
    assert [item["ticker"] for item in frozen.metadata["peer_context_batch_watchlist"]] == ["AAPL", "TSLA", "MSFT"]


def test_build_peer_context_prefers_frozen_snapshot_over_live_store(tmp_path):
    gateway = RichPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)
    service = AnalysisService(
        executor=FakeExecutor(),
        result_store=store,
        job_service=JobService(
            task_results={},
            analysis_tasks={},
            processes={},
            persist_task=lambda task_id, data: None,
            delete_task=lambda task_id: None,
        ),
    )

    context = service._build_peer_context(
        ticker="AAPL",
        date="2026-04-13",
        peer_snapshot=[
            {"ticker": "AAA", "result": {"decision": "BUY", "confidence": 0.7}},
            {"ticker": "BBB", "result": {"decision": "SELL", "confidence": 0.6}},
        ],
        watchlist_snapshot=[{"ticker": "AAPL"}, {"ticker": "AAA"}, {"ticker": "BBB"}],
    )

    assert "AAA:BUY" in context
    assert "BBB:SELL" in context
    assert "industry-normalized" in context


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
            observation={
                "status": "completed",
                "observation_code": "completed",
                "attempt_mode": request_context.metadata.get("attempt_mode", "baseline"),
                "evidence_id": "fake-success",
            },
        )


class RecoveryThenSuccessExecutor:
    def __init__(self):
        self.attempt_modes = []

    async def execute(self, *, task_id, ticker, date, request_context, on_stage=None):
        mode = request_context.metadata.get("attempt_mode", "baseline")
        self.attempt_modes.append(mode)
        if on_stage is not None:
            await on_stage("analysts")
        if mode == "baseline":
            raise AnalysisExecutorError(
                "analysis subprocess failed without required markers: RESULT_META",
                code="analysis_protocol_failed",
                observation={
                    "status": "failed",
                    "observation_code": "analysis_protocol_failed",
                    "attempt_mode": mode,
                    "evidence_id": "baseline",
                    "message": "analysis subprocess failed without required markers: RESULT_META",
                },
            )
        return AnalysisExecutionOutput(
            decision="BUY",
            quant_signal="OVERWEIGHT",
            llm_signal="BUY",
            confidence=0.82,
            report_path=f"results/{ticker}/{date}/complete_report.md",
            observation={
                "status": "completed",
                "observation_code": "completed",
                "attempt_mode": mode,
                "evidence_id": f"{mode}-success",
            },
        )


class RecoveryThenProbeExecutor:
    def __init__(self):
        self.attempt_modes = []
        self.selected_analysts = []

    async def execute(self, *, task_id, ticker, date, request_context, on_stage=None):
        mode = request_context.metadata.get("attempt_mode", "baseline")
        self.attempt_modes.append(mode)
        self.selected_analysts.append(tuple(request_context.selected_analysts))
        if on_stage is not None:
            await on_stage("analysts")
        if mode == "provider_probe":
            return AnalysisExecutionOutput(
                decision="HOLD",
                quant_signal="HOLD",
                llm_signal="HOLD",
                confidence=0.5,
                report_path=f"results/{ticker}/{date}/complete_report.md",
                observation={
                    "status": "completed",
                    "observation_code": "completed",
                    "attempt_mode": mode,
                    "evidence_id": "provider-probe-success",
                },
            )
        raise AnalysisExecutorError(
            "analysis subprocess timed out after 300s",
            code="analysis_failed",
            retryable=True,
            observation={
                "status": "failed",
                "observation_code": "subprocess_stdout_timeout",
                "attempt_mode": mode,
                "evidence_id": f"{mode}-failure",
                "message": "analysis subprocess timed out after 300s",
            },
        )


class AlwaysFailRuntimePolicyExecutor:
    def __init__(self):
        self.attempt_modes = []

    async def execute(self, *, task_id, ticker, date, request_context, on_stage=None):
        mode = request_context.metadata.get("attempt_mode", "baseline")
        self.attempt_modes.append(mode)
        raise AnalysisExecutorError(
            f"{mode} failed",
            code="analysis_failed",
            retryable=(mode != "provider_probe"),
            observation={
                "status": "failed",
                "observation_code": "subprocess_stdout_timeout",
                "attempt_mode": mode,
                "evidence_id": f"{mode}-failure",
                "message": f"{mode} failed",
            },
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
            request_context=build_request_context(
                auth_key="dashboard-secret",
                provider_api_key="provider-secret",
                llm_provider="anthropic",
                backend_url="https://api.minimaxi.com/anthropic",
                selected_analysts=["market"],
                analysis_prompt_style="compact",
                llm_timeout=45,
                llm_max_retries=0,
            ),
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
    assert task_results["task-1"]["tentative_classification"]["kind"] == "no_issue"
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


def test_classify_attempts_marks_baseline_success_as_no_issue():
    analysis_service = AnalysisService(
        executor=None,
        result_store=None,
        job_service=None,
    )

    classification = analysis_service._classify_attempts([
        {
            "status": "completed",
            "observation_code": "completed",
            "attempt_mode": "baseline",
        }
    ])

    assert classification["kind"] == "no_issue"


def test_analysis_service_promotes_local_recovery_before_success(tmp_path):
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
    executor = RecoveryThenSuccessExecutor()
    analysis_service = AnalysisService(
        executor=executor,
        result_store=store,
        job_service=service,
    )
    broadcasts = []

    async def _broadcast(task_id, payload):
        broadcasts.append((task_id, payload["status"], payload.get("tentative_classification")))

    async def scenario():
        response = await analysis_service.start_analysis(
            task_id="task-recovery",
            ticker="AAPL",
            date="2026-04-13",
            request_context=build_request_context(
                provider_api_key="provider-secret",
                llm_provider="anthropic",
                backend_url="https://api.minimaxi.com/anthropic",
                selected_analysts=["market", "news"],
            ),
            broadcast_progress=_broadcast,
        )
        await analysis_tasks["task-recovery"]
        return response

    response = asyncio.run(scenario())

    assert response["status"] == "running"
    assert executor.attempt_modes == ["baseline", "local_recovery"]
    assert task_results["task-recovery"]["status"] == "completed"
    assert task_results["task-recovery"]["tentative_classification"]["kind"] == "local_runtime"
    assert task_results["task-recovery"]["budget_state"]["local_recovery_used"] is True
    assert any(status == "auto_recovering" for _, status, _ in broadcasts)


def test_analysis_service_uses_single_provider_probe_after_recovery_failure(tmp_path):
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
    executor = RecoveryThenProbeExecutor()
    analysis_service = AnalysisService(
        executor=executor,
        result_store=store,
        job_service=service,
    )
    broadcasts = []

    async def _broadcast(task_id, payload):
        broadcasts.append(payload["status"])

    async def scenario():
        response = await analysis_service.start_analysis(
            task_id="task-probe",
            ticker="AAPL",
            date="2026-04-13",
            request_context=build_request_context(
                provider_api_key="provider-secret",
                llm_provider="anthropic",
                backend_url="https://api.minimaxi.com/anthropic",
                selected_analysts=["news", "fundamentals"],
            ),
            broadcast_progress=_broadcast,
        )
        await analysis_tasks["task-probe"]
        return response

    response = asyncio.run(scenario())

    assert response["status"] == "running"
    assert executor.attempt_modes == ["baseline", "local_recovery", "provider_probe"]
    assert executor.selected_analysts[-1] == ("news",)
    assert task_results["task-probe"]["status"] == "completed"
    assert task_results["task-probe"]["budget_state"]["provider_probe_used"] is True
    assert "probing_provider" in broadcasts
    assert task_results["task-probe"]["tentative_classification"]["kind"] == "interaction_effect"


def test_portfolio_analysis_uses_runtime_policy_and_persists_failure_evidence(tmp_path):
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
    executor = AlwaysFailRuntimePolicyExecutor()
    analysis_service = AnalysisService(
        executor=executor,
        result_store=store,
        job_service=service,
    )

    async def _broadcast(task_id, payload):
        return None

    async def scenario():
        response = await analysis_service.start_portfolio_analysis(
            task_id="portfolio-runtime-policy",
            date="2026-04-13",
            request_context=build_request_context(
                provider_api_key="provider-secret",
                llm_provider="anthropic",
                backend_url="https://api.minimaxi.com/anthropic",
                selected_analysts=["market", "social"],
            ),
            broadcast_progress=_broadcast,
        )
        await analysis_tasks["portfolio-runtime-policy"]
        return response

    response = asyncio.run(scenario())

    assert response["status"] == "running"
    assert executor.attempt_modes == ["baseline", "local_recovery", "provider_probe"]
    assert task_results["portfolio-runtime-policy"]["status"] == "completed"
    assert task_results["portfolio-runtime-policy"]["failed"] == 1
    assert len(task_results["portfolio-runtime-policy"]["results"]) == 1
    rec = task_results["portfolio-runtime-policy"]["results"][0]
    assert rec["status"] == "failed"
    assert rec["error"]["code"] == "analysis_failed"
    assert rec["tentative_classification"]["kind"] == "interaction_effect"
    assert rec["budget_state"]["provider_probe_used"] is True
    assert rec["evidence"]["attempts"][-1]["attempt_mode"] == "provider_probe"


def test_task_query_service_loads_contract_and_lists_sorted_summaries(tmp_path):
    gateway = DummyPortfolioGateway()
    store = ResultStore(tmp_path / "task_status", gateway)
    task_results = {
        "task-old": {
            "contract_version": "v1alpha1",
            "task_id": "task-old",
            "request_id": "req-old",
            "executor_type": "legacy_subprocess",
            "result_ref": None,
            "ticker": "AAPL",
            "date": "2026-04-10",
            "status": "running",
            "progress": 10,
            "current_stage": "analysts",
            "created_at": "2026-04-10T10:00:00",
            "elapsed_seconds": 1,
            "stages": [],
            "result": None,
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "compat": {},
        },
        "task-new": {
            "contract_version": "v1alpha1",
            "task_id": "task-new",
            "request_id": "req-new",
            "executor_type": "legacy_subprocess",
            "result_ref": "results/task-new/result.v1alpha1.json",
            "ticker": "MSFT",
            "date": "2026-04-11",
            "status": "completed",
            "progress": 100,
            "current_stage": "portfolio",
            "created_at": "2026-04-11T10:00:00",
            "elapsed_seconds": 3,
            "stages": [],
            "result": {"decision": "STALE"},
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "compat": {},
        },
    }
    service = JobService(
        task_results=task_results,
        analysis_tasks={},
        processes={},
        persist_task=lambda task_id, data: None,
        delete_task=lambda task_id: None,
    )
    store.save_result_contract(
        "task-new",
        {
            "status": "completed",
            "ticker": "MSFT",
            "date": "2026-04-11",
            "result": {
                "decision": "BUY",
                "confidence": 0.91,
                "degraded": False,
                "signals": {"merged": {"rating": "BUY"}},
            },
            "error": None,
        },
    )
    query_service = TaskQueryService(
        task_results=task_results,
        result_store=store,
        job_service=service,
    )

    payload = query_service.public_task_payload("task-new")
    listing = query_service.list_task_summaries()

    assert payload["result"]["decision"] == "BUY"
    assert listing["contract_version"] == "v1alpha1"
    assert listing["total"] == 2
    assert [task["task_id"] for task in listing["tasks"]] == ["task-new", "task-old"]


def test_job_service_maps_internal_runtime_statuses_to_running_public_status():
    service = JobService(
        task_results={
            "task-runtime": {
                "contract_version": "v1alpha1",
                "task_id": "task-runtime",
                "request_id": "req-runtime",
                "executor_type": "legacy_subprocess",
                "result_ref": None,
                "ticker": "AAPL",
                "date": "2026-04-13",
                "status": "auto_recovering",
                "progress": 10,
                "current_stage": "analysts",
                "created_at": "2026-04-13T10:00:00",
                "elapsed_seconds": 2,
                "stages": [],
                "result": None,
                "error": None,
                "degradation_summary": None,
                "data_quality_summary": None,
                "evidence_summary": {"attempts": []},
                "tentative_classification": None,
                "budget_state": {},
                "compat": {},
            }
        },
        analysis_tasks={},
        processes={},
        persist_task=lambda task_id, data: None,
        delete_task=lambda task_id: None,
    )

    payload = service.to_public_task_payload("task-runtime")
    summary = service.to_task_summary("task-runtime")

    assert payload["status"] == "running"
    assert summary["status"] == "running"


class _DummyTask:
    def __init__(self, events):
        self.events = events

    def cancel(self):
        self.events.append("background task cancel")


class _DummyProcess:
    def __init__(self, events):
        self.events = events
        self.returncode = None

    def kill(self):
        self.events.append("process kill")


class _RecordingTaskStatusStore:
    def __init__(self, task_status_dir: Path, events: list[str]):
        self.task_status_dir = task_status_dir
        self.events = events

    def save_task_status(self, task_id: str, data: dict) -> None:
        self.events.append("save_task_status")
        self.task_status_dir.mkdir(parents=True, exist_ok=True)
        (self.task_status_dir / f"{task_id}.json").write_text(json.dumps(data, ensure_ascii=False))

    def delete_task_status(self, task_id: str) -> None:
        self.events.append("delete_task_status")
        (self.task_status_dir / f"{task_id}.json").unlink(missing_ok=True)

    def load_result_contract(self, *, result_ref=None, task_id=None):
        return None


def test_task_command_service_preserves_delete_on_cancel_sequence(tmp_path):
    events: list[str] = []
    task_status_dir = tmp_path / "task_status"
    store = _RecordingTaskStatusStore(task_status_dir, events)
    task_results = {
        "task-cancel": {
            "contract_version": "v1alpha1",
            "task_id": "task-cancel",
            "request_id": "req-cancel",
            "executor_type": "legacy_subprocess",
            "result_ref": None,
            "ticker": "AAPL",
            "date": "2026-04-11",
            "status": "running",
            "progress": 20,
            "current_stage": "research",
            "created_at": "2026-04-11T10:00:00",
            "elapsed_seconds": 3,
            "stages": [],
            "result": None,
            "error": None,
            "degradation_summary": None,
            "data_quality_summary": None,
            "compat": {},
        }
    }
    job_service = JobService(
        task_results=task_results,
        analysis_tasks={"task-cancel": _DummyTask(events)},
        processes={"task-cancel": _DummyProcess(events)},
        persist_task=lambda task_id, data: None,
        delete_task=lambda task_id: None,
    )
    original_cancel_job = job_service.cancel_job

    def _wrapped_cancel_job(task_id: str, error: str = "用户取消"):
        events.append("job_service.cancel_job")
        return original_cancel_job(task_id, error)

    job_service.cancel_job = _wrapped_cancel_job

    command_service = TaskCommandService(
        task_results=task_results,
        analysis_tasks=job_service.analysis_tasks,
        processes=job_service.processes,
        result_store=store,
        job_service=job_service,
    )
    broadcasts: list[dict] = []

    async def _broadcast(task_id: str, payload: dict):
        events.append("broadcast_progress")
        broadcasts.append(json.loads(json.dumps(payload)))

    response = asyncio.run(
        command_service.cancel_task("task-cancel", broadcast_progress=_broadcast)
    )

    assert response == {
        "contract_version": "v1alpha1",
        "task_id": "task-cancel",
        "status": "cancelled",
    }
    assert events == [
        "process kill",
        "background task cancel",
        "job_service.cancel_job",
        "save_task_status",
        "broadcast_progress",
        "delete_task_status",
    ]
    assert broadcasts[-1]["status"] == "cancelled"
    assert broadcasts[-1]["error"] == {
        "code": "cancelled",
        "message": "用户取消",
        "retryable": False,
    }
    assert task_results["task-cancel"]["status"] == "cancelled"
    assert task_results["task-cancel"]["error"]["code"] == "cancelled"
    assert not (task_status_dir / "task-cancel.json").exists()
