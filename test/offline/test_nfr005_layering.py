"""SEL-TA-NFR-005 — Cohesive, compatible integration (structural).

Fit: interactive prompts live only under cli/; tradingagents/runapi,
tradingagents/agents and tradingagents/graph do not import terminal-prompt
modules. This keeps the shared boundary usable without a terminal.

Enforcing design: runapi/execution.py + cli/input_ui.py boundary (INV-10).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = {"questionary", "prompt_toolkit", "inquirer", "rich.prompt"}
PROMPT_SOURCES = [
    ROOT / "tradingagents" / "runapi",
    ROOT / "tradingagents" / "agents",
    ROOT / "tradingagents" / "graph",
]


def _prompt_imports(path: Path) -> set[str]:
    hits = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            for forbidden in FORBIDDEN:
                if name == forbidden or name.startswith(forbidden + "."):
                    hits.add(f"{path.relative_to(ROOT)}: {name}")
            if name == "rich":
                pass  # rich.console is fine; only rich.prompt is a prompt module
    return hits


# TC-NFR005-a: no terminal-prompt import in the shared boundary or engine layers.
def test_tc_nfr005_a_no_prompt_imports_outside_cli():
    offenders = []
    for directory in PROMPT_SOURCES:
        for path in directory.rglob("*.py"):
            offenders.extend(sorted(_prompt_imports(path)))
    assert offenders == []


# TC-NFR005-b: runapi does not import cli (dependency direction is one-way).
def test_tc_nfr005_b_runapi_does_not_import_cli():
    offenders = []
    for path in (ROOT / "tradingagents" / "runapi").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n == "cli" or n.startswith("cli.") for n in names):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
