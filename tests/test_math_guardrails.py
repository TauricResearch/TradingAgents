import pytest

from tradingagents.guardrails import (
    MathGuardrailEngine,
    build_market_price_anchor,
)


@pytest.mark.unit
def test_build_market_price_anchor_uses_latest_close_from_snapshot_payload():
    anchor = build_market_price_anchor(
        symbol="cof",
        as_of_date="2026-05-20",
        market_snapshot_payload={
            "latest_ohlcv": {"Close": 123.45},
            "latest_date": "2026-05-20",
        },
        evidence_id="EVD-MKT-123",
    )

    assert anchor.anchor_id.startswith("QA-")
    assert anchor.symbol == "COF"
    assert anchor.as_of_date == "2026-05-20"
    assert anchor.current_price == 123.45
    assert anchor.evidence_id == "EVD-MKT-123"


@pytest.mark.unit
def test_price_target_inside_warn_threshold_has_no_events():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    events = MathGuardrailEngine().check_price_target(anchor, 250)

    assert events == []


@pytest.mark.unit
def test_missing_price_target_has_no_events():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    events = MathGuardrailEngine().check_price_target(anchor, None)

    assert events == []


@pytest.mark.unit
def test_price_target_at_warn_multiple_emits_warn_event():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    [event] = MathGuardrailEngine().check_price_target(anchor, 300)

    assert event.rule_id == "price_target_multiple"
    assert event.status == "warn"
    assert event.action == "review_target_price"
    assert event.actual_value == 3.0


@pytest.mark.unit
def test_price_target_at_block_multiple_emits_blocked_event():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    [event] = MathGuardrailEngine().check_price_target(anchor, 500)

    assert event.rule_id == "price_target_multiple"
    assert event.status == "blocked"
    assert event.action == "remove_or_rejustify_target_price"
    assert event.actual_value == 5.0


@pytest.mark.unit
def test_low_price_target_at_warn_multiple_emits_warn_event():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    [event] = MathGuardrailEngine().check_price_target(anchor, 100 / 3)

    assert event.rule_id == "price_target_multiple"
    assert event.status == "warn"
    assert event.action == "review_target_price"
    assert event.actual_value == pytest.approx(3.0)


@pytest.mark.unit
def test_low_price_target_at_block_multiple_emits_blocked_event():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    [event] = MathGuardrailEngine().check_price_target(anchor, 20)

    assert event.rule_id == "price_target_multiple"
    assert event.status == "blocked"
    assert event.action == "remove_or_rejustify_target_price"
    assert event.actual_value == 5.0


@pytest.mark.unit
def test_non_positive_price_target_is_blocked():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": 100}}, "EVD-MKT")

    [event] = MathGuardrailEngine().check_price_target(anchor, 0)

    assert event.rule_id == "price_target_positive"
    assert event.status == "blocked"
    assert event.action == "remove_target_price"


@pytest.mark.unit
def test_missing_current_price_skips_target_check_with_warning():
    anchor = build_market_price_anchor("COF", "2026-05-20", {"latest_ohlcv": {"Close": None}}, "EVD-MKT")

    [event] = MathGuardrailEngine().check_price_target(anchor, 100)

    assert event.rule_id == "current_price_available"
    assert event.status == "warn"
    assert event.action == "skip_target_price_check"
