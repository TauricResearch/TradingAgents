"""ModelBundle: wire the Phase 0 ModelRouting contract into the pipeline.

Until now a single llm object served all 59 evidence agents and every
pipeline stage (review finding MODEL-01). The bundle routes:
- evidence teams -> quick model (or a per-team override)
- debaters / sentiment -> quick model
- critic / reflection / judge -> deep model

A bare llm passed anywhere is auto-wrapped as a single-model bundle, so
tests and simple callers keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.contracts import AgentTeam, ProConfig


@dataclass
class ModelBundle:
    quick: object
    deep: object
    team_overrides: dict[AgentTeam, object] = field(default_factory=dict)

    def for_team(self, team: AgentTeam):
        return self.team_overrides.get(team, self.quick)

    @classmethod
    def single(cls, llm) -> ModelBundle:
        return cls(quick=llm, deep=llm)

    @classmethod
    def coerce(cls, llm_or_bundle) -> ModelBundle:
        if isinstance(llm_or_bundle, cls):
            return llm_or_bundle
        return cls.single(llm_or_bundle)


def bundle_from_config(
    config: ProConfig,
    quick_timeout: float = 60.0,
    deep_timeout: float = 180.0,
    **client_kwargs,
) -> ModelBundle:
    """Build a bundle from ProConfig.models via the base provider factory.

    Model IDs should be pinned, dated snapshots in production (SEC-02 /
    MODEL-01): a floating alias silently changes behavior with no eval gate.

    Per-tier request timeouts bound worst-case decision latency (eval
    finding: reasoning-class deep calls blocked 20+ minutes on an open
    socket; SDK default only breaks at 600 s). A timed-out call flows into
    the existing retry -> abstain path.
    """
    from tradingagents.llm_clients import create_llm_client

    routing = config.models

    def make(model_id: str, timeout: float):
        return create_llm_client(
            routing.llm_provider, model_id, timeout=timeout, **client_kwargs
        ).get_llm()

    quick = make(routing.quick_think_llm, quick_timeout)
    deep = quick if routing.deep_think_llm == routing.quick_think_llm else make(
        routing.deep_think_llm, deep_timeout
    )
    made: dict[str, object] = {routing.quick_think_llm: quick,
                               routing.deep_think_llm: deep}
    overrides = {}
    for team, model_id in routing.team_overrides.items():
        if model_id not in made:
            made[model_id] = make(model_id, quick_timeout)
        overrides[team] = made[model_id]
    return ModelBundle(quick=quick, deep=deep, team_overrides=overrides)
