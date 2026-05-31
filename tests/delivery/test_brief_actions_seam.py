"""Boundary test (P7): no channel module calls F2, the classifier, or the
secretary directly. Channels only write brief_actions rows.

This catches an entire class of regression where someone takes a shortcut
and routes an accepted action straight from the channel into compose_*
or run_brief_scoped_backtest, defeating the action_handler seam.
"""

import ast
import pathlib
import pytest


_DELIVERY_DIR = pathlib.Path(__file__).resolve().parents[2] / "tradingagents" / "delivery"

_FORBIDDEN_IMPORTS = {
    "tradingagents.backtest",
    "tradingagents.backtest.runner",
    "tradingagents.secretary.service",
    "tradingagents.secretary.refinement",
    "tradingagents.secretary.morning",
}


def _imported_modules(py_path: pathlib.Path) -> set[str]:
    tree = ast.parse(py_path.read_text())
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                seen.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            seen.add(node.module)
    return seen


@pytest.mark.unit
def test_no_delivery_module_imports_forbidden_targets():
    offenders: dict[str, set[str]] = {}
    for py in _DELIVERY_DIR.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        imports = _imported_modules(py)
        bad = imports & _FORBIDDEN_IMPORTS
        if bad:
            offenders[str(py.relative_to(_DELIVERY_DIR))] = bad
    assert not offenders, (
        f"delivery modules must not import F2/secretary/classifier directly: {offenders}"
    )
