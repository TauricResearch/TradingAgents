from tradingagents.paper import discovery


def test_discovery_console_entry_exists():
    from pathlib import Path
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert 'koral-equities-discover = "tradingagents.paper.discovery:main"' in pyproject.read_text()
    assert callable(discovery.main)
