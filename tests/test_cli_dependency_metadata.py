from __future__ import annotations

import tomllib
from pathlib import Path


def test_cli_direct_imports_are_declared_dependencies() -> None:
    deps = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))['project']['dependencies']
    declared = {item.split('>=')[0].split('==')[0] for item in deps}

    assert 'questionary' in declared
    assert 'python-dotenv' in declared
