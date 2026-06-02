from __future__ import annotations

import pytest


@pytest.mark.unit
def test_historical_snapshot_caveat_for_past_date():
    from tradingagents.dataflows.point_in_time import historical_snapshot_caveat

    caveat = historical_snapshot_caveat("2020-01-02")

    assert "LATEST snapshot" in caveat
    assert "not point-in-time as of 2020-01-02" in caveat


@pytest.mark.unit
def test_alpha_vantage_fundamentals_prefixes_caveat_for_past_date(monkeypatch):
    import tradingagents.dataflows.alpha_vantage_fundamentals as avf

    # Mock cache_text if it is present (PR-10)
    if hasattr(avf, "cache_text"):
        monkeypatch.setattr(avf, "cache_text", lambda namespace, parts, fetch: fetch())
    monkeypatch.setattr(avf, "_make_api_request", lambda function, params: '{"PERatio":"20"}')

    out = avf.get_fundamentals("AAPL", curr_date="2020-01-02")

    assert out.startswith("NOTE: OVERVIEW/company-info metrics reflect the LATEST snapshot")
    assert '"PERatio"' in out


@pytest.mark.unit
def test_alpha_vantage_fundamentals_today_has_no_caveat(monkeypatch):
    from datetime import date
    import tradingagents.dataflows.alpha_vantage_fundamentals as avf

    # Mock cache_text if it is present (PR-10)
    if hasattr(avf, "cache_text"):
        monkeypatch.setattr(avf, "cache_text", lambda namespace, parts, fetch: fetch())
    monkeypatch.setattr(avf, "_make_api_request", lambda function, params: '{"PERatio":"20"}')

    out = avf.get_fundamentals("AAPL", curr_date=date.today().strftime("%Y-%m-%d"))

    assert not out.startswith("NOTE: OVERVIEW")
