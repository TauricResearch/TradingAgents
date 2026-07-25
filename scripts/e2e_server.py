"""H1 - Localhost server for Playwright e2e with a deterministic fake runner.

Started by ``frontend/playwright.config.ts`` webServer. Composes the real
FastAPI app + SingleRunManager + RunStore with a fake runner that emits a
deterministic 13-role event sequence, so the browser exercises the real
SPA + SSE + artifact pipeline without a live LLM or data vendor.
"""

from __future__ import annotations

import os
from typing import Any

from tradingagents.execution.models import (
    AnalysisCancelled,
    AnalysisRequest,
    AnalysisResult,
    CancellationToken,
)
from tradingagents.observability.observer import DurableRunObserver
from tradingagents.web.api import create_app
from tradingagents.web.broker import EventBroker
from tradingagents.web.manager import SingleRunManager
from tradingagents.web.store import RunStore

# Deterministic 13-role script: (actor_id, response_text, business_delta).
_SCRIPT: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("analyst.market", "市场行情偏强，成交量放大", {"market_report": "市场行情偏强，成交量放大"}),
    ("analyst.sentiment", "社区情绪中性偏多", {"sentiment_report": "社区情绪中性偏多"}),
    ("analyst.news", "公司新闻覆盖充分", {"news_report": "公司新闻覆盖充分"}),
    ("analyst.fundamentals", "基本面稳健，现金流充足", {"fundamentals_report": "基本面稳健，现金流充足"}),
    ("evidence.steward", "证据门已通过", {"evidence_status": "sufficient", "evidence_report": "证据门已通过"}),
    ("researcher.bull", "多方：品牌护城河支撑估值", {"investment_debate_state": {"current_response": "多方：品牌护城河支撑估值", "count": 1}}),
    ("researcher.bear", "空方：估值安全边际不足", {"investment_debate_state": {"current_response": "空方：估值安全边际不足", "count": 1}}),
    ("manager.research", "研究经理裁决：多方占优", {"investment_debate_state": {"judge_decision": "研究经理裁决：多方占优"}}),
    ("trader", "交易员计划：分批建仓", {"trader_investment_plan": "交易员计划：分批建仓"}),
    ("risk.aggressive", "激进观点：可加仓", {"risk_debate_state": {"current_aggressive_response": "激进观点：可加仓"}}),
    ("risk.neutral", "中性观点：维持仓位", {"risk_debate_state": {"current_neutral_response": "中性观点：维持仓位"}}),
    ("risk.conservative", "保守观点：减仓对冲", {"risk_debate_state": {"current_conservative_response": "保守观点：减仓对冲"}}),
    ("manager.portfolio", "组合经理最终决策：HOLD", {"final_trade_decision": "HOLD", "risk_debate_state": {"judge_decision": "组合经理最终决策：HOLD"}}),
)


class _FakeRunner:
    """Deterministic ManagedRunner that emits the 13-role script via observer."""

    def __init__(self, request: AnalysisRequest, observer: DurableRunObserver) -> None:
        self._request = request
        self._observer = observer

    def run(
        self,
        request: AnalysisRequest,
        *,
        cancellation_token: CancellationToken,
        observation_context: Any,
        callbacks: list[Any],
        checkpoint_run_id: str,
        checkpoint_guard: Any,
    ) -> AnalysisResult:
        import time

        observer = self._observer
        graph_step = 1
        for index, (actor_id, _text, business_delta) in enumerate(_SCRIPT):
            if cancellation_token.is_cancelled:
                raise AnalysisCancelled(partial_state={})
            ref = observer.start_turn(
                actor_id=actor_id,
                graph_task_id=f"gt-{actor_id}-{index}",
                graph_step=graph_step,
                turn_index=1,
            )
            graph_step += 1
            artifact = observer.store_artifact("data", business_delta)
            observer.mark_turn_output_ready(ref.turn_id, artifact=artifact)
            observer.complete_turn(ref.turn_id, duration_ms=10, reason="fake_complete")
            # Pace the event stream so live SSE delivery is observable and
            # cancellation tests have a window to click cancel mid-run.
            time.sleep(_PACE_SECONDS)
        return AnalysisResult(
            final_state={"final_trade_decision": "HOLD"},
            final_signal="HOLD",
        )


def _fake_runner_factory(request: AnalysisRequest, observer: DurableRunObserver) -> _FakeRunner:
    return _FakeRunner(request, observer)


# Per-turn pause (seconds). Default 50ms keeps the suite fast; raise via
# E2E_TURN_PACE_MS so cancellation tests have a window to click cancel mid-run.
_PACE_SECONDS = float(os.environ.get("E2E_TURN_PACE_MS", "50")) / 1000.0


def build_app() -> Any:
    root = os.environ.get("TRADINGAGENTS_E2E_RUN_ROOT", "/tmp/tradingagents-e2e-runs")
    store = RunStore(root=root)
    broker = EventBroker(store)
    manager = SingleRunManager(store, broker=broker, runner_factory=_fake_runner_factory)
    environment = {"DEEPSEEK_API_KEY": "fake-deepseek-e2e-key"}
    app = create_app(
        store=store,
        broker=broker,
        manager=manager,
        checkpoint_available=False,
        environment=environment,
    )
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(build_app(), host="127.0.0.1", port=8771)