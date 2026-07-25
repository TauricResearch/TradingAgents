"""Single metadata registry for the analyst roles that users may select.

The graph has thirteen roles, but only these four are configurable in preset
v1.  Everything after the analyst phase is deliberately a fixed convergence
path; keeping that distinction in one module prevents a UI/configuration
change from accidentally making a decision-stage role optional.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalystDefinition:
    """Stable metadata for one existing analyst implementation.

    ``factory_key`` is intentionally a symbolic reference, not a YAML-imported
    callable.  Factories remain code-owned and allow-listed in ``GraphSetup``;
    presets can only choose and order the keys defined here.
    """

    key: str
    order: int
    actor_id: str
    node_id: str
    display_name: str
    description: str
    investing_style: str
    factory_key: str
    clear_node_id: str
    tool_node_id: str
    report_key: str
    icon_id: str
    # Matches the code-owned methodology role.  YAML may select this analyst
    # but cannot replace its skill pool or inject arbitrary skill text.
    skill_role: str

    def as_api_option(self) -> dict[str, object]:
        """Return safe, non-executable metadata for ``GET /api/config``."""
        return {
            "id": self.key,
            "display_name": self.display_name,
            "description": self.description,
            "investing_style": self.investing_style,
            "order": self.order,
        }


# This is the only registry for selectable analyst metadata.  Keep keys stable:
# saved runs and YAML presets persist these wire identifiers.
ANALYST_CONFIG: tuple[AnalystDefinition, ...] = (
    AnalystDefinition(
        key="market",
        order=10,
        actor_id="analyst.market",
        node_id="Market Analyst",
        display_name="Market Analyst",
        description="Reads price action, technical indicators, and market structure.",
        investing_style="technical and market-structure",
        factory_key="market",
        clear_node_id="Msg Clear Market",
        tool_node_id="tools_market",
        report_key="market_report",
        icon_id="chart-bars",
        skill_role="market_analyst",
    ),
    AnalystDefinition(
        # ``social`` is retained as a wire key for saved-run compatibility;
        # its display name reflects the broader Sentiment Analyst remit.
        key="social",
        order=20,
        actor_id="analyst.sentiment",
        node_id="Sentiment Analyst",
        display_name="Sentiment Analyst",
        description="Assesses news, StockTwits, and Reddit sentiment.",
        investing_style="sentiment and attention",
        factory_key="social",
        clear_node_id="Msg Clear Sentiment",
        tool_node_id="tools_social",
        report_key="sentiment_report",
        icon_id="speech-pulse",
        skill_role="sentiment_analyst",
    ),
    AnalystDefinition(
        key="news",
        order=30,
        actor_id="analyst.news",
        node_id="News Analyst",
        display_name="News Analyst",
        description="Interprets material news and catalysts for the instrument.",
        investing_style="event-driven",
        factory_key="news",
        clear_node_id="Msg Clear News",
        tool_node_id="tools_news",
        report_key="news_report",
        icon_id="newspaper",
        skill_role="news_analyst",
    ),
    AnalystDefinition(
        key="fundamentals",
        order=40,
        actor_id="analyst.fundamentals",
        node_id="Fundamentals Analyst",
        display_name="Fundamentals Analyst",
        description="Evaluates financial statements, valuation, and business quality.",
        investing_style="fundamental",
        factory_key="fundamentals",
        clear_node_id="Msg Clear Fundamentals",
        tool_node_id="tools_fundamentals",
        report_key="fundamentals_report",
        icon_id="institution-columns",
        skill_role="fundamentals_analyst",
    ),
)

ANALYST_BY_KEY = {definition.key: definition for definition in ANALYST_CONFIG}
ANALYST_WIRE_KEYS = tuple(definition.key for definition in ANALYST_CONFIG)

# These roles are not preset options.  This named invariant is used by preset
# inspection and documents the fixed analyst -> conclusion convergence path.
MANDATORY_CONVERGENCE_NODE_IDS = (
    "Evidence Steward",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Neutral Analyst",
    "Conservative Analyst",
    "Portfolio Manager",
)


def analyst_definition(key: str) -> AnalystDefinition:
    """Return an existing selectable role or fail before graph construction."""
    try:
        return ANALYST_BY_KEY[key]
    except KeyError as exc:
        raise ValueError(f"unknown analyst key: {key}") from exc
