"""Per-team LLM clients.

The desk's roles fall into five teams. By default every team shares one quick
and one deep client. ``config["team_llms"]`` lets a team run on its own API key,
endpoint, or models, so a gateway that bills by key can split spend by team:

    "team_llms": {
        "research": {"api_key_env": "RESEARCH_API_KEY", "deep_think_llm": "..."},
    }

``api_key_env`` names the environment variable holding the key, so the key
itself never sits in the config. Fields left out fall back to the top-level
config, and an unlisted team uses the shared default clients.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

# Team -> roles it covers. The reflector reviews the portfolio manager's
# decision, so it bills with the portfolio team.
TEAMS: dict[str, tuple[str, ...]] = {
    "analysts": ("market", "social", "news", "fundamentals"),
    "research": ("bull", "bear", "research_manager"),
    "trader": ("trader",),
    "risk": ("aggressive", "neutral", "conservative"),
    "portfolio": ("portfolio_manager", "reflector"),
}

TEAM_FIELDS = ("api_key_env", "backend_url", "quick_think_llm", "deep_think_llm")

TIERS = ("quick", "deep")


def _validate(team_llms: dict) -> None:
    unknown = sorted(set(team_llms) - set(TEAMS))
    if unknown:
        raise ValueError(
            f"Unknown team(s) in team_llms: {', '.join(unknown)}. "
            f"Valid teams: {', '.join(TEAMS)}."
        )
    for team, spec in team_llms.items():
        bad = sorted(set(spec) - set(TEAM_FIELDS))
        if bad:
            raise ValueError(
                f"Unknown field(s) for team '{team}' in team_llms: {', '.join(bad)}. "
                f"Valid fields: {', '.join(TEAM_FIELDS)}."
            )


def _team_api_key(team: str, env_name: str) -> str:
    key = os.environ.get(env_name)
    if not key:
        # Name the variable, never a value.
        raise ValueError(
            f"team_llms['{team}'] reads its API key from {env_name}, which is unset or empty."
        )
    return key


class TeamLLMs:
    """Resolves the LLM each team uses for each tier (quick or deep).

    Clients are built once per distinct (tier, model, endpoint, key), so teams
    that share a config share a client.
    """

    def __init__(
        self,
        config: dict[str, Any],
        default_quick: Any,
        default_deep: Any,
        make_llm: Callable[..., Any],
    ):
        team_llms = config.get("team_llms") or {}
        _validate(team_llms)
        self._defaults = {"quick": default_quick, "deep": default_deep}
        self._llms: dict[tuple[str, str], Any] = {}
        built: dict[tuple, Any] = {}

        for team, spec in team_llms.items():
            api_key = _team_api_key(team, spec["api_key_env"]) if spec.get("api_key_env") else None
            base_url = spec.get("backend_url") or config.get("backend_url")
            for tier in TIERS:
                model = spec.get(f"{tier}_think_llm") or config[f"{tier}_think_llm"]
                signature = (model, base_url, api_key)
                if signature not in built:
                    built[signature] = make_llm(model=model, base_url=base_url, api_key=api_key)
                self._llms[(team, tier)] = built[signature]

    def get(self, team: str, tier: str) -> Any:
        if team not in TEAMS:
            raise KeyError(f"Unknown team: {team}")
        if tier not in TIERS:
            raise KeyError(f"Unknown tier: {tier}")
        return self._llms.get((team, tier), self._defaults[tier])
