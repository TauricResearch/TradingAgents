"""Thread-safe progress tracker for the TradingAgents pipeline.

Shared data layer between CLI (Rich TUI) and Desktop (NiceGUI).
The pipeline thread writes updates; the UI thread reads snapshots.
All public methods are protected by a ``threading.Lock``.

See also: PLAN-desktop.md, Phase 1.
"""

from __future__ import annotations

import copy
import datetime
import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────

# Fixed teams that always run (not user-selectable)
FIXED_AGENTS: dict[str, list[str]] = {
    "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "Trading Team": ["Trader"],
    "Risk Management": [
        "Aggressive Analyst",
        "Neutral Analyst",
        "Conservative Analyst",
    ],
    "Portfolio Management": ["Portfolio Manager"],
}

# Analyst key -> display name
ANALYST_MAPPING: dict[str, str] = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

# Report section -> (analyst_key for filtering, finalizing_agent)
# analyst_key ``None`` means the section is always included.
REPORT_SECTIONS: dict[str, tuple[str | None, str]] = {
    "market_report": ("market", "Market Analyst"),
    "sentiment_report": ("social", "Sentiment Analyst"),
    "news_report": ("news", "News Analyst"),
    "fundamentals_report": ("fundamentals", "Fundamentals Analyst"),
    "investment_plan": (None, "Research Manager"),
    "trader_investment_plan": (None, "Trader"),
    "final_trade_decision": (None, "Portfolio Manager"),
}

SECTION_TITLES: dict[str, str] = {
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
}

# ── Immutable snapshot returned to UI ────────────────────────────────────


@dataclass(frozen=True)
class ProgressSnapshot:
    """Read-only snapshot of pipeline progress.

    Returned by ``ProgressTracker.snapshot()`` for safe cross-thread
    consumption. All fields are copies -- mutating them does not affect
    the tracker.
    """

    agent_status: dict[str, str]
    report_sections: dict[str, str | None]
    messages: list[tuple[str, str, str]]
    tool_calls: list[tuple[str, str, Any]]
    current_agent: str | None
    selected_analysts: list[str]
    last_activity: datetime.datetime | None


# ── Thread-safe tracker ──────────────────────────────────────────────────


class ProgressTracker:
    """Thread-safe progress state shared between pipeline and UI.

    The pipeline thread calls ``add_message``, ``update_agent_status``,
    etc.  The UI thread calls ``snapshot()`` to get an immutable copy
    of the current state.

    Parameters
    ----------
    max_messages : int
        Maximum number of messages and tool calls to retain (FIFO).
    """

    def __init__(self, max_messages: int = 100) -> None:
        self._lock = threading.Lock()
        self._max_messages = max_messages

        # Mutable state -- only written under lock
        self._agent_status: dict[str, str] = {}
        self._report_sections: dict[str, str | None] = {}
        self._messages: deque[tuple[str, str, str]] = deque(maxlen=max_messages)
        self._tool_calls: deque[tuple[str, str, Any]] = deque(maxlen=max_messages)
        self._current_agent: str | None = None
        self._selected_analysts: list[str] = []
        self._processed_message_ids: set[str] = set()
        self._last_activity: datetime.datetime | None = None

    # ── Initialization ───────────────────────────────────────────────

    def init_for_analysis(self, selected_analysts: list[str]) -> None:
        """Reset and configure for a new analysis run.

        Must be called before the pipeline starts streaming.
        """
        with self._lock:
            analysts = [a.lower() for a in selected_analysts]
            self._selected_analysts = analysts

            # Build agent_status dynamically
            self._agent_status = {}
            for key in analysts:
                name = ANALYST_MAPPING.get(key)
                if name:
                    self._agent_status[name] = "pending"
            for team_agents in FIXED_AGENTS.values():
                for agent in team_agents:
                    self._agent_status[agent] = "pending"

            # Build report_sections dynamically
            self._report_sections = {}
            for section, (analyst_key, _) in REPORT_SECTIONS.items():
                if analyst_key is None or analyst_key in analysts:
                    self._report_sections[section] = None

            # Reset transient state
            self._current_agent = None
            self._messages.clear()
            self._tool_calls.clear()
            self._processed_message_ids.clear()
            self._last_activity = datetime.datetime.now()

    # ── Pipeline-side writes ─────────────────────────────────────────

    def add_message(self, message_type: str, content: str) -> None:
        """Append a timestamped message to the log."""
        with self._lock:
            now = datetime.datetime.now()
            ts = now.strftime("%H:%M:%S")
            self._messages.append((ts, message_type, content))
            self._last_activity = now

    def add_tool_call(self, tool_name: str, args: Any) -> None:
        """Record a tool invocation.

        ``args`` is deep-copied so the snapshot never shares mutable
        references with the caller (CR-01).
        """
        safe_args = copy.deepcopy(args)
        with self._lock:
            now = datetime.datetime.now()
            ts = now.strftime("%H:%M:%S")
            self._tool_calls.append((ts, tool_name, safe_args))
            self._last_activity = now

    def update_agent_status(self, agent: str, status: str) -> None:
        """Set an agent's status (pending / in_progress / completed / error)."""
        with self._lock:
            if agent in self._agent_status:
                self._agent_status[agent] = status
                self._current_agent = agent
                self._last_activity = datetime.datetime.now()
            else:
                logger.warning("Unknown agent %r ignored (known: %s)", agent, list(self._agent_status))

    def update_report_section(self, section_name: str, content: str) -> None:
        """Store (or overwrite) a report section's content."""
        with self._lock:
            if section_name in self._report_sections:
                self._report_sections[section_name] = content
                self._last_activity = datetime.datetime.now()
            else:
                logger.warning("Unknown report section %r ignored", section_name)

    def has_seen_message(self, message_id: str) -> bool:
        """Check and mark a message ID as processed (deduplication)."""
        with self._lock:
            if message_id in self._processed_message_ids:
                return True
            self._processed_message_ids.add(message_id)
            return False

    # ── UI-side reads ────────────────────────────────────────────────

    def snapshot(self) -> ProgressSnapshot:
        """Return an immutable copy of the current state.

        Safe to call from any thread. The returned object contains
        only copies -- the caller can read it at leisure without
        holding the lock.
        """
        with self._lock:
            return ProgressSnapshot(
                agent_status=dict(self._agent_status),
                report_sections=dict(self._report_sections),
                messages=list(self._messages),
                tool_calls=list(self._tool_calls),
                current_agent=self._current_agent,
                selected_analysts=list(self._selected_analysts),
                last_activity=self._last_activity,
            )

    def get_completed_reports_count(self) -> int:
        """Count reports whose finalizing agent has completed."""
        with self._lock:
            count = 0
            for section in self._report_sections:
                meta = REPORT_SECTIONS.get(section)
                if meta is None:
                    continue
                _, finalizing_agent = meta
                has_content = self._report_sections.get(section) is not None
                agent_done = self._agent_status.get(finalizing_agent) == "completed"
                if has_content and agent_done:
                    count += 1
            return count

    def get_total_reports_count(self) -> int:
        """Return total number of expected report sections."""
        with self._lock:
            return len(self._report_sections)

    def seconds_since_last_activity(self) -> float | None:
        """Seconds elapsed since the last pipeline write, or None if idle."""
        with self._lock:
            if self._last_activity is None:
                return None
            delta = datetime.datetime.now() - self._last_activity
            return delta.total_seconds()
