from datetime import time
import pytest


@pytest.mark.unit
def test_quiet_hours_overnight_wrap_includes_midnight():
    from tradingagents.delivery.quiet_hours import is_quiet_hours
    cfg = {"enabled": True, "start": "22:00", "end": "07:00"}
    assert is_quiet_hours(local_time=time(23, 30), config=cfg) is True
    assert is_quiet_hours(local_time=time(2, 0), config=cfg) is True
    assert is_quiet_hours(local_time=time(6, 59), config=cfg) is True


@pytest.mark.unit
def test_quiet_hours_excludes_morning_and_day():
    from tradingagents.delivery.quiet_hours import is_quiet_hours
    cfg = {"enabled": True, "start": "22:00", "end": "07:00"}
    assert is_quiet_hours(local_time=time(7, 0), config=cfg) is False
    assert is_quiet_hours(local_time=time(12, 0), config=cfg) is False
    assert is_quiet_hours(local_time=time(21, 59), config=cfg) is False


@pytest.mark.unit
def test_quiet_hours_disabled_always_false():
    from tradingagents.delivery.quiet_hours import is_quiet_hours
    cfg = {"enabled": False, "start": "22:00", "end": "07:00"}
    assert is_quiet_hours(local_time=time(2, 0), config=cfg) is False


@pytest.mark.unit
def test_quiet_hours_non_wrap_window():
    from tradingagents.delivery.quiet_hours import is_quiet_hours
    cfg = {"enabled": True, "start": "13:00", "end": "14:00"}
    assert is_quiet_hours(local_time=time(13, 30), config=cfg) is True
    assert is_quiet_hours(local_time=time(14, 1), config=cfg) is False
