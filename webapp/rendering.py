"""Markdown rendering for the web console's report panel.

The agents write CommonMark, which the terminal renders with ``rich`` and the
saved HTML report renders with ``markdown-it``. The page needs the same, so this
module renders it with the same library and the same safe configuration
``tradingagents.report_html`` uses: raw HTML is escaped and images are off, so
nothing a model wrote can inject markup or load a remote asset. That is what
makes the result safe to place in the page with ``innerHTML``.

Rendering is cached by text: a run's sections are re-read on every poll, and the
same text must not be parsed again.
"""

from __future__ import annotations

import threading
from functools import lru_cache

from markdown_it import MarkdownIt

# One renderer for the process. Its rules are read-only during a render, but the
# instance is shared across request threads, so rendering is serialised: a
# report's sections are small and the parsed result is cached anyway.
_RENDER_LOCK = threading.Lock()


def _markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False, "linkify": False})
    md.enable("table").disable("image")
    # A wide table scrolls inside the panel instead of stretching the page.
    md.add_render_rule("table_open", lambda *a: '<div class="table-wrap"><table>\n')
    md.add_render_rule("table_close", lambda *a: "</table></div>\n")
    return md


_MD = _markdown()


def _demote_headings(tokens) -> None:
    """Drop the text's own headings two levels, so they sit under the section label.

    Each section shows the agent's name as an ``h3``; an agent's report typically
    opens with ``## Market Analysis``, which as written would outrank it.
    """
    for token in tokens:
        if token.type in ("heading_open", "heading_close"):
            token.tag = f"h{min(int(token.tag[1]) + 2, 6)}"


@lru_cache(maxsize=1024)
def _render_cached(text: str) -> str:
    tokens = _MD.parse(text)
    _demote_headings(tokens)
    return _MD.renderer.render(tokens, _MD.options, {})


def render_markdown(text: str) -> str:
    """Markdown as safe HTML: raw HTML escaped, images and unsafe links inert."""
    if not text:
        return ""
    with _RENDER_LOCK:
        return _render_cached(str(text))
