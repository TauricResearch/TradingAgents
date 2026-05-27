import pytest
from pathlib import Path


@pytest.mark.unit
def test_sweep_service_runs_cli_subcommand():
    p = Path("ops/systemd/iic-watchlist-sweep.service")
    assert p.exists()
    text = p.read_text()
    assert "Type=oneshot" in text
    assert "forge sense sweep-watchlist" in text


@pytest.mark.unit
def test_sweep_timer_hourly():
    p = Path("ops/systemd/iic-watchlist-sweep.timer")
    assert p.exists()
    text = p.read_text()
    assert "OnCalendar=hourly" in text
    assert "Persistent=true" in text
