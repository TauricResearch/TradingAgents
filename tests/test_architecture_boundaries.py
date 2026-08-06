"""Ratcheting import rules for newly extracted architectural packages."""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "tradingagents"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                names.add("<relative-import>")
            elif node.module:
                names.add(node.module)
    return names


@pytest.mark.unit
def test_domain_imports_only_domain_stdlib_and_validation_library():
    allowed_external = {"pydantic", "typing_extensions"}
    violations = []
    for path in sorted((PACKAGE / "domain").rglob("*.py")):
        for name in _imports(path):
            root = name.split(".", 1)[0]
            if name == "tradingagents.domain" or name.startswith("tradingagents.domain."):
                continue
            if root in sys.stdlib_module_names or root in allowed_external or root == "__future__":
                continue
            violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not violations, "\n".join(violations)


@pytest.mark.unit
def test_ports_import_only_domain_ports_and_stdlib():
    violations = []
    for path in sorted((PACKAGE / "ports").rglob("*.py")):
        for name in _imports(path):
            root = name.split(".", 1)[0]
            if name in {"tradingagents.domain", "tradingagents.ports"} or name.startswith(
                ("tradingagents.domain.", "tradingagents.ports.")
            ):
                continue
            if root in sys.stdlib_module_names or root == "__future__":
                continue
            violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert not violations, "\n".join(violations)
