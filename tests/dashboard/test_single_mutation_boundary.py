"""Boundary test (P7): only tradingagents/dashboard/action_form.py performs
SQLite writes within the dashboard package. Panels are read-only."""

import ast
import pathlib
import pytest


_DASH_DIR = pathlib.Path(__file__).resolve().parents[2] / "tradingagents" / "dashboard"

_WRITE_CALLS = {"insert_brief_action", "insert_brief", "insert_delivery",
                "update_action_state", "mark_action_done",
                "expire_lapsed_actions", "update_brief_refine_metadata"}


def _calls_write_helpers(py_path: pathlib.Path) -> set[str]:
    tree = ast.parse(py_path.read_text())
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            attr = getattr(node.func, "attr", None)
            name = getattr(node.func, "id", None)
            for candidate in (attr, name):
                if candidate in _WRITE_CALLS:
                    seen.add(candidate)
    return seen


def _has_sql_mutation(py_path: pathlib.Path) -> bool:
    """Detect raw INSERT/UPDATE/DELETE/REPLACE SQL strings."""
    src = py_path.read_text().upper()
    return any(kw in src for kw in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE "))


@pytest.mark.unit
def test_only_action_form_mutates_state():
    offenders: dict[str, set[str]] = {}
    for py in _DASH_DIR.rglob("*.py"):
        if py.name in ("__init__.py", "action_form.py"):
            continue
        bad_calls = _calls_write_helpers(py)
        if bad_calls or _has_sql_mutation(py):
            label = set(bad_calls) | ({"raw SQL"} if _has_sql_mutation(py) else set())
            offenders[str(py.relative_to(_DASH_DIR))] = label
    assert not offenders, (
        f"only dashboard/action_form.py may mutate state; offenders: {offenders}"
    )
