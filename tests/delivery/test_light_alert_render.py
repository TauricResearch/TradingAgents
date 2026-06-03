import pytest
from tradingagents.delivery.render import render_for_channel


@pytest.mark.unit
@pytest.mark.parametrize("channel", ["cli", "telegram", "email"])
def test_light_alert_renders_summary_and_tickers(channel):
    brief = {
        "brief_id": "lb1",
        "mode": "event_alert_light",
        "summary": "Networking-sector outage report; vendors may see demand shifts.",
        "tickers": ["NVDA", "PANW"],
        "event_headline": "Sector outage",
    }
    out = render_for_channel(channel=channel, mode="event_alert_light", brief=brief)
    assert "Networking-sector outage" in out
    assert "NVDA" in out and "PANW" in out
