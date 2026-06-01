"""Demote stray H1/H2 headings inside LLM-generated sections of complete_report.md.

The CLI builder in ``cli/main.py`` wraps each agent's output with fixed
wrapper headings (``## I. Analyst Team Reports`` … ``### Market Analyst`` …).
Inside those wrappers, the LLM frequently emits its own ``# Title`` and
``## Section`` lines, producing multiple H1s per page and a scrambled
heading hierarchy.

Inside each LLM body region this script demotes ``#`` to ``####`` and
``##`` to ``####``, leaving H3+ alone. Idempotent: rerunning is a no-op
because no body H1/H2 remains after the first pass.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

WRAPPER_H2 = re.compile(r"^## [IVX]+\. ")
WRAPPER_H3 = re.compile(r"^### \S")
HEADING = re.compile(r"^(#{1,6}) (.*)$")


def demote(line: str) -> str:
    m = HEADING.match(line)
    if not m:
        return line
    level = len(m.group(1))
    if level > 2:
        return line
    return f"{'#' * 4} {m.group(2)}\n"


def transform(text: str) -> str:
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

        if WRAPPER_H2.match(line):
            in_body = False
            out.append(line)
            continue
        if WRAPPER_H3.match(line):
            in_body = True
            out.append(line)
            continue
        if in_body:
            out.append(demote(line))
        else:
            out.append(line)
    return "".join(out)


def main() -> int:
    targets = sorted(DOCS.glob("*/*/complete_report.md"))
    changed = 0
    for path in targets:
        original = path.read_text(encoding="utf-8")
        updated = transform(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"Processed {len(targets)} reports; rewrote {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
