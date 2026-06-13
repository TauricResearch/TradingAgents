from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - exercised on Python 3.10
    tomllib = None  # type: ignore[assignment]


def _load_declared_dependencies() -> list[str]:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    content = pyproject_path.read_text(encoding="utf-8")

    if tomllib is not None:
        return tomllib.loads(content)["project"]["dependencies"]

    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if not match:
        return []
    return [dep.strip(" '\"") for dep in match.group(1).split(",") if dep.strip()]


def test_cli_direct_imports_are_declared_dependencies() -> None:
    declared = {re.split(r"[><=!~;]", item, maxsplit=1)[0].strip() for item in _load_declared_dependencies()}

    assert "questionary" in declared
    assert "python-dotenv" in declared
