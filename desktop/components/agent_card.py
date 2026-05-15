"""Agent status cards grouped by team.

Renders a vertical list of team sections, each containing agent cards
with status indicators (pending / in_progress / completed / error).
"""

from __future__ import annotations

from nicegui import ui

from tradingagents.progress import FIXED_AGENTS, ProgressSnapshot

# Display order: Analyst Team first, then pipeline order
_TEAM_ORDER = [
    ("Analyst Team", [
        "Market Analyst", "Sentiment Analyst", "News Analyst", "Fundamentals Analyst",
    ]),
    ("Research Team", FIXED_AGENTS["Research Team"]),
    ("Trading Team", FIXED_AGENTS["Trading Team"]),
    ("Risk Management", FIXED_AGENTS["Risk Management"]),
    ("Portfolio Management", FIXED_AGENTS["Portfolio Management"]),
]

_STATUS_ICONS: dict[str, tuple[str, str]] = {
    "pending": ("hourglass_empty", "grey"),
    "in_progress": ("sync", "blue"),
    "completed": ("check_circle", "green"),
    "error": ("error", "red"),
}


class AgentStatusPanel:
    """Reactive panel showing all agent statuses grouped by team.

    Call ``update(snapshot)`` from the UI timer to refresh.
    """

    def __init__(self) -> None:
        self._container: ui.column | None = None
        self._cards: dict[str, _AgentCard] = {}
        self._team_badges: dict[str, ui.label] = {}

    def build(self) -> None:
        """Render the initial layout (call once during page setup)."""
        self._container = ui.column().classes("w-full gap-sm")
        with self._container:
            for team_name, agents in _TEAM_ORDER:
                with ui.expansion(team_name, icon="groups").classes(
                    "w-full bg-dark"
                ).props("dense default-opened header-class='text-subtitle2 text-white'"):
                    badge = ui.label("").classes("text-caption text-grey-5")
                    self._team_badges[team_name] = badge
                    for agent_name in agents:
                        card = _AgentCard(agent_name)
                        card.build()
                        self._cards[agent_name] = card

    def update(self, snap: ProgressSnapshot) -> None:
        """Refresh all cards from a snapshot."""
        for agent_name, card in self._cards.items():
            status = snap.agent_status.get(agent_name)
            if status is not None:
                card.update(status)
                card.show()
            else:
                card.hide()

        # Update team badges
        for team_name, agents in _TEAM_ORDER:
            active = [a for a in agents if a in snap.agent_status]
            if not active:
                self._team_badges[team_name].set_text("")
                continue
            done = sum(1 for a in active if snap.agent_status.get(a) == "completed")
            self._team_badges[team_name].set_text(f"{done}/{len(active)} done")


class _AgentCard:
    """Single agent status card with icon + name + status label."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._row: ui.row | None = None
        self._icon: ui.icon | None = None
        self._status_label: ui.label | None = None

    def build(self) -> None:
        self._row = ui.row().classes("agent-card pending items-center q-pa-xs q-ml-md w-full")
        with self._row:
            self._icon = ui.icon("hourglass_empty").classes("text-grey")
            ui.label(self.name).classes("text-body2 q-ml-xs")
            ui.space()
            self._status_label = ui.label("pending").classes("text-caption text-grey")

    def update(self, status: str) -> None:
        icon_name, color = _STATUS_ICONS.get(status, ("help", "grey"))
        if self._icon:
            self._icon._props["name"] = icon_name
            self._icon.classes(replace=f"text-{color}")
            self._icon.update()
        if self._status_label:
            self._status_label.set_text(status.replace("_", " "))
            self._status_label.classes(replace=f"text-caption text-{color}")
        if self._row:
            # Update border class
            for s in ("pending", "in_progress", "completed", "error"):
                self._row.classes(remove=s)
            self._row.classes(add=status)

    def show(self) -> None:
        if self._row:
            self._row.set_visibility(True)

    def hide(self) -> None:
        if self._row:
            self._row.set_visibility(False)
