import threading

from tradingagents.dataflows import stockstats_utils


def test_get_fallback_session_reuses_session_in_same_thread(monkeypatch):
    created = []

    class FakeSession:
        def __init__(self):
            self.trust_env = True
            created.append(self)

    monkeypatch.setattr(stockstats_utils, "_fallback_session_local", threading.local())
    monkeypatch.setattr(stockstats_utils.requests, "Session", FakeSession)

    first = stockstats_utils._get_fallback_session()
    second = stockstats_utils._get_fallback_session()

    assert first is second
    assert len(created) == 1
    assert first.trust_env is False
