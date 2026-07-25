"""Language-independent role registry for the complete TradingAgents graph."""

from __future__ import annotations

from dataclasses import dataclass

from tradingagents.analysts import ANALYST_CONFIG


@dataclass(frozen=True)
class RoleDefinition:
    actor_id: str
    node_id: str
    team_id: str
    display_name: str
    icon_id: str
    analyst_key: str | None = None


ROLE_REGISTRY: tuple[RoleDefinition, ...] = (
    *(
        RoleDefinition(
            definition.actor_id,
            definition.node_id,
            "analysts",
            definition.display_name,
            definition.icon_id,
            definition.key,
        )
        for definition in ANALYST_CONFIG
    ),
    RoleDefinition(
        "evidence.steward",
        "Evidence Steward",
        "evidence",
        "Evidence Steward",
        "verified-magnifier",
    ),
    RoleDefinition(
        "researcher.bull",
        "Bull Researcher",
        "research",
        "Bull Researcher",
        "rising-horn",
    ),
    RoleDefinition(
        "researcher.bear",
        "Bear Researcher",
        "research",
        "Bear Researcher",
        "falling-paw",
    ),
    RoleDefinition(
        "manager.research",
        "Research Manager",
        "research",
        "Research Manager",
        "scales",
    ),
    RoleDefinition(
        "trader",
        "Trader",
        "trading",
        "Trader",
        "opposing-arrows",
    ),
    RoleDefinition(
        "risk.aggressive",
        "Aggressive Analyst",
        "risk",
        "Aggressive Risk Analyst",
        "lightning",
    ),
    RoleDefinition(
        "risk.neutral",
        "Neutral Analyst",
        "risk",
        "Neutral Risk Analyst",
        "centered-crosshair",
    ),
    RoleDefinition(
        "risk.conservative",
        "Conservative Analyst",
        "risk",
        "Conservative Risk Analyst",
        "shield",
    ),
    RoleDefinition(
        "manager.portfolio",
        "Portfolio Manager",
        "portfolio",
        "Portfolio Manager",
        "portfolio-compass",
    ),
)

ROLES_BY_ACTOR_ID = {role.actor_id: role for role in ROLE_REGISTRY}
ROLES_BY_NODE_ID = {role.node_id: role for role in ROLE_REGISTRY}


def role_instance_id(run_id: str, actor_id: str) -> str:
    if actor_id not in ROLES_BY_ACTOR_ID:
        raise KeyError(f"unknown TradingAgents actor_id: {actor_id}")
    if not run_id:
        raise ValueError("run_id is required")
    return f"{run_id}:{actor_id}"
