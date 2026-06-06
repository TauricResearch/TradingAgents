"""Per-agent context state — a context window tailored to each agent's task.

Each agent owns an ``AgentContext``: a structured, accumulating working memory
for one analysis, organised into **sections cut to that agent's job** (e.g. the
Technical agent has price / indicators / volume; the Market agent has macro /
catalysts / price / portfolio). It starts from the injected first context (warm
start) and files every tool result into the right section, keeping the structure.
It is carried in the graph state, so it lasts intact and self-maintains across
the agent's tool-call rounds and the "when in doubt, ask" revisions, until the
end of the task. Durable facts live in the DB; this is the working memory.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Which section each tool's result is filed under, per agent (ad-hoc structure).
_TOOL_SECTIONS: dict[str, dict[str, str]] = {
    "market": {"macro": "macro", "news": "catalysts", "quote": "price",
               "prices": "price", "indicators": "price", "portfolio_risk": "portfolio"},
    "sentiment": {"news": "news", "social": "social", "quote": "price",
                  "portfolio_risk": "portfolio"},
    "technical": {"quote": "price", "prices": "price", "indicators": "indicators",
                  "volume": "volume"},
    "fundamental": {"fundamentals": "valuation", "quote": "price", "prices": "price"},
    "risk": {"quote": "price", "indicators": "indicators", "news": "news",
             "fundamentals": "fundamentals", "portfolio_risk": "portfolio"},
}

_FOCUS: dict[str, str] = {
    "market": "macro & sector regime, news catalysts",
    "sentiment": "mood across news + social, positioning vs price",
    "technical": "trend, momentum, volatility (ATR), key levels",
    "fundamental": "valuation, balance-sheet health, earnings/event risk",
    "risk": "bear case + deterministic Statute guardrails",
}

# Order in which sections render, per agent (also defines the empty skeleton).
_SECTION_ORDER: dict[str, list[str]] = {
    "market": ["macro", "catalysts", "price", "portfolio"],
    "sentiment": ["news", "social", "price", "portfolio"],
    "technical": ["price", "indicators", "volume"],
    "fundamental": ["valuation", "price"],
    "risk": ["price", "indicators", "news", "fundamentals", "portfolio"],
}


class ToolRecord(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: str = ""


class AgentContext(BaseModel):
    agent: str
    focus: str = ""
    injected: str = ""
    section_map: dict[str, str] = Field(default_factory=dict)  # tool -> section
    section_order: list[str] = Field(default_factory=list)
    sections: dict[str, list[ToolRecord]] = Field(default_factory=dict)
    rounds: int = 0

    @property
    def tool_records(self) -> list[ToolRecord]:
        """All accumulated tool results, flattened (across sections)."""
        return [r for recs in self.sections.values() for r in recs]

    def add_tool_record(self, tool: str, args: dict[str, Any], result: Any) -> None:
        """File a tool result into its task-specific section (preserving structure)."""
        section = self.section_map.get(tool, "misc")
        self.sections.setdefault(section, []).append(
            ToolRecord(tool=tool, args=args, result=str(result)[:2000])
        )

    def render(self) -> str:
        """Render the structured, sectioned context to the text the agent reads."""
        parts: list[str] = []
        if self.focus:
            parts.append(f"# focus: {self.focus}")
        if self.injected:
            parts.append(self.injected)
        order = self.section_order or list(self.sections.keys())
        seen = set()
        for sec in [*order, *[k for k in self.sections if k not in order]]:
            if sec in seen:
                continue
            seen.add(sec)
            recs = self.sections.get(sec)
            if not recs:
                continue
            parts.append(f"<{sec}>")
            for r in recs:
                parts.append(f"- {r.tool}({r.args}): {r.result}")
            parts.append(f"</{sec}>")
        return "\n".join(parts)


def make_agent_context(agent: str, injected: str = "") -> AgentContext:
    """Create the context structure tailored to ``agent``'s task."""
    return AgentContext(
        agent=agent,
        focus=_FOCUS.get(agent, ""),
        injected=injected,
        section_map=_TOOL_SECTIONS.get(agent, {}),
        section_order=_SECTION_ORDER.get(agent, []),
    )
