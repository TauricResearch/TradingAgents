import pytest
from pathlib import Path


_SENSE_UNITS = [
    "iic-sense-polygon", "iic-sense-telegram", "iic-sense-x",
    "iic-sense-rss", "iic-sense-gdelt", "iic-sense-macro",
]


@pytest.mark.unit
@pytest.mark.parametrize("name", _SENSE_UNITS)
def test_sense_unit_files_exist(name):
    p = Path(f"ops/systemd/{name}.service")
    assert p.exists(), f"missing {p}"
    text = p.read_text()
    assert "Requires=redis-server.service" in text
    assert "After=network-online.target redis-server.service" in text
    assert "Restart=on-failure" in text
    assert "RestartSec=30" in text
    assert "MemoryMax=512M" in text
    assert "CPUQuota=50%" in text
    assert "tradingagents.sensing.adapters" in text


@pytest.mark.unit
def test_triage_unit_file():
    p = Path("ops/systemd/iic-triage.service")
    assert p.exists()
    text = p.read_text()
    assert "Requires=redis-server.service" in text
    assert "tradingagents.sensing.triage" in text
    assert "MemoryMax=" in text


@pytest.mark.unit
@pytest.mark.parametrize("name", _SENSE_UNITS + ["iic-triage"])
def test_unit_files_reference_env_file(name):
    """Every service must read .env so creds are available without exposing them in unit files."""
    p = Path(f"ops/systemd/{name}.service")
    text = p.read_text()
    assert "EnvironmentFile=" in text
