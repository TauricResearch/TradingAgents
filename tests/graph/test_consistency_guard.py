from tradingagents.graph._consistency_guard import (
    NumericClaim,
    extract_numeric_claims,
    verify_against_fundamentals,
)


def test_extract_high_confidence_percent_claim():
    rm_text = "- EBITDA margin expanded +3.8% YoY coinciding with..."
    claims = extract_numeric_claims(rm_text)
    assert any(
        c.metric.lower().startswith("ebitda margin")
        and c.value == 3.8
        and c.unit == "%"
        and c.direction == "expansion"
        for c in claims
    )


def test_extract_bps_claim():
    rm_text = "- net leverage declined 320bps to 3.8x"
    claims = extract_numeric_claims(rm_text)
    bps = [c for c in claims if c.unit == "bps"]
    assert bps and bps[0].value == 320 and bps[0].direction == "compression"


def test_verify_detects_sign_disagreement():
    """RM claims margin expansion; fundamentals shows compression."""
    fundamentals = (
        "Operating margin Q4 2025: 9.3% vs Q2 2025: 12.0% - 270bps compression"
    )
    claims = [
        NumericClaim(
            metric="EBITDA margin",
            value=3.8,
            unit="%",
            direction="expansion",
            confidence="high",
        )
    ]
    result = verify_against_fundamentals(claims, fundamentals)
    assert len(result["violations"]) == 1
    assert "expansion" in result["violations"][0].reason.lower()


def test_verify_passes_when_within_tolerance():
    fundamentals = "Operating margin compressed 270bps over 2 quarters"
    claims = [
        NumericClaim(
            metric="operating margin",
            value=270,
            unit="bps",
            direction="compression",
            confidence="high",
        )
    ]
    result = verify_against_fundamentals(claims, fundamentals)
    assert result["violations"] == []


def test_unmappable_claim_downgrades_to_flag():
    """Metric not in fundamentals -> flag-only, not a violation."""
    fundamentals = "Operating margin compressed 270bps"
    claims = [
        NumericClaim(
            metric="DCF coverage ratio",
            value=1.2,
            unit="x",
            direction=None,
            confidence="low",
        )
    ]
    result = verify_against_fundamentals(claims, fundamentals)
    assert result["violations"] == []
    assert claims[0] in result["flags"]


def test_replay_et_rm_violations():
    """ET RM from run 01KQHDVJB2R19S4D7Z7Z6DP9F7 vs fundamentals report."""
    rm_text = (
        "- EBITDA margin expanded +3.8% YoY coinciding with U.S. sovereign...\n"
        "- Free cash flow conversion improved +14.2bps quarter-over-quarter "
        "while net leverage declined 320bps to 3.8x"
    )
    fundamentals = (
        "Operating margins peaked at 12.0% in Q2 2025 and have since declined to "
        "9.3% in Q4 2025, a 270bps compression. "
        "Free cash flow turned negative in Q4 2025 (-$225M). "
        "Total debt increased by $6.119B in Q4 2025 (+9.6% QoQ)."
    )
    claims = extract_numeric_claims(rm_text)
    result = verify_against_fundamentals(claims, fundamentals)
    # All three claims contradict fundamentals -> 3 high-confidence violations.
    assert len(result["violations"]) >= 2  # at least margin + leverage
