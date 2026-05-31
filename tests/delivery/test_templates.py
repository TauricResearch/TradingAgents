import pytest


SAMPLE_BRIEF = {
    "brief_id": "b1",
    "mode": "deep_dive",
    "scope": "AAPL",
    "generated_ts": "2026-05-27T12:00:00+00:00",
    "tickers": [
        {
            "ticker": "AAPL",
            "consensus": "Strong fundamentals; supply-chain risk noted.",
            "divergence": "Macro neutral; momentum bullish; value flat.",
            "recommendation": "BUY (medium confidence).",
        }
    ],
    "trigger_event": None,
}


@pytest.mark.unit
def test_render_cli_deep_dive():
    from tradingagents.delivery.render import render_for_channel
    out = render_for_channel(channel="cli", mode="deep_dive", brief=SAMPLE_BRIEF)
    assert "AAPL" in out
    assert "Strong fundamentals" in out
    assert "BUY" in out


@pytest.mark.unit
def test_render_telegram_deep_dive_is_terse():
    from tradingagents.delivery.render import render_for_channel
    out = render_for_channel(channel="telegram", mode="deep_dive", brief=SAMPLE_BRIEF)
    assert len(out) < 1500
    assert "AAPL" in out


@pytest.mark.unit
def test_render_email_morning_digest_html():
    from tradingagents.delivery.render import render_for_channel
    digest_brief = {**SAMPLE_BRIEF, "mode": "morning_digest"}
    out = render_for_channel(channel="email", mode="morning_digest", brief=digest_brief)
    assert "<html" in out.lower()
    assert "AAPL" in out


@pytest.mark.unit
def test_render_unknown_channel_raises():
    from tradingagents.delivery.render import render_for_channel
    with pytest.raises(ValueError, match="unknown channel"):
        render_for_channel(channel="sms", mode="deep_dive", brief=SAMPLE_BRIEF)


@pytest.mark.unit
def test_render_email_event_alert_falls_back_to_cli():
    """Email has no event_alert template (V1 design); fall back to cli/event_alert.j2."""
    from tradingagents.delivery.render import render_for_channel
    out = render_for_channel(channel="email", mode="event_alert", brief={
        **SAMPLE_BRIEF, "mode": "event_alert",
        "trigger_event": {"summary": "FOMC surprise rate cut.", "ts": "2026-05-27T14:00:00+00:00"},
    })
    assert "FOMC" in out
