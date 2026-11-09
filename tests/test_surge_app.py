import socket
from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("exchange_calendars")
pytest.importorskip("plotly")

from streamlit.testing.v1 import AppTest

from tradingagents.dataflows.vendors.eodhd import DailySnapshot, EODHDError

_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_SOCKETPAIR = socket.socketpair


@pytest.fixture
def local_socketpair(monkeypatch):
    """Windows asyncio uses a loopback pair; keep all application network blocked."""

    def socketpair(*args, **kwargs):
        with monkeypatch.context() as scoped:
            scoped.setattr(socket.socket, "connect", _ORIGINAL_CONNECT)
            return _ORIGINAL_SOCKETPAIR(*args, **kwargs)

    monkeypatch.setattr(socket, "socketpair", socketpair)


def test_app_initial_scan_replay_and_failed_refresh(monkeypatch, local_socketpair):
    from tests.test_surge_engine import pattern_bars

    bars = pattern_bars()
    snapshot = DailySnapshot(
        bars,
        {
            "symbol": "SPY.US",
            "last_completed_bar": bars.index[-1].isoformat(),
            "retrieved_at": "2025-02-01T00:00:00Z",
            "cache_hit": False,
            "warning": "Historical/delayed data",
            "missing_sessions": [],
        },
    )
    download = Mock(return_value=snapshot)
    monkeypatch.setattr("tradingagents.dataflows.vendors.eodhd.EODHDClient.daily", download)
    entrypoint = Path(__file__).resolve().parents[1] / "tradingagents/surge/app.py"
    app = AppTest.from_file(entrypoint, default_timeout=15).run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert len(app.dataframe) == 2
    assert app.dataframe[0].value["partial_points"].iloc[0] == 1
    assert app.dataframe[0].value["scored_maximum"].iloc[0] == 1
    app.select_slider[0].set_value(bars.index[-2]).run()
    assert not app.exception
    assert len(app.dataframe) == 0
    assert download.call_count == 1  # replay does not consume API quota
    download.side_effect = EODHDError("test denied")
    app.button[0].click().run()
    assert not app.exception
    assert app.error[0].value == "test denied"
    assert "surge_scan" not in app.session_state
