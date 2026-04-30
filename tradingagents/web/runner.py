"""Background execution and state aggregation for the Streamlit console."""

from __future__ import annotations

import ast
import datetime as dt
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from dotenv import load_dotenv

from cli.stats_handler import StatsCallbackHandler
from tradingagents.graph.checkpointer import clear_checkpoint, get_checkpointer, thread_id
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.web.models import (
    ANALYST_LABELS,
    ANALYST_ORDER,
    AnalysisJob,
    AnalysisMessage,
    AnalysisRequest,
    AnalysisSnapshot,
    JobStatus,
    ToolCallRecord,
)

load_dotenv()
load_dotenv(".env.enterprise", override=False)


FIXED_AGENTS = {
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
    "Portfolio Management": ["Portfolio Manager"],
}

REPORT_SECTIONS = {
    "market_report": ("market", "Market Analyst"),
    "sentiment_report": ("social", "Social Analyst"),
    "news_report": ("news", "News Analyst"),
    "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
    "investment_plan": (None, "Research Manager"),
    "trader_investment_plan": (None, "Trader"),
    "final_trade_decision": (None, "Portfolio Manager"),
}

ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}

API_KEY_ENV_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
}


def _timestamp() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def validate_provider_credentials(request: AnalysisRequest) -> None:
    env_var = API_KEY_ENV_BY_PROVIDER.get(request.llm_provider.lower())
    if not env_var:
        return
    if not os.environ.get(env_var, "").strip():
        raise RuntimeError(
            f"Missing {env_var}. Set it in .env or export it before starting the web console."
        )


def _is_empty(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        try:
            return not bool(ast.literal_eval(stripped))
        except (ValueError, SyntaxError):
            return False
    return not bool(value)


def extract_content_string(content: Any) -> Optional[str]:
    if _is_empty(content):
        return None

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        text = content.get("text", "")
        return text.strip() if not _is_empty(text) else None

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", "").strip())
            elif isinstance(item, str):
                parts.append(item.strip())
        text = " ".join(part for part in parts if part and not _is_empty(part))
        return text or None

    return str(content).strip() if not _is_empty(content) else None


def classify_message_type(message: Any) -> tuple[str, Optional[str]]:
    content = extract_content_string(getattr(message, "content", None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)

    if isinstance(message, ToolMessage):
        return ("Data", content)

    if isinstance(message, AIMessage):
        return ("Agent", content)

    return ("System", content)


class AnalysisAccumulator:
    """Convert LangGraph stream chunks into a UI-friendly snapshot."""

    def __init__(self, analysts: Iterable[str]):
        self.selected_analysts = [analyst for analyst in ANALYST_ORDER if analyst in set(analysts)]
        self.agent_status: Dict[str, str] = {}
        self.report_sections: Dict[str, Optional[str]] = {}
        self.messages: List[AnalysisMessage] = []
        self.tool_calls: List[ToolCallRecord] = []
        self.final_state: Optional[Dict[str, Any]] = None
        self.decision: Optional[Any] = None
        self.report_path: Optional[str] = None
        self._processed_message_ids: set[str] = set()
        self._init_status()

    def _init_status(self) -> None:
        for analyst in self.selected_analysts:
            self.agent_status[ANALYST_LABELS[analyst]] = "pending"

        for agents in FIXED_AGENTS.values():
            for agent in agents:
                self.agent_status[agent] = "pending"

        for section, (analyst, _) in REPORT_SECTIONS.items():
            if analyst is None or analyst in self.selected_analysts:
                self.report_sections[section] = None

        if self.selected_analysts:
            self.agent_status[ANALYST_LABELS[self.selected_analysts[0]]] = "in_progress"

    def add_message(self, message_type: str, content: str) -> None:
        self.messages.append(AnalysisMessage(_timestamp(), message_type, content))
        self.messages = self.messages[-250:]

    def add_tool_call(self, tool_name: str, args: Any) -> None:
        self.tool_calls.append(ToolCallRecord(_timestamp(), tool_name, args))
        self.tool_calls = self.tool_calls[-250:]

    def update_agent_status(self, agent: str, status: str) -> None:
        if agent in self.agent_status:
            self.agent_status[agent] = status

    def update_report_section(self, section_name: str, content: str) -> None:
        if section_name in self.report_sections and content:
            self.report_sections[section_name] = content

    def update_from_chunk(self, chunk: Dict[str, Any]) -> None:
        for message in chunk.get("messages", []):
            msg_id = getattr(message, "id", None)
            if msg_id is not None:
                if msg_id in self._processed_message_ids:
                    continue
                self._processed_message_ids.add(msg_id)

            msg_type, content = classify_message_type(message)
            if content and content.strip():
                self.add_message(msg_type, content)

            for tool_call in getattr(message, "tool_calls", []) or []:
                if isinstance(tool_call, dict):
                    self.add_tool_call(tool_call.get("name", "tool"), tool_call.get("args", {}))
                else:
                    self.add_tool_call(tool_call.name, tool_call.args)

        self._update_analysts(chunk)
        self._update_research(chunk)
        self._update_trading(chunk)
        self._update_risk(chunk)

    def _update_analysts(self, chunk: Dict[str, Any]) -> None:
        found_active = False

        for analyst in ANALYST_ORDER:
            if analyst not in self.selected_analysts:
                continue

            agent_name = ANALYST_LABELS[analyst]
            report_key = ANALYST_REPORT_MAP[analyst]

            if chunk.get(report_key):
                self.update_report_section(report_key, chunk[report_key])

            has_report = bool(self.report_sections.get(report_key))
            if has_report:
                self.update_agent_status(agent_name, "completed")
            elif not found_active:
                self.update_agent_status(agent_name, "in_progress")
                found_active = True
            else:
                self.update_agent_status(agent_name, "pending")

        if not found_active and self.selected_analysts:
            if self.agent_status.get("Bull Researcher") == "pending":
                self.update_agent_status("Bull Researcher", "in_progress")

    def _update_research(self, chunk: Dict[str, Any]) -> None:
        debate_state = chunk.get("investment_debate_state")
        if not debate_state:
            return

        bull = debate_state.get("bull_history", "").strip()
        bear = debate_state.get("bear_history", "").strip()
        judge = debate_state.get("judge_decision", "").strip()

        if bull or bear:
            for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
                self.update_agent_status(agent, "in_progress")
        if bull:
            self.update_report_section("investment_plan", f"### Bull Researcher Analysis\n{bull}")
        if bear:
            self.update_report_section("investment_plan", f"### Bear Researcher Analysis\n{bear}")
        if judge:
            self.update_report_section("investment_plan", f"### Research Manager Decision\n{judge}")
            for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
                self.update_agent_status(agent, "completed")
            self.update_agent_status("Trader", "in_progress")

    def _update_trading(self, chunk: Dict[str, Any]) -> None:
        trader_plan = chunk.get("trader_investment_plan")
        if not trader_plan:
            return

        self.update_report_section("trader_investment_plan", trader_plan)
        self.update_agent_status("Trader", "completed")
        self.update_agent_status("Aggressive Analyst", "in_progress")

    def _update_risk(self, chunk: Dict[str, Any]) -> None:
        risk_state = chunk.get("risk_debate_state")
        if not risk_state:
            return

        aggressive = risk_state.get("aggressive_history", "").strip()
        conservative = risk_state.get("conservative_history", "").strip()
        neutral = risk_state.get("neutral_history", "").strip()
        judge = risk_state.get("judge_decision", "").strip()

        if aggressive:
            self.update_agent_status("Aggressive Analyst", "in_progress")
            self.update_report_section(
                "final_trade_decision",
                f"### Aggressive Analyst Analysis\n{aggressive}",
            )
        if conservative:
            self.update_agent_status("Conservative Analyst", "in_progress")
            self.update_report_section(
                "final_trade_decision",
                f"### Conservative Analyst Analysis\n{conservative}",
            )
        if neutral:
            self.update_agent_status("Neutral Analyst", "in_progress")
            self.update_report_section(
                "final_trade_decision",
                f"### Neutral Analyst Analysis\n{neutral}",
            )
        if judge:
            self.update_agent_status("Portfolio Manager", "in_progress")
            self.update_report_section("final_trade_decision", f"### Portfolio Manager Decision\n{judge}")
            for agent in (
                "Aggressive Analyst",
                "Conservative Analyst",
                "Neutral Analyst",
                "Portfolio Manager",
            ):
                self.update_agent_status(agent, "completed")

    def finish(self, final_state: Dict[str, Any], decision: Any, report_path: Optional[str] = None) -> None:
        self.final_state = final_state
        self.decision = decision
        self.report_path = report_path
        for agent in self.agent_status:
            self.agent_status[agent] = "completed"
        for section in self.report_sections:
            if final_state.get(section):
                self.update_report_section(section, final_state[section])

    def snapshot(self, stats: Optional[Dict[str, Any]] = None) -> AnalysisSnapshot:
        return AnalysisSnapshot(
            agent_status=dict(self.agent_status),
            report_sections=dict(self.report_sections),
            messages=list(self.messages),
            tool_calls=list(self.tool_calls),
            stats=dict(stats or {}),
            final_state=self.final_state,
            decision=self.decision,
            report_path=self.report_path,
        )


def save_report_to_results(final_state: Dict[str, Any], request: AnalysisRequest, config: Dict[str, Any], job_id: str) -> Path:
    save_path = Path(config["results_dir"]) / request.ticker / request.analysis_date / job_id
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    analyst_parts = []
    for key, title in (
        ("market_report", "Market Analyst"),
        ("sentiment_report", "Social Analyst"),
        ("news_report", "News Analyst"),
        ("fundamentals_report", "Fundamentals Analyst"),
    ):
        if final_state.get(key):
            section_dir = save_path / "1_analysts"
            section_dir.mkdir(exist_ok=True)
            (section_dir / f"{key}.md").write_text(final_state[key], encoding="utf-8")
            analyst_parts.append((title, final_state[key]))
    if analyst_parts:
        content = "\n\n".join(f"### {title}\n{text}" for title, text in analyst_parts)
        sections.append(f"## I. Analyst Team Reports\n\n{content}")

    debate = final_state.get("investment_debate_state") or {}
    research_parts = [
        ("Bull Researcher", debate.get("bull_history", "")),
        ("Bear Researcher", debate.get("bear_history", "")),
        ("Research Manager", debate.get("judge_decision", "")),
    ]
    research_parts = [(title, text) for title, text in research_parts if text]
    if research_parts:
        section_dir = save_path / "2_research"
        section_dir.mkdir(exist_ok=True)
        for title, text in research_parts:
            (section_dir / f"{title.lower().split()[0]}.md").write_text(text, encoding="utf-8")
        content = "\n\n".join(f"### {title}\n{text}" for title, text in research_parts)
        sections.append(f"## II. Research Team Decision\n\n{content}")

    if final_state.get("trader_investment_plan"):
        section_dir = save_path / "3_trading"
        section_dir.mkdir(exist_ok=True)
        (section_dir / "trader.md").write_text(final_state["trader_investment_plan"], encoding="utf-8")
        sections.append(f"## III. Trading Team Plan\n\n### Trader\n{final_state['trader_investment_plan']}")

    risk = final_state.get("risk_debate_state") or {}
    risk_parts = [
        ("Aggressive Analyst", risk.get("aggressive_history", "")),
        ("Conservative Analyst", risk.get("conservative_history", "")),
        ("Neutral Analyst", risk.get("neutral_history", "")),
    ]
    risk_parts = [(title, text) for title, text in risk_parts if text]
    if risk_parts:
        section_dir = save_path / "4_risk"
        section_dir.mkdir(exist_ok=True)
        for title, text in risk_parts:
            (section_dir / f"{title.lower().split()[0]}.md").write_text(text, encoding="utf-8")
        content = "\n\n".join(f"### {title}\n{text}" for title, text in risk_parts)
        sections.append(f"## IV. Risk Management Team Decision\n\n{content}")

    if risk.get("judge_decision"):
        section_dir = save_path / "5_portfolio"
        section_dir.mkdir(exist_ok=True)
        (section_dir / "decision.md").write_text(risk["judge_decision"], encoding="utf-8")
        sections.append(f"## V. Portfolio Manager Decision\n\n### Portfolio Manager\n{risk['judge_decision']}")

    header = (
        f"# Trading Analysis Report: {request.ticker}\n\n"
        f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    report_path = save_path / "complete_report.md"
    report_path.write_text(header + "\n\n".join(sections), encoding="utf-8")
    return report_path


def run_analysis_job(job: AnalysisJob) -> None:
    request = job.request
    validate_provider_credentials(request)
    config = request.to_config()
    selected_analysts = request.normalized_analysts()
    stats_handler = StatsCallbackHandler()
    accumulator = AnalysisAccumulator(selected_analysts)
    accumulator.add_message("System", f"Selected ticker: {request.ticker}")
    accumulator.add_message("System", f"Analysis date: {request.analysis_date}")
    job.update_snapshot(accumulator.snapshot(stats_handler.get_stats()))

    graph = TradingAgentsGraph(
        selected_analysts,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )
    graph.ticker = request.ticker
    graph._resolve_pending_entries(request.ticker)

    checkpointer_ctx = None
    if config.get("checkpoint_enabled"):
        checkpointer_ctx = get_checkpointer(config["data_cache_dir"], request.ticker)
        saver = checkpointer_ctx.__enter__()
        graph.graph = graph.workflow.compile(checkpointer=saver)

    try:
        past_context = graph.memory_log.get_past_context(request.ticker)
        init_agent_state = graph.propagator.create_initial_state(
            request.ticker,
            request.analysis_date,
            past_context=past_context,
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler])
        if config.get("checkpoint_enabled"):
            tid = thread_id(request.ticker, str(request.analysis_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        trace = []
        for chunk in graph.graph.stream(init_agent_state, **args):
            accumulator.update_from_chunk(chunk)
            job.update_snapshot(accumulator.snapshot(stats_handler.get_stats()))
            trace.append(chunk)

        if not trace:
            raise RuntimeError("Analysis produced no graph state.")

        final_state = trace[-1]
        decision = graph.process_signal(final_state["final_trade_decision"])
        graph.curr_state = final_state
        graph._log_state(request.analysis_date, final_state)
        graph.memory_log.store_decision(
            ticker=request.ticker,
            trade_date=request.analysis_date,
            final_trade_decision=final_state["final_trade_decision"],
        )
        if config.get("checkpoint_enabled"):
            clear_checkpoint(config["data_cache_dir"], request.ticker, str(request.analysis_date))

        report_path = save_report_to_results(final_state, request, config, job.job_id)
        accumulator.finish(final_state, decision, str(report_path))
        accumulator.add_message("System", f"Completed analysis for {request.analysis_date}")
        job.update_snapshot(accumulator.snapshot(stats_handler.get_stats()))
    finally:
        if checkpointer_ctx is not None:
            checkpointer_ctx.__exit__(None, None, None)
            graph.graph = graph.workflow.compile()


class AnalysisJobManager:
    def __init__(self, runner: Callable[[AnalysisJob], None] = run_analysis_job, start_worker: bool = True):
        self._runner = runner
        self._jobs: Dict[str, AnalysisJob] = {}
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._stop = False
        self._worker: Optional[threading.Thread] = None
        if start_worker:
            self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="tradingagents-web-worker")
            self._worker.start()

    def enqueue(self, request: AnalysisRequest) -> AnalysisJob:
        job = AnalysisJob(request=request)
        with self._condition:
            self._jobs[job.job_id] = job
            self._condition.notify()
        return job

    def cancel(self, job_id: str) -> bool:
        with self._condition:
            job = self._jobs.get(job_id)
            if not job:
                return False
            return job.mark_cancelled()

    def list_jobs(self) -> List[AnalysisJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get_job(self, job_id: str) -> Optional[AnalysisJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def wait_for_terminal(self, job_id: str, timeout: float = 10.0) -> JobStatus:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get_job(job_id)
            if job and job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
                return job.status
            time.sleep(0.05)
        raise TimeoutError(f"Job {job_id} did not finish within {timeout} seconds")

    def shutdown(self) -> None:
        with self._condition:
            self._stop = True
            self._condition.notify_all()
        if self._worker:
            self._worker.join(timeout=2)

    def _next_queued_job(self) -> Optional[AnalysisJob]:
        queued = [
            job for job in self._jobs.values()
            if job.status == JobStatus.QUEUED
        ]
        if not queued:
            return None
        return sorted(queued, key=lambda job: job.created_at)[0]

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._stop:
                    job = self._next_queued_job()
                    if job:
                        job.mark_running()
                        break
                    self._condition.wait(timeout=0.5)
                else:
                    return

            try:
                self._runner(job)
            except Exception as exc:  # pragma: no cover - exercised through tests by behavior
                job.mark_failed(str(exc))
            else:
                if job.status == JobStatus.RUNNING:
                    job.mark_completed()
            finally:
                with self._condition:
                    self._condition.notify_all()


def list_saved_reports(results_dir: str | Path, limit: int = 50) -> List[Path]:
    root = Path(results_dir)
    if not root.exists():
        return []
    reports = sorted(root.rglob("complete_report.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[:limit]
