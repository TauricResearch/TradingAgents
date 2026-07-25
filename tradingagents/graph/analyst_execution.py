from collections.abc import Iterable
from dataclasses import dataclass
from time import monotonic

from tradingagents.analysts import ANALYST_BY_KEY, ANALYST_CONFIG, AnalystDefinition


@dataclass(frozen=True)
class AnalystNodeSpec:
    key: str
    factory_key: str
    agent_node: str
    clear_node: str
    tool_node: str
    report_key: str


@dataclass(frozen=True)
class AnalystExecutionPlan:
    specs: list[AnalystNodeSpec]


def _to_node_spec(definition: AnalystDefinition) -> AnalystNodeSpec:
    return AnalystNodeSpec(
        key=definition.key,
        factory_key=definition.factory_key,
        agent_node=definition.node_id,
        clear_node=definition.clear_node_id,
        tool_node=definition.tool_node_id,
        report_key=definition.report_key,
    )


# Kept as a mapping for existing consumers.  It is mechanically derived from
# ANALYST_CONFIG rather than a second handwritten role registry.
ANALYST_NODE_SPECS: dict[str, AnalystNodeSpec] = {
    definition.key: _to_node_spec(definition) for definition in ANALYST_CONFIG
}


def build_analyst_execution_plan(
    selected_analysts: Iterable[str],
) -> AnalystExecutionPlan:
    specs: list[AnalystNodeSpec] = []
    for analyst_key in selected_analysts:
        definition = ANALYST_BY_KEY.get(analyst_key)
        if definition is None:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        spec = ANALYST_NODE_SPECS[definition.key]
        specs.append(spec)

    if not specs:
        raise ValueError("at least one analyst must be selected")

    return AnalystExecutionPlan(specs=specs)


def get_initial_analyst_node(plan: AnalystExecutionPlan) -> str:
    return plan.specs[0].agent_node


class AnalystWallTimeTracker:
    def __init__(self, plan: AnalystExecutionPlan):
        self.plan = plan
        self._started_at: dict[str, float] = {}
        self._wall_times: dict[str, float] = {}

    def mark_started(self, analyst_key: str, started_at: float | None = None) -> None:
        if analyst_key not in ANALYST_NODE_SPECS:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        self._started_at.setdefault(analyst_key, monotonic() if started_at is None else started_at)

    def mark_completed(
        self,
        analyst_key: str,
        completed_at: float | None = None,
    ) -> None:
        if analyst_key not in ANALYST_NODE_SPECS:
            raise ValueError(f"unknown analyst key: {analyst_key}")
        if analyst_key in self._wall_times:
            return
        started_at = self._started_at.get(analyst_key)
        if started_at is None:
            return
        finished_at = monotonic() if completed_at is None else completed_at
        self._wall_times[analyst_key] = max(0.0, finished_at - started_at)

    def get_wall_times(self) -> dict[str, float]:
        return dict(self._wall_times)

    def format_summary(self) -> str:
        parts = []
        for spec in self.plan.specs:
            duration = self._wall_times.get(spec.key)
            if duration is not None:
                label = spec.agent_node.removesuffix(" Analyst")
                parts.append(f"{label} {duration:.2f}s")
        if not parts:
            return "Analyst wall time: pending"
        return "Analyst wall time: " + " | ".join(parts)


def sync_analyst_tracker_from_chunk(
    tracker: AnalystWallTimeTracker,
    chunk: dict[str, str],
    now: float | None = None,
) -> None:
    current_time = monotonic() if now is None else now
    active_found = False

    for spec in tracker.plan.specs:
        has_report = bool(chunk.get(spec.report_key))

        if has_report:
            tracker.mark_started(spec.key, started_at=current_time)
            tracker.mark_completed(spec.key, completed_at=current_time)
            continue

        if not active_found:
            tracker.mark_started(spec.key, started_at=current_time)
            active_found = True
