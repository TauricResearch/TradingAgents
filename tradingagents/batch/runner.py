from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, RemoveMessage
from langchain_core.messages.utils import convert_to_messages
from langgraph.prebuilt import ToolNode

from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    create_msg_delete,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_insider_transactions,
    get_news,
    get_stock_data,
    resolve_instrument_identity,
)
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.batch.adapters import adapter_for_provider, write_jsonl
from tradingagents.batch.deferred import (
    BatchRequestDeferred,
    BatchRuntimeContext,
    DeferredBatchChatModel,
)
from tradingagents.batch.manifest import (
    BatchManifest,
    BatchRunState,
    ProviderBatch,
    batch_root,
)
from tradingagents.dataflows.config import set_config
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.signal_processing import SignalProcessor


class BatchRunner:
    """Pause/resume executor for provider batch APIs.

    This runner intentionally keeps the normal synchronous graph untouched.
    It reuses the same agent factory functions and tool nodes, but drives the
    workflow with explicit phases so an LLM call can be recorded, submitted as
    a provider batch request, and replayed later from the manifest.
    """

    def __init__(
        self,
        *,
        manifest: BatchManifest,
        root: Path | None = None,
        adapter=None,
    ):
        self.manifest = manifest
        self.root = root or batch_root(manifest.config)
        self.adapter = adapter or adapter_for_provider(manifest.provider, manifest.config)
        self.context = BatchRuntimeContext(
            manifest=manifest,
            adapter=self.adapter,
            batch_root=self.root,
        )
        self.provider = manifest.provider
        self.quick_llm = DeferredBatchChatModel(
            provider=self.provider,
            model_name=manifest.config["quick_think_llm"],
            context=self.context,
        )
        self.deep_llm = DeferredBatchChatModel(
            provider=self.provider,
            model_name=manifest.config["deep_think_llm"],
            context=self.context,
        )
        set_config(manifest.config)
        self.memory_log = TradingMemoryLog(manifest.config)
        self.signal_processor = SignalProcessor()
        self.propagator = Propagator(
            max_recur_limit=manifest.config.get("max_recur_limit", 100)
        )
        self.nodes = self._build_nodes()
        self.tool_nodes = self._build_tool_nodes()
        self.clear_node = create_msg_delete()

    @classmethod
    def create(
        cls,
        *,
        provider: str,
        tickers: list[str],
        trade_date: str,
        asset_types: dict[str, str],
        selected_analysts: list[str],
        config: dict[str, Any],
        root: Path | None = None,
    ) -> BatchRunner:
        provider_key = provider.lower()
        if provider_key not in {"openai", "anthropic"}:
            raise ValueError("batch mode supports only provider='openai' or provider='anthropic'")
        config = dict(config)
        config["llm_provider"] = provider_key
        runs: dict[str, BatchRunState] = {}
        memory_log = TradingMemoryLog(config)
        propagator = Propagator(max_recur_limit=config.get("max_recur_limit", 100))
        for ticker in tickers:
            asset_type = asset_types.get(ticker, "stock")
            instrument_context = build_instrument_context(
                ticker,
                asset_type,
                resolve_instrument_identity(ticker),
            )
            state = propagator.create_initial_state(
                ticker,
                trade_date,
                asset_type=asset_type,
                past_context=memory_log.get_past_context(ticker),
                instrument_context=instrument_context,
            )
            runs[ticker] = BatchRunState.create(
                ticker=ticker,
                trade_date=trade_date,
                asset_type=asset_type,
                state=state,
            )
        manifest = BatchManifest.new(
            provider=provider_key,
            selected_analysts=selected_analysts,
            config=config,
            runs=runs,
        )
        return cls(manifest=manifest, root=root)

    @classmethod
    def load(cls, *, config: dict[str, Any], run_id: str) -> BatchRunner:
        root = batch_root(config)
        manifest = BatchManifest.load(root, run_id)
        return cls(manifest=manifest, root=root)

    def save(self) -> Path:
        return self.manifest.save(self.root)

    def submit(self) -> Path:
        self.advance_all()
        self.submit_pending()
        return self.save()

    def collect(self) -> Path:
        self.download_completed_results()
        self.advance_all()
        self.submit_pending()
        return self.save()

    def wait(self, poll_seconds: float = 60.0, max_wait_seconds: float | None = None) -> None:
        started = time.monotonic()
        self.submit()
        while self.manifest.status != "completed":
            if max_wait_seconds is not None and time.monotonic() - started > max_wait_seconds:
                raise TimeoutError("batch wait timed out before all ticker runs completed")
            time.sleep(poll_seconds)
            self.collect()

    def status_summary(self) -> dict[str, Any]:
        request_counts: dict[str, int] = {}
        for request in self.manifest.requests.values():
            request_counts[request.status] = request_counts.get(request.status, 0) + 1
        run_counts: dict[str, int] = {}
        for run in self.manifest.runs.values():
            run_counts[run.status] = run_counts.get(run.status, 0) + 1
        return {
            "run_id": self.manifest.run_id,
            "provider": self.manifest.provider,
            "status": self.manifest.status,
            "runs": run_counts,
            "requests": request_counts,
            "provider_batches": [
                {
                    "provider": batch.provider,
                    "model": batch.model,
                    "batch_id": batch.batch_id,
                    "status": batch.status,
                    "requests": len(batch.request_ids),
                }
                for batch in self.manifest.provider_batches
            ],
        }

    def _build_nodes(self) -> dict[str, Any]:
        return {
            "Market Analyst": create_market_analyst(self.quick_llm),
            "Sentiment Analyst": create_sentiment_analyst(self.quick_llm),
            "News Analyst": create_news_analyst(self.quick_llm),
            "Fundamentals Analyst": create_fundamentals_analyst(self.quick_llm),
            "Bull Researcher": create_bull_researcher(self.quick_llm),
            "Bear Researcher": create_bear_researcher(self.quick_llm),
            "Research Manager": create_research_manager(self.deep_llm),
            "Trader": create_trader(self.quick_llm),
            "Aggressive Analyst": create_aggressive_debator(self.quick_llm),
            "Conservative Analyst": create_conservative_debator(self.quick_llm),
            "Neutral Analyst": create_neutral_debator(self.quick_llm),
            "Portfolio Manager": create_portfolio_manager(self.deep_llm),
        }

    def _build_tool_nodes(self) -> dict[str, ToolNode]:
        return {
            "market": ToolNode([get_stock_data, get_indicators]),
            "social": ToolNode([get_news]),
            "news": ToolNode([get_news, get_global_news, get_insider_transactions]),
            "fundamentals": ToolNode(
                [get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement]
            ),
        }

    def advance_all(self) -> None:
        for run in self.manifest.runs.values():
            if run.status == "completed":
                continue
            try:
                self._advance_run(run)
            except BatchRequestDeferred:
                continue
            except Exception as exc:  # noqa: BLE001 - manifest should preserve failure
                run.status = "failed"
                run.error = str(exc)
        if all(run.status == "completed" for run in self.manifest.runs.values()):
            self.manifest.status = "completed"
        elif any(run.status == "failed" for run in self.manifest.runs.values()):
            self.manifest.status = "failed"
        else:
            self.manifest.status = "running"

    def _advance_run(self, run: BatchRunState) -> None:
        state = run.decoded_state()
        self._ensure_message_ids(state)
        max_steps = self.manifest.config.get("max_recur_limit", 100)
        for _ in range(max_steps):
            if run.status == "completed":
                return
            progress = run.progress
            if progress.get("active_node"):
                active_node = progress["active_node"]
                self._execute_llm_node(run, state, active_node)
                self._after_active_node(run, state, active_node)
                continue

            phase = progress.get("phase")
            if phase == "analyst":
                if self._advance_analyst(run, state):
                    continue
                progress["phase"] = "debate"
                continue
            if phase == "debate":
                if state["investment_debate_state"]["count"] < 2 * self.manifest.config["max_debate_rounds"]:
                    current = state["investment_debate_state"].get("current_response", "")
                    node = "Bear Researcher" if current.startswith("Bull") else "Bull Researcher"
                    self._execute_llm_node(run, state, node)
                    continue
                progress["phase"] = "research_manager"
                continue
            if phase == "research_manager":
                self._execute_llm_node(run, state, "Research Manager")
                progress["phase"] = "trader"
                continue
            if phase == "trader":
                self._execute_llm_node(run, state, "Trader")
                progress["phase"] = "risk"
                continue
            if phase == "risk":
                if state["risk_debate_state"]["count"] < 3 * self.manifest.config["max_risk_discuss_rounds"]:
                    latest = state["risk_debate_state"].get("latest_speaker", "")
                    if latest.startswith("Aggressive"):
                        node = "Conservative Analyst"
                    elif latest.startswith("Conservative"):
                        node = "Neutral Analyst"
                    else:
                        node = "Aggressive Analyst"
                    self._execute_llm_node(run, state, node)
                    continue
                progress["phase"] = "portfolio_manager"
                continue
            if phase == "portfolio_manager":
                self._execute_llm_node(run, state, "Portfolio Manager")
                progress["phase"] = "complete"
                continue
            if phase == "complete":
                run.final_signal = self.signal_processor.process_signal(
                    state["final_trade_decision"]
                )
                self.memory_log.store_decision(
                    ticker=run.ticker,
                    trade_date=run.trade_date,
                    final_trade_decision=state["final_trade_decision"],
                )
                run.set_state(state)
                run.status = "completed"
                return
        raise RuntimeError(f"batch runner exceeded recursion limit for {run.ticker}")

    def _after_active_node(
        self,
        run: BatchRunState,
        state: dict[str, Any],
        node_name: str,
    ) -> None:
        phase = run.progress.get("phase")
        if phase == "analyst":
            self._finish_analyst_step(run, state)
        elif phase == "research_manager" and node_name == "Research Manager":
            run.progress["phase"] = "trader"
        elif phase == "trader" and node_name == "Trader":
            run.progress["phase"] = "risk"
        elif phase == "portfolio_manager" and node_name == "Portfolio Manager":
            run.progress["phase"] = "complete"
        run.set_state(state)

    def _advance_analyst(self, run: BatchRunState, state: dict[str, Any]) -> bool:
        index = int(run.progress.get("analyst_index", 0))
        if index >= len(self.manifest.selected_analysts):
            return False
        spec = ANALYST_NODE_SPECS[self.manifest.selected_analysts[index]]
        self._execute_llm_node(run, state, spec.agent_node)
        self._finish_analyst_step(run, state)
        return True

    def _finish_analyst_step(self, run: BatchRunState, state: dict[str, Any]) -> None:
        index = int(run.progress.get("analyst_index", 0))
        spec = ANALYST_NODE_SPECS[self.manifest.selected_analysts[index]]
        if not state.get(spec.report_key):
            update = self.tool_nodes[spec.key].invoke(state)
            self._apply_update(state, update)
            run.set_state(state)
            return
        self._apply_update(state, self.clear_node(state))
        run.progress["analyst_index"] = index + 1
        run.set_state(state)

    def _execute_llm_node(
        self,
        run: BatchRunState,
        state: dict[str, Any],
        node_name: str,
    ) -> None:
        self.context.begin_node(run, node_name)
        try:
            update = self.nodes[node_name](state)
        except BatchRequestDeferred:
            run.set_state(state)
            raise
        else:
            self.context.end_node()
            self._apply_update(state, update)
            run.set_state(state)

    def _apply_update(self, state: dict[str, Any], update: dict[str, Any] | None) -> None:
        if not update:
            return
        for key, value in update.items():
            if key == "messages":
                state["messages"] = self._merge_messages(state.get("messages", []), value)
            else:
                state[key] = value
        self._ensure_message_ids(state)

    def _merge_messages(self, current: Any, incoming: Any) -> list[BaseMessage]:
        messages = convert_to_messages(current)
        additions = convert_to_messages(incoming)
        by_id = {message.id: i for i, message in enumerate(messages) if message.id}
        for message in additions:
            if isinstance(message, RemoveMessage):
                if message.id in by_id:
                    index = by_id.pop(message.id)
                    messages.pop(index)
                    by_id = {m.id: i for i, m in enumerate(messages) if m.id}
                continue
            messages.append(message)
        return messages

    def _ensure_message_ids(self, state: dict[str, Any]) -> None:
        messages = convert_to_messages(state.get("messages", []))
        for message in messages:
            if not getattr(message, "id", None):
                message.id = f"batch-{uuid.uuid4().hex}"
        state["messages"] = messages

    def submit_pending(self) -> None:
        pending = self.manifest.pending_requests
        if not pending:
            return
        run_dir = self.root / self.manifest.run_id
        grouped: dict[tuple[str, str], list[Any]] = {}
        for request in pending:
            grouped.setdefault((request.provider, request.model), []).append(request)
        for (provider, model), requests in grouped.items():
            lines = [request.payload for request in requests]
            input_path = run_dir / "inputs" / f"{provider}_{model}_{len(self.manifest.provider_batches)}.jsonl"
            write_jsonl(input_path, lines)
            batch_id = self.adapter.submit_batch(
                model=model,
                lines=lines,
                input_path=input_path,
            )
            provider_batch = ProviderBatch(
                provider=provider,
                model=model,
                endpoint=self.adapter.endpoint,
                batch_id=batch_id,
                status="submitted",
                request_ids=[request.custom_id for request in requests],
                input_path=str(input_path),
            )
            self.manifest.provider_batches.append(provider_batch)
            for request in requests:
                request.status = "submitted"
                request.provider_batch_id = batch_id

    def download_completed_results(self) -> None:
        run_dir = self.root / self.manifest.run_id
        for provider_batch in self.manifest.provider_batches:
            if provider_batch.status in {"collected", "failed"}:
                continue
            if not provider_batch.batch_id:
                continue
            status = self.adapter.refresh_batch(provider_batch.batch_id)
            provider_status = (
                status.get("status")
                or status.get("processing_status")
                or provider_batch.status
            )
            provider_batch.status = str(provider_status)
            complete = provider_status in {"completed", "ended"}
            terminal_failure = provider_status in {"failed", "expired", "cancelled", "canceled"}
            if not complete and not terminal_failure:
                continue
            output_path = run_dir / "outputs" / f"{provider_batch.batch_id}.jsonl"
            error_path = run_dir / "outputs" / f"{provider_batch.batch_id}.errors.jsonl"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            results = self.adapter.download_results(
                batch_id=provider_batch.batch_id,
                output_path=output_path,
                error_path=error_path,
            )
            provider_batch.output_path = str(output_path)
            provider_batch.error_path = str(error_path)
            provider_batch.status = "collected" if complete else "failed"
            self._apply_results(results)

    def _apply_results(self, results: dict[str, dict[str, Any]]) -> None:
        for custom_id, result in results.items():
            request = self.manifest.requests.get(custom_id)
            if request is None:
                continue
            if self.manifest.provider == "openai":
                error = result.get("error")
                response = result.get("response")
                if error or not response or int(response.get("status_code", 0)) >= 400:
                    request.status = "errored"
                    request.error = error or response
                    continue
                request.status = "succeeded"
                request.response = response["body"]
            else:
                body = result.get("result", result)
                result_type = body.get("type")
                if result_type == "succeeded":
                    request.status = "succeeded"
                    request.response = body.get("message") or body.get("response")
                else:
                    request.status = result_type or "errored"
                    request.error = body

    def retry_failed(self) -> None:
        for request in self.manifest.requests.values():
            if request.status in {"errored", "expired", "canceled", "cancelled"}:
                request.status = "pending"
                request.provider_batch_id = None
                request.error = None
        self.submit_pending()

    def completed_states(self) -> dict[str, dict[str, Any]]:
        return {
            ticker: run.decoded_state()
            for ticker, run in self.manifest.runs.items()
            if run.status == "completed"
        }

    def estimated_token_usage(self) -> dict[str, int]:
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for request in self.manifest.requests.values():
            if request.status != "succeeded" or request.response is None:
                continue
            message = self.adapter.message_from_response(request.response)
            usage = message.usage_metadata or {}
            totals["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
            totals["output_tokens"] += int(usage.get("output_tokens", 0) or 0)
            totals["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
        return totals


def summary_json(runner: BatchRunner) -> str:
    return json.dumps(runner.status_summary(), indent=2, sort_keys=True)
