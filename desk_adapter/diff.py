"""Turn consecutive ``stream_mode="values"`` whole-state snapshots into a typed,
append-only event stream.

The TradingAgents graph streams full accumulated state on every step (verified:
``tradingagents/graph/propagation.py`` ``get_graph_args`` -> ``stream_mode="values"``).
This module holds the previous view of the world and emits only what is new,
porting the CLI's proven derivation logic (``cli/main.py``: ``update_analyst_statuses``,
``classify_message_type``, ``extract_content_string``, and the investment/risk
debate handling) into structured events instead of Rich panels.

Dependency-free and duck-typed: it never imports ``tradingagents`` or
``langchain`` so it runs and is unit-testable on any interpreter. LangChain
message objects are read via ``.type`` / ``.content`` / ``.tool_calls`` /
``.tool_call_id`` / ``.id`` (with attribute-sniffing fallbacks for test fakes).
"""

from __future__ import annotations

import ast
import re
from typing import Any

# --- Static maps (mirror cli/main.py MessageBuffer) ---

ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_AGENT = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}
RESEARCH_AGENTS = ["Bull Researcher", "Bear Researcher", "Research Manager"]
RISK_AGENTS = ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"]

REPORT_TITLES = {
    "market_report": "Market analysis",
    "sentiment_report": "Sentiment analysis",
    "news_report": "News analysis",
    "fundamentals_report": "Fundamentals analysis",
    "investment_plan": "Research decision",
    "trader_investment_plan": "Trader plan",
    "final_trade_decision": "Portfolio decision",
}
REPORT_FINALIZER = {
    "market_report": "Market Analyst",
    "sentiment_report": "Sentiment Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
    "investment_plan": "Research Manager",
    "trader_investment_plan": "Trader",
    "final_trade_decision": "Portfolio Manager",
}

_GROUP = {}
for _a in ANALYST_AGENT.values():
    _GROUP[_a] = "analyst"
for _a in RESEARCH_AGENTS:
    _GROUP[_a] = "research"
_GROUP["Trader"] = "trader"
for _a in RISK_AGENTS:
    _GROUP[_a] = "risk"
_GROUP["Portfolio Manager"] = "portfolio"

# The non-analyst pipeline tail, shared by ``_PIPELINE`` and the initial status map.
_NON_ANALYST_PIPELINE = RESEARCH_AGENTS + ["Trader"] + RISK_AGENTS + ["Portfolio Manager"]

# Pipeline order used to resolve the single "active" agent for step attribution.
_PIPELINE = list(ANALYST_AGENT.values()) + _NON_ANALYST_PIPELINE

# Each debate turn is appended to its OWN speaker's history field as
# "\n<Speaker> Analyst: <text>" (bull_researcher.py:53, aggressive_debator.py:45,
# etc.). Deriving turns from the per-speaker histories — rather than scanning the
# shared combined ``history`` — means content that quotes another speaker by name
# (risk debators are prompted to rebut "the conservative and neutral analysts")
# can't manufacture a phantom turn or corrupt the round numbering.
_DEBATE_SPEAKERS: dict[str, list[tuple[str, str]]] = {
    "investment": [("Bull Analyst", "bull_history"), ("Bear Analyst", "bear_history")],
    "risk": [
        ("Aggressive Analyst", "aggressive_history"),
        ("Conservative Analyst", "conservative_history"),
        ("Neutral Analyst", "neutral_history"),
    ],
}
_SENTIMENT_SCORE_RE = re.compile(r"Score:\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10")

NO_DATA_PREFIX = "NO_DATA_AVAILABLE"


def extract_content_string(content: Any) -> str | None:
    """Extract displayable text from a LangChain message ``content`` field.

    Ported verbatim in behavior from ``cli/main.py:extract_content_string`` so
    GUI and CLI agree on what counts as real text. Returns ``None`` for empty.
    """

    def is_empty(val: Any) -> bool:
        if val is None or val == "":
            return True
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return True
            try:
                return not bool(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return False
        return not bool(val)

    if is_empty(content):
        return None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        text = content.get("text", "")
        return text.strip() if not is_empty(text) else None
    if isinstance(content, list):
        parts = [
            item.get("text", "").strip()
            if isinstance(item, dict) and item.get("type") == "text"
            else (item.strip() if isinstance(item, str) else "")
            for item in content
        ]
        result = " ".join(p for p in parts if p and not is_empty(p))
        return result or None
    return str(content).strip() if not is_empty(content) else None


def _split_speaker_history(history: str, speaker: str) -> list[str]:
    """Split one speaker's accumulated debate history into that speaker's turn texts.

    Splits on the speaker's OWN line-start prefix only, so a turn whose content
    quotes a different speaker's name can never create a phantom turn.
    """
    if not history:
        return []
    prefix = re.compile(rf"^{re.escape(speaker)}:[ \t]*", re.MULTILINE)
    matches = list(prefix.finditer(history))
    turns: list[str] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(history)
        turns.append(history[m.end() : end].strip())
    return turns


def extract_sentiment_score(report: str) -> float | None:
    """Pull the 0-10 score out of the Sentiment Analyst's structured header."""
    if not report:
        return None
    m = _SENTIMENT_SCORE_RE.search(report)
    return float(m.group(1)) if m else None


def _msg_type(msg: Any) -> str:
    """Duck-typed message kind: ai | tool | human | system | remove | other."""
    t = getattr(msg, "type", None)
    if isinstance(t, str) and t:
        return t
    if getattr(msg, "tool_call_id", None) is not None:
        return "tool"
    if getattr(msg, "tool_calls", None):
        return "ai"
    return "other"


def _toolcall_fields(tc: Any) -> tuple[str, Any, str]:
    """Normalize a tool call (dict or object) to (name, args, call_id)."""
    if isinstance(tc, dict):
        return tc.get("name", ""), tc.get("args", {}), tc.get("id", "")
    return getattr(tc, "name", ""), getattr(tc, "args", {}), getattr(tc, "id", "")


class SnapshotDiffer:
    """Stateful diff: feed it whole-state snapshots, get back new events.

    Construct once per run with the selected analyst keys, then call
    ``process(snapshot)`` for each streamed chunk. Returned events are dicts
    carrying a ``type`` key plus that event's fields (no envelope — the
    ``Emitter`` adds ``v``/``run_id``/``seq``/``ts``).
    """

    def __init__(self, selected_analysts: list[str]):
        self.selected = [a.lower() for a in selected_analysts]
        self.status: dict[str, str] = {}
        for k in ANALYST_ORDER:
            if k in self.selected:
                self.status[ANALYST_AGENT[k]] = "pending"
        for agent in _NON_ANALYST_PIPELINE:
            self.status[agent] = "pending"
        self.active: str | None = None
        self.reports: dict[str, str] = {}
        self.processed_ids: set = set()
        self.tool_index: dict[str, str] = {}
        self._emitted_turns: dict[str, dict[str, int]] = {"investment": {}, "risk": {}}
        self._debate_count = {"investment": 0, "risk": 0}
        self._judge_emitted = {"investment": False, "risk": False}

    # -- public API --

    def process(self, snapshot: dict) -> list[dict]:
        events: list[dict] = []
        events += self._status_events(snapshot)  # first: lights up the rail + sets self.active
        events += self._message_events(snapshot)
        events += self._report_events(snapshot)
        events += self._debate_events(snapshot, "investment", "investment_debate_state")
        events += self._debate_events(snapshot, "risk", "risk_debate_state")
        return events

    # -- status (ported from cli/main.py:update_analyst_statuses + debate transitions) --

    def _status_events(self, snap: dict) -> list[dict]:
        desired = dict(self.status)
        found_active = False
        for k in ANALYST_ORDER:
            if k not in self.selected:
                continue
            agent = ANALYST_AGENT[k]
            has_report = bool(snap.get(ANALYST_REPORT[k])) or bool(self.reports.get(ANALYST_REPORT[k]))
            if has_report:
                desired[agent] = "completed"
            elif not found_active:
                desired[agent] = "in_progress"
                found_active = True
            else:
                desired[agent] = "pending"
        if not found_active and self.selected and desired.get("Bull Researcher") == "pending":
            desired["Bull Researcher"] = "in_progress"

        inv = snap.get("investment_debate_state") or {}
        if (inv.get("bull_history") or "").strip() and desired.get("Bull Researcher") != "completed":
            desired["Bull Researcher"] = "in_progress"
        if (inv.get("bear_history") or "").strip() and desired.get("Bear Researcher") != "completed":
            desired["Bear Researcher"] = "in_progress"
        if (inv.get("judge_decision") or "").strip() or snap.get("investment_plan"):
            desired["Bull Researcher"] = "completed"
            desired["Bear Researcher"] = "completed"
            desired["Research Manager"] = "completed"
            if desired.get("Trader") == "pending":
                desired["Trader"] = "in_progress"

        if snap.get("trader_investment_plan"):
            desired["Trader"] = "completed"
            if desired.get("Aggressive Analyst") == "pending":
                desired["Aggressive Analyst"] = "in_progress"

        risk = snap.get("risk_debate_state") or {}
        for hist_key, agent in (
            ("aggressive_history", "Aggressive Analyst"),
            ("conservative_history", "Conservative Analyst"),
            ("neutral_history", "Neutral Analyst"),
        ):
            if (risk.get(hist_key) or "").strip() and desired.get(agent) != "completed":
                desired[agent] = "in_progress"
        if (risk.get("judge_decision") or "").strip() or snap.get("final_trade_decision"):
            for agent in RISK_AGENTS:
                desired[agent] = "completed"
            desired["Portfolio Manager"] = "completed"

        events = []
        for agent, state in desired.items():
            if self.status.get(agent) != state:
                self.status[agent] = state
                events.append(
                    {"type": "node_status", "node": agent, "group": _GROUP.get(agent, ""), "state": state}
                )
        self.active = self._active_agent()
        return events

    def _active_agent(self) -> str | None:
        for agent in _PIPELINE:
            if self.status.get(agent) == "in_progress":
                return agent
        last_completed = None
        for agent in _PIPELINE:
            if self.status.get(agent) == "completed":
                last_completed = agent
        return last_completed

    # -- messages -> agent_step / tool_call / tool_result --

    def _message_events(self, snap: dict) -> list[dict]:
        events = []
        for msg in snap.get("messages") or []:
            key = self._dedupe_key(msg)
            if key in self.processed_ids:
                continue
            self.processed_ids.add(key)
            mtype = _msg_type(msg)
            content = extract_content_string(getattr(msg, "content", None))
            if mtype == "ai":
                if content:
                    events.append(
                        {
                            "type": "agent_step",
                            "node": self.active or "",
                            "role": self.active or "",
                            "text": content,
                            "text_kind": "reasoning",
                            "is_final": False,
                        }
                    )
                for tc in getattr(msg, "tool_calls", None) or []:
                    name, args, call_id = _toolcall_fields(tc)
                    if call_id:
                        self.tool_index[call_id] = name
                    events.append(
                        {
                            "type": "tool_call",
                            "node": self.active or "",
                            "call_id": call_id,
                            "name": name,
                            "args": args if isinstance(args, (dict, list)) else str(args),
                        }
                    )
            elif mtype == "tool":
                call_id = getattr(msg, "tool_call_id", None)
                name = self.tool_index.get(call_id, getattr(msg, "name", "") or "")
                text = content or ""
                no_data = text.startswith(NO_DATA_PREFIX)
                events.append(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "name": name,
                        "ok": not no_data,
                        "preview": text[:280],
                        "full": text,
                        "data_status": "no_data" if no_data else "ok",
                    }
                )
        return events

    def _dedupe_key(self, msg: Any):
        mid = getattr(msg, "id", None)
        if mid is not None:
            return mid
        # id-less fakes/messages: best-effort stable key
        return (
            "anon",
            _msg_type(msg),
            getattr(msg, "tool_call_id", None),
            hash(extract_content_string(getattr(msg, "content", None)) or ""),
        )

    # -- report sections --

    def _report_events(self, snap: dict) -> list[dict]:
        events = []
        for section, title in REPORT_TITLES.items():
            val = snap.get(section)
            if val and val != self.reports.get(section):
                self.reports[section] = val
                event = {
                    "type": "report_section",
                    "section": section,
                    "title": title,
                    "markdown": val,
                    "finalized": self.status.get(REPORT_FINALIZER[section]) == "completed",
                }
                if section == "sentiment_report":
                    score = extract_sentiment_score(val)
                    if score is not None:
                        event["sentiment_score"] = score
                events.append(event)
        return events

    # -- debates -> ordered, speaker-attributed turns --

    def _debate_events(self, snap: dict, name: str, key: str) -> list[dict]:
        state = snap.get(key) or {}
        speakers = _DEBATE_SPEAKERS[name]
        per_round = len(speakers)
        emitted = self._emitted_turns[name]
        events = []
        # Emit each speaker's new turns in fixed graph order. In a live run exactly
        # one speaker's history grows per snapshot, so the global index — and thus
        # the round (index // per_round + 1) — follows the real debate order.
        for label, field in speakers:
            turns = _split_speaker_history(state.get(field) or "", label)
            for j in range(emitted.get(label, 0), len(turns)):
                idx = self._debate_count[name]
                events.append(
                    {
                        "type": "debate_turn",
                        "debate": name,
                        "round": idx // per_round + 1,
                        "index": idx + 1,
                        "speaker": label,
                        "text": turns[j],
                        "is_judge": False,
                    }
                )
                self._debate_count[name] = idx + 1
            emitted[label] = len(turns)

        judge = (state.get("judge_decision") or "").strip()
        if judge and not self._judge_emitted[name]:
            self._judge_emitted[name] = True
            events.append(
                {
                    "type": "debate_turn",
                    "debate": name,
                    "round": 0,
                    "index": self._debate_count[name] + 1,
                    "speaker": "Research Manager" if name == "investment" else "Portfolio Manager",
                    "text": judge,
                    "is_judge": True,
                }
            )
        return events
