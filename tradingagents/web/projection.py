"""Server-side projection of raw langgraph ``updates`` chunks into slim events.

Raw ``updates`` events are MBs per run (full tool CSVs, duplicated reports,
cumulative debate histories). Only the projected, typed events below enter
the replay log. The mapping mirrors the CLI's projection loop (cli/main.py),
so the web view and the terminal view tell the same story.

Typed events produced (event_type, data):

- ``agent_status``  {agent, team, status: pending|working|done}
- ``report_section`` {section, markdown}  (whole accumulated section)
- ``tool_call``     {name, args_preview}
- ``message``       {agent, preview}
"""

from __future__ import annotations

from typing import Any

from tradingagents.graph.analyst_execution import build_analyst_execution_plan

# Section -> UI title, mirroring cli/main.py REPORT_SECTIONS ordering.
REPORT_SECTIONS: dict[str, str] = {
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}

# Fixed (non-analyst) agents and their teams, mirroring MessageBuffer.
FIXED_TEAMS: dict[str, list[str]] = {
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
    "Portfolio Management": ["Portfolio Manager"],
}

ARGS_PREVIEW_LENGTH = 120
MESSAGE_PREVIEW_LENGTH = 240


def _preview(value: Any, max_length: int) -> str:
    text = str(value)
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _message_content(message: Any) -> str:
    """Flatten a langchain message content (str or block list) to text."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return str(content)


class RunProjector:
    """Stateful reducer: feed per-node ``updates`` deltas, get typed events."""

    def __init__(self, selected_analysts: list[str]):
        self.plan = build_analyst_execution_plan(selected_analysts)
        self.state: dict[str, Any] = {}

        self.agent_teams: dict[str, str] = {}
        for spec in self.plan.specs:
            self.agent_teams[spec.agent_node] = "Analyst Team"
        for team, agents in FIXED_TEAMS.items():
            for agent in agents:
                self.agent_teams[agent] = team

        self.agent_status: dict[str, str] = dict.fromkeys(self.agent_teams, "pending")
        self.sections: dict[str, str] = {}
        self.tool_call_count = 0
        self._seen_message_ids: set[str] = set()
        self._emitted_status: dict[str, str] = {}

        # Analyst agent/tool/clear nodes all map back to the analyst's spec.
        self._node_to_spec = {}
        for spec in self.plan.specs:
            self._node_to_spec[spec.agent_node] = spec
            self._node_to_spec[spec.tool_node] = spec
            self._node_to_spec[spec.clear_node] = spec

    # -- public API -------------------------------------------------------

    def feed(self, chunk: dict[str, Any]) -> list[tuple[str, dict]]:
        """Project one ``updates`` chunk ({node_name: state_delta})."""
        events: list[tuple[str, dict]] = []
        for node, delta in chunk.items():
            if not isinstance(delta, dict):
                continue
            self._merge(delta)
            events.extend(self._message_events(node, delta))
            self._apply_node_status(node, delta)

        self._apply_state_status()
        events.extend(self._section_events())
        # Status flips are computed after sections so a finished analyst's
        # section and its "done" flip arrive in the same batch.
        events.extend(self._status_events())
        return events

    def final_events(self) -> list[tuple[str, dict]]:
        """Terminal flush: everything done + final section contents."""
        for agent in self.agent_status:
            self.agent_status[agent] = "done"
        events = self._section_events(force_from_state=True)
        events.extend(self._status_events())
        return events

    @property
    def merged_state(self) -> dict[str, Any]:
        return self.state

    # -- internals --------------------------------------------------------

    def _merge(self, delta: dict[str, Any]) -> None:
        for key, value in delta.items():
            if key == "messages":
                continue  # message history is projected, never accumulated
            self.state[key] = value

    def _message_events(self, node: str, delta: dict[str, Any]) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        for message in delta.get("messages") or []:
            message_id = getattr(message, "id", None)
            if message_id is not None:
                if message_id in self._seen_message_ids:
                    continue
                self._seen_message_ids.add(message_id)

            for tool_call in getattr(message, "tool_calls", None) or []:
                if isinstance(tool_call, dict):
                    name, args = tool_call.get("name"), tool_call.get("args")
                else:
                    name, args = getattr(tool_call, "name", None), getattr(tool_call, "args", None)
                if not name:
                    continue
                self.tool_call_count += 1
                events.append(("tool_call", {
                    "name": name,
                    "args_preview": _preview(args, ARGS_PREVIEW_LENGTH),
                }))

            content = _message_content(message).strip()
            if content:
                events.append(("message", {
                    "agent": node,
                    "preview": _preview(content, MESSAGE_PREVIEW_LENGTH),
                }))
        return events

    def _apply_node_status(self, node: str, delta: dict[str, Any]) -> None:
        spec = self._node_to_spec.get(node)
        if spec is not None:
            if delta.get(spec.report_key) or node == spec.clear_node:
                self._set_done(spec.agent_node)
            else:
                self._set_working(spec.agent_node)
            return
        if node in self.agent_status:
            self._set_working(node)

    def _apply_state_status(self) -> None:
        """State-driven completion, mirroring the CLI's chunk rules."""
        for spec in self.plan.specs:
            if self.state.get(spec.report_key):
                self._set_done(spec.agent_node)

        debate = self.state.get("investment_debate_state") or {}
        if debate.get("judge_decision", "").strip():
            for agent in FIXED_TEAMS["Research Team"]:
                self._set_done(agent)
            self._set_working("Trader")

        if self.state.get("trader_investment_plan"):
            self._set_done("Trader")
            self._set_working("Aggressive Analyst")

        risk = self.state.get("risk_debate_state") or {}
        if risk.get("judge_decision", "").strip():
            for agent in FIXED_TEAMS["Risk Management"]:
                self._set_done(agent)
            self._set_done("Portfolio Manager")

    def _set_working(self, agent: str) -> None:
        if self.agent_status.get(agent) == "pending":
            self.agent_status[agent] = "working"

    def _set_done(self, agent: str) -> None:
        if self.agent_status.get(agent) != "done":
            self.agent_status[agent] = "done"

    def _status_events(self) -> list[tuple[str, dict]]:
        events = []
        for agent, status in self.agent_status.items():
            if self._emitted_status.get(agent) != status:
                events.append(("agent_status", {
                    "agent": agent,
                    "team": self.agent_teams[agent],
                    "status": status,
                }))
                self._emitted_status[agent] = status
        return events

    def _section_events(self, force_from_state: bool = False) -> list[tuple[str, dict]]:
        """Emit whole-section markdown for every section whose content changed."""
        events = []
        for section in REPORT_SECTIONS:
            content = self._compose_section(section, force_from_state)
            if content and content != self.sections.get(section):
                self.sections[section] = content
                events.append(("report_section", {
                    "section": section,
                    "markdown": content,
                }))
        return events

    def _compose_section(self, section: str, force_from_state: bool) -> str | None:
        value = self.state.get(section)
        if isinstance(value, str) and value.strip():
            return value

        # During the debates the final channel is still empty; compose the
        # in-progress view from the debate histories, like the CLI does.
        if section == "investment_plan" and not force_from_state:
            debate = self.state.get("investment_debate_state") or {}
            parts = []
            if debate.get("bull_history", "").strip():
                parts.append(f"### Bull Researcher Analysis\n{debate['bull_history'].strip()}")
            if debate.get("bear_history", "").strip():
                parts.append(f"### Bear Researcher Analysis\n{debate['bear_history'].strip()}")
            if debate.get("judge_decision", "").strip():
                parts.append(f"### Research Manager Decision\n{debate['judge_decision'].strip()}")
            if parts:
                return "\n\n".join(parts)

        if section == "final_trade_decision" and not force_from_state:
            risk = self.state.get("risk_debate_state") or {}
            parts = []
            for label, key in (
                ("Aggressive Analyst Analysis", "aggressive_history"),
                ("Conservative Analyst Analysis", "conservative_history"),
                ("Neutral Analyst Analysis", "neutral_history"),
                ("Portfolio Manager Decision", "judge_decision"),
            ):
                if risk.get(key, "").strip():
                    parts.append(f"### {label}\n{risk[key].strip()}")
            if parts:
                return "\n\n".join(parts)

        return None
