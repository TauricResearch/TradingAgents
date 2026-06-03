import pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_morning_timer_fires_at_0600():
    txt = (REPO / "ops/systemd/iic-morning.timer").read_text()
    assert "OnCalendar=*-*-* 06:00:00" in txt
    assert "07:00:00" not in txt
