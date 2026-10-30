"""Only the data layer imports vendor libraries.

Vendor calls belong in dataflows, where failures are raised as VendorError
subclasses; a call made elsewhere can report an outage as a fact about the market.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VENDOR_LIBRARIES = {"yfinance"}


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.unit
def test_vendor_libraries_are_imported_only_by_the_data_layer():
    data_layer = ROOT / "tradingagents" / "dataflows"
    offenders = sorted(
        str(path.relative_to(ROOT))
        for package in ("tradingagents", "cli")
        for path in (ROOT / package).rglob("*.py")
        if data_layer not in path.parents and _imports(path) & VENDOR_LIBRARIES
    )
    assert offenders == []
