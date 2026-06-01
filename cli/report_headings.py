"""Normalize heading levels inside ``complete_report.md``.

The CLI builder in ``cli/main.py`` wraps each agent's output with fixed
wrapper headings:

- ``# Trading Analysis Report: <TICKER>``      (H1, page title)
- ``## I. Analyst Team Reports`` …             (H2, section)
- ``### Market Analyst`` …                     (H3, agent)

Inside each agent body the LLM frequently emits its own ``# Title``,
``## Section``, and ``### Subsection`` lines. Body H1/H2 obviously
collide with the page H1 and the section H2; less obviously, body H3
visually escapes its agent wrapper because both are H3 (``### Trend …``
becomes a sibling of ``### Market Analyst``), shattering the outline.

This module demotes any heading inside an agent body to H4 (``####``).
Wrapper headings — the page H1, the ``## I.`` section H2s, and the
known agent H3s — are preserved. H4+ inside a body is left alone.

Idempotent: a second run is a no-op because no body H1/H2/H3 remains.

This lives in the ``cli`` package (not ``scripts/``) so it ships with
the installed wheel and is importable in the Docker/site-packages layout,
where ``save_report_to_disk`` needs it.
"""
from __future__ import annotations

import re

# H2 wrappers always start with a roman-numeral marker (``## I. …``).
WRAPPER_H2 = re.compile(r"^## [IVX]+\. ")

# H3 wrappers are the fixed agent labels emitted by ``cli/main.py``'s
# ``save_report_to_disk``. Anything else at H3 inside a body region is
# treated as agent-emitted content and demoted.
WRAPPER_H3_LABELS = frozenset({
    "Market Analyst",
    "Sentiment Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Conservative Analyst",
    "Neutral Analyst",
    "Portfolio Manager",
})

HEADING = re.compile(r"^(#{1,6}) (.*?)\s*$")


def _is_wrapper_h3(text: str) -> bool:
    return text.strip() in WRAPPER_H3_LABELS


def transform(text: str) -> str:
    """Demote agent-body H1/H2/H3 to H4. Preserve wrapper headings and code fences."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_body = False
    in_fence = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        m = HEADING.match(line)
        if not m:
            out.append(line)
            continue

        level = len(m.group(1))
        title = m.group(2)
        newline = "\n" if line.endswith("\n") else ""

        if level == 1:
            # Page title (or stray body H1). H1 outside any agent body is
            # the page title and stays. Body H1 gets demoted.
            if in_body:
                out.append(f"#### {title}{newline}")
            else:
                out.append(line)
            continue

        if level == 2:
            if WRAPPER_H2.match(line):
                in_body = False
                out.append(line)
            else:
                # Stray body H2 (or a stray top-level H2 before any body).
                # Demote either way to keep the outline monotonic.
                out.append(f"#### {title}{newline}")
            continue

        if level == 3:
            if _is_wrapper_h3(title):
                in_body = True
                out.append(line)
            else:
                # Agent body H3. Demote.
                out.append(f"#### {title}{newline}")
            continue

        # H4, H5, H6: leave alone.
        out.append(line)

    return "".join(out)
