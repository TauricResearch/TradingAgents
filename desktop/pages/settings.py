"""Settings page — user preferences stored in SQLite.

See also: PLAN-desktop.md, F5.
"""

from __future__ import annotations

from nicegui import ui

from desktop.state.database import HistoryDB

_DEFAULT_SETTINGS = {
    "default_provider": "claude_cli",
    "default_analysts": "market,social,news,fundamentals",
    "research_depth": "1",
    "watchdog_timeout": "1200",
}


def render_settings_page(*, db: HistoryDB) -> None:
    """Render the settings page content."""
    page = _SettingsPage(db=db)
    page.build()


class _SettingsPage:
    def __init__(self, *, db: HistoryDB) -> None:
        self._db = db

    def build(self) -> None:
        settings = {**_DEFAULT_SETTINGS, **self._db.get_all_settings()}

        with ui.column().classes("w-full max-w-xl mx-auto q-pa-md gap-md"):
            ui.label("Settings").classes("text-h5 text-white")
            ui.label("Default values for new analyses.").classes(
                "text-body2 text-grey-5"
            )

            with ui.card().classes("w-full"):
                # Default provider
                provider_input = ui.select(
                    label="Default Provider",
                    options=[
                        "claude_cli", "openai", "google", "anthropic",
                        "xai", "deepseek", "ollama", "openrouter",
                    ],
                    value=settings.get("default_provider", "claude_cli"),
                ).classes("w-full").props("outlined dense")

                # Default analysts
                ui.label("Default Analysts").classes("text-subtitle2 q-mt-md")
                current_analysts = settings.get("default_analysts", "").split(",")
                analyst_checks: dict[str, ui.checkbox] = {}
                with ui.row().classes("gap-md"):
                    for key in ["market", "social", "news", "fundamentals"]:
                        cb = ui.checkbox(key.capitalize(), value=key in current_analysts)
                        analyst_checks[key] = cb

                # Research depth
                depth_slider = ui.slider(
                    min=1, max=3, step=1,
                    value=int(settings.get("research_depth", "1")),
                ).classes("w-full q-mt-md").props("label-always markers snap")
                ui.label("Research Depth").classes("text-subtitle2")

                # Watchdog timeout
                watchdog_input = ui.number(
                    "Watchdog Timeout (seconds)",
                    value=int(settings.get("watchdog_timeout", "1200")),
                    min=60, max=1800, step=30,
                ).classes("w-full q-mt-md").props("outlined dense")

            # Save button
            async def save() -> None:
                self._db.set_setting("default_provider", provider_input.value or "claude_cli")

                selected = [k for k, cb in analyst_checks.items() if cb.value]
                self._db.set_setting("default_analysts", ",".join(selected))

                self._db.set_setting("research_depth", str(int(depth_slider.value)))
                self._db.set_setting("watchdog_timeout", str(int(watchdog_input.value or 1200)))

                ui.notify("Settings saved!", type="positive")

            ui.button("Save Settings", icon="save", on_click=save).classes(
                "w-full q-mt-md"
            ).props("color=green")
