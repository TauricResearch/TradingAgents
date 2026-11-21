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

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN = {"questionary", "prompt_toolkit", "inquirer", "rich.prompt", "typer"}
PROMPT_SOURCES = [
    ROOT / "tradingagents" / "runapi",
    ROOT / "tradingagents" / "agents",
    ROOT / "tradingagents" / "graph",
]


def _prompt_imports(path: Path) -> set[str]:
    hits = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input":
            hits.add(f"{path}: input")
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
        for name in names:
            for forbidden in FORBIDDEN:
                if name == forbidden or name.startswith(forbidden + "."):
                    hits.add(f"{path}: {name}")
            if name == "rich":
                pass  # rich.console is fine; only rich.prompt is a prompt module
    return hits


# TC-NFR005-a: no terminal-prompt import in the shared boundary or engine layers.
def test_tc_nfr005_a_no_prompt_imports_outside_cli():
    offenders = []
    for directory in PROMPT_SOURCES:
        assert directory.is_dir(), f"Missing source directory: {directory}"
        paths = list(directory.rglob("*.py"))
        assert paths, f"Empty source scan: {directory}"
        for path in paths:
            offenders.extend(sorted(_prompt_imports(path)))
    assert offenders == []


# TC-NFR005-b: runapi does not import cli (dependency direction is one-way).
def test_tc_nfr005_b_runapi_does_not_import_cli():
    offenders = []
    paths = list((ROOT / "tradingagents" / "runapi").rglob("*.py"))
    assert paths, "No runapi source files scanned"
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{alias.name}" for alias in node.names]
            if any(n == "cli" or n.startswith("cli.") for n in names):
                offenders.append(str(path))
    assert offenders == []


@pytest.mark.parametrize("source", ["import questionary", "from rich import prompt", "import typer", "input('pick')"])
def test_forbidden_prompt_fixture(tmp_path, source):
    path = tmp_path / "forbidden.py"
    path.write_text(source, encoding="utf-8")
    assert _prompt_imports(path)
