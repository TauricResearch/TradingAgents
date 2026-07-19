"""Translate shared AnalysisRunner state updates into the legacy CLI display."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


class CliRunObserver:
    """Render graph state updates without owning graph execution or completion."""

    def __init__(
        self,
        message_buffer: Any,
        *,
        wall_time_tracker: Any,
        classify_message: Callable[[Any], tuple[str, str | None]],
        update_analysts: Callable[..., None],
        refresh_display: Callable[[], None],
    ) -> None:
        self.message_buffer = message_buffer
        self.wall_time_tracker = wall_time_tracker
        self.classify_message = classify_message
        self.update_analysts = update_analysts
        self.refresh_display = refresh_display

    def __call__(self, chunk: Mapping[str, Any]) -> None:
        self._record_messages(chunk)
        self.update_analysts(
            self.message_buffer,
            chunk,
            wall_time_tracker=self.wall_time_tracker,
        )
        self._record_research(chunk)
        self._record_trading(chunk)
        self._record_risk(chunk)
        self.refresh_display()

    def _record_messages(self, chunk: Mapping[str, Any]) -> None:
        for message in chunk.get("messages", ()):
            message_id = getattr(message, "id", None)
            if message_id is not None:
                if message_id in self.message_buffer._processed_message_ids:
                    continue
                self.message_buffer._processed_message_ids.add(message_id)

            message_type, content = self.classify_message(message)
            if content and content.strip():
                self.message_buffer.add_message(message_type, content)

            for tool_call in getattr(message, "tool_calls", ()) or ():
                if isinstance(tool_call, Mapping):
                    self.message_buffer.add_tool_call(
                        tool_call["name"],
                        tool_call["args"],
                    )
                else:
                    self.message_buffer.add_tool_call(tool_call.name, tool_call.args)

    def _record_research(self, chunk: Mapping[str, Any]) -> None:
        debate_state = chunk.get("investment_debate_state")
        if not isinstance(debate_state, Mapping):
            return
        bull_history = str(debate_state.get("bull_history") or "").strip()
        bear_history = str(debate_state.get("bear_history") or "").strip()
        judge = str(debate_state.get("judge_decision") or "").strip()

        if bull_history or bear_history:
            self._set_research_team_status("in_progress")
        if bull_history:
            self.message_buffer.update_report_section(
                "investment_plan",
                f"### 多方研究员分析\n{bull_history}",
            )
        if bear_history:
            self.message_buffer.update_report_section(
                "investment_plan",
                f"### 空方研究员分析\n{bear_history}",
            )
        if judge:
            self.message_buffer.update_report_section(
                "investment_plan",
                f"### 研究经理决策\n{judge}",
            )
            self._set_research_team_status("completed")
            self.message_buffer.update_agent_status("Trader", "in_progress")

    def _record_trading(self, chunk: Mapping[str, Any]) -> None:
        plan = chunk.get("trader_investment_plan")
        if not plan:
            return
        self.message_buffer.update_report_section("trader_investment_plan", plan)
        if self.message_buffer.agent_status.get("Trader") != "completed":
            self.message_buffer.update_agent_status("Trader", "completed")
            self.message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

    def _record_risk(self, chunk: Mapping[str, Any]) -> None:
        risk_state = chunk.get("risk_debate_state")
        if not isinstance(risk_state, Mapping):
            return
        histories = (
            (
                "Aggressive Analyst",
                "激进风险分析师分析",
                str(risk_state.get("aggressive_history") or "").strip(),
            ),
            (
                "Conservative Analyst",
                "保守风险分析师分析",
                str(risk_state.get("conservative_history") or "").strip(),
            ),
            (
                "Neutral Analyst",
                "中性风险分析师分析",
                str(risk_state.get("neutral_history") or "").strip(),
            ),
        )
        for agent, title, history in histories:
            if not history:
                continue
            if self.message_buffer.agent_status.get(agent) != "completed":
                self.message_buffer.update_agent_status(agent, "in_progress")
            self.message_buffer.update_report_section(
                "final_trade_decision",
                f"### {title}\n{history}",
            )

        judge = str(risk_state.get("judge_decision") or "").strip()
        if not judge or self.message_buffer.agent_status.get(
            "Portfolio Manager"
        ) == "completed":
            return
        self.message_buffer.update_agent_status("Portfolio Manager", "in_progress")
        self.message_buffer.update_report_section(
            "final_trade_decision",
            f"### 组合经理决策\n{judge}",
        )
        for agent in (
            "Aggressive Analyst",
            "Conservative Analyst",
            "Neutral Analyst",
            "Portfolio Manager",
        ):
            self.message_buffer.update_agent_status(agent, "completed")

    def _set_research_team_status(self, status: str) -> None:
        for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
            self.message_buffer.update_agent_status(agent, status)

