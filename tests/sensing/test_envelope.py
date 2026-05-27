import json
import pytest


@pytest.mark.unit
def test_envelope_round_trip_json():
    from tradingagents.sensing.envelope import Envelope
    env = Envelope(
        source="polygon_news",
        ingested_ts="2026-05-26T14:33:21.123Z",
        external_id="pn:abc123",
        text="Apple reports earnings beat.",
        source_tags={"tickers": ["AAPL"], "category": "earnings"},
        raw_path="data/events/staging/2026-05-26/abc123.json",
    )
    blob = env.to_json()
    parsed = Envelope.from_json(blob)
    assert parsed == env


@pytest.mark.unit
def test_envelope_to_redis_fields():
    """Redis XADD takes a flat dict[str, str]; envelope must serialize cleanly."""
    from tradingagents.sensing.envelope import Envelope
    env = Envelope(
        source="rss", ingested_ts="2026-05-26T00:00:00Z",
        external_id="rss:1", text="...", source_tags={}, raw_path="p",
    )
    fields = env.to_redis_fields()
    assert isinstance(fields, dict)
    assert all(isinstance(k, str) and isinstance(v, str)
               for k, v in fields.items())
    assert "data" in fields
    assert json.loads(fields["data"])["source"] == "rss"


@pytest.mark.unit
def test_envelope_from_redis_fields():
    from tradingagents.sensing.envelope import Envelope
    env = Envelope(source="x", ingested_ts="t", external_id="x:1",
                   text="hello", source_tags={"a": 1}, raw_path="p")
    fields = env.to_redis_fields()
    assert Envelope.from_redis_fields(fields) == env


@pytest.mark.unit
def test_envelope_text_truncation_for_fingerprint():
    """Whitespace + leading/trailing-noise normalization for SHA-256 input."""
    from tradingagents.sensing.envelope import normalize_for_fingerprint
    assert normalize_for_fingerprint("  Hello   World\n\n") == \
           normalize_for_fingerprint("hello world")
