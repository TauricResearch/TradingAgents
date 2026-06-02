from __future__ import annotations

import pytest


@pytest.mark.unit
def test_make_api_request_retries_then_succeeds(monkeypatch):
    import tradingagents.dataflows.alpha_vantage_common as av

    calls = {"n": 0}

    class Response:
        text = '{"ok": 1}'

        def raise_for_status(self):
            return None

    def flaky_get(url, params, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            raise av.requests.Timeout()
        assert timeout == av.AV_REQUEST_TIMEOUT
        return Response()

    monkeypatch.setattr(av.requests, "get", flaky_get)
    monkeypatch.setattr(av, "get_api_key", lambda: "KEY")
    monkeypatch.setattr(av.time, "sleep", lambda *_: None)

    out = av._make_api_request("OVERVIEW", {"symbol": "AAPL"})

    assert calls["n"] == 2
    assert '"ok"' in out
