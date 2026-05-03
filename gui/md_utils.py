"""Markdown rendering helpers for the Streamlit UI.

Streamlit's ``st.markdown`` runs the text through KaTeX, so any ``$...$``
pair is interpreted as inline math. Financial reports are full of price
strings (``$198``, ``$45,203``, ``$96.68B``) and two of them on the same
block silently mangles everything between them into italicized math.

We escape ``$`` to ``\\$`` only for display in Streamlit. Export files
(.md / .html / .pdf) go through python-markdown / xhtml2pdf which don't
treat ``$`` specially, so the export side leaves the source untouched —
otherwise ``\\$`` would leak into copy-pasted text.
"""

from __future__ import annotations

import re

# Match a single ``$`` that is NOT already escaped (preceded by a backslash).
# Lookbehind avoids double-escaping if the agent ever does emit literal ``\$``.
_BARE_DOLLAR = re.compile(r"(?<!\\)\$")


def safe_md(text: str | None) -> str:
    """Escape ``$`` in ``text`` so Streamlit doesn't render it as KaTeX math."""
    if not text:
        return ""
    return _BARE_DOLLAR.sub(r"\\$", text)
