"""Expandable report section component.

Each report section (Market, News, etc.) is rendered as a Quasar
expansion item that opens when its content first arrives.
"""

from __future__ import annotations

from nicegui import ui

from tradingagents.progress import SECTION_TITLES, ProgressSnapshot


class ReportSectionsPanel:
    """Accordion of report sections that fill in as the pipeline runs.

    Call ``update(snapshot)`` from the UI timer.
    """

    def __init__(self) -> None:
        self._sections: dict[str, _ReportSection] = {}
        self._container: ui.column | None = None

    def build(self, section_keys: list[str]) -> None:
        """Render empty expansion items for each expected section."""
        self._container = ui.column().classes("w-full gap-xs")
        with self._container:
            for key in section_keys:
                title = SECTION_TITLES.get(key, key)
                section = _ReportSection(key, title)
                section.build()
                self._sections[key] = section

    def update(self, snap: ProgressSnapshot) -> None:
        """Refresh content from a snapshot."""
        for key, section in self._sections.items():
            content = snap.report_sections.get(key)
            section.update(content)


class _ReportSection:
    """Single expandable report section."""

    def __init__(self, key: str, title: str) -> None:
        self.key = key
        self.title = title
        self._expansion: ui.expansion | None = None
        self._content_area: ui.html | None = None
        self._has_opened = False
        self._last_content: str | None = None

    def build(self) -> None:
        self._expansion = ui.expansion(
            f"{self.title}",
            icon="description",
        ).classes("w-full report-section bg-dark").props(
            "dense header-class='text-subtitle2 text-grey-4'"
        )
        with self._expansion:
            self._content_area = ui.html("").classes("text-body2 text-white")

    def update(self, content: str | None) -> None:
        if content is None:
            return
        if content == self._last_content:
            return

        self._last_content = content
        if self._content_area:
            # Render markdown as HTML via NiceGUI's markdown
            self._content_area.content = f"<pre style='white-space:pre-wrap;font-family:inherit'>{_escape_html(content)}</pre>"

        # Auto-open on first content
        if not self._has_opened and self._expansion:
            self._expansion.open()
            self._has_opened = True


def _escape_html(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
