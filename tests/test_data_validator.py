"""Phase 1 — deterministic data validator tests (contract section 3.3).

Generic rules over vendor data: OHLC consistency, unit reconciliation,
share-class conversion, ticker identity. Nothing is BRK-B-specific; the
regression numbers live in the Phase 0 fixture and the tests that use them.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows.validator import (
    BRK_A_TO_B_RATIO,
    OK,
    QUARANTINED,
    UNVERIFIED,
    check_ticker_identity,
    convert_share_class,
    reconcile_metric,
    validate_ohlcv_frame,
    validate_share_class_comparison,
)


def _frame(rows):
    return pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])


# ---------------------------------------------------------------------------
# OHLC consistency
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_consistent_frame_is_ok():
    df = _frame([
        ["2026-11-06", 571.0, 573.0, 569.5, 570.89, 1_000_000],
        ["2026-11-05", 572.0, 574.0, 571.0, 572.33, 900_000],
    ])
    result = validate_ohlcv_frame(df)
    assert result.status == OK
    assert result.issues == []


@pytest.mark.unit
def test_inverted_high_low_is_an_error():
    df = _frame([["2026-11-06", 571.0, 569.0, 570.0, 570.89, 1_000_000]])
    result = validate_ohlcv_frame(df)
    assert result.status == QUARANTINED
    assert any(i.code == "OHLCV_INVERTED_RANGE" for i in result.issues)


@pytest.mark.unit
def test_close_outside_bar_range_is_an_error():
    df = _frame([["2026-11-06", 571.0, 573.0, 571.5, 560.0, 1_000_000]])
    result = validate_ohlcv_frame(df)
    assert result.has_errors
    assert any(i.code == "OHLCV_RANGE_VIOLATION" for i in result.issues)


@pytest.mark.unit
def test_negative_volume_and_nonpositive_close_are_errors():
    df = _frame([
        ["2026-11-06", 571.0, 573.0, 569.5, 570.89, -5],
        ["2026-11-05", 572.0, 574.0, 571.0, 0.0, 900_000],
    ])
    result = validate_ohlcv_frame(df)
    codes = {i.code for i in result.issues}
    assert "OHLCV_NEGATIVE_VOLUME" in codes
    assert "OHLCV_NONPOSITIVE_PRICE" in codes
    assert result.status == QUARANTINED


@pytest.mark.unit
def test_all_nan_row_is_unsettled_not_corruption():
    df = _frame([["2026-11-06", None, None, None, None, None]])
    result = validate_ohlcv_frame(df)
    assert result.status == OK


@pytest.mark.unit
def test_missing_columns_is_an_error_not_a_keyerror():
    result = validate_ohlcv_frame(pd.DataFrame({"Close": [1.0]}))
    assert result.status == QUARANTINED
    assert any(i.code == "OHLCV_MISSING_COLUMNS" for i in result.issues)


# ---------------------------------------------------------------------------
# Unit / scale reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_matching_values_across_scales_reconcile():
    """12,705 million reported vs 12.705 billion derived: same fact."""
    result, delta = reconcile_metric(
        12_705, 12.705, reported_unit="million", derived_unit="billion"
    )
    assert result.status == OK
    assert delta == pytest.approx(0.0)


@pytest.mark.unit
def test_mismatched_values_beyond_materiality_are_quarantined():
    result, delta = reconcile_metric(
        12_705, 9_000, reported_unit="million", derived_unit="million"
    )
    assert result.status == QUARANTINED
    assert any(i.code == "RECONCILIATION_MISMATCH" for i in result.issues)
    assert delta == pytest.approx(41.17, abs=0.01)


@pytest.mark.unit
def test_small_drift_within_materiality_is_a_warning():
    result, delta = reconcile_metric(
        100.0, 100.02, reported_unit="unit", derived_unit="unit",
        materiality_pct=1.0,
    )
    assert result.status == UNVERIFIED  # warnings, no errors
    assert any(i.code == "RECONCILIATION_MINOR_DRIFT" for i in result.issues)


@pytest.mark.unit
def test_unknown_unit_cannot_reconcile():
    result, delta = reconcile_metric(5, 5, reported_unit="USD", derived_unit="million")
    assert result.status == QUARANTINED
    assert delta is None


@pytest.mark.unit
def test_zero_derived_value_is_undefined_not_divide_by_zero():
    result, delta = reconcile_metric(5, 0, reported_unit="unit", derived_unit="unit")
    assert result.status == QUARANTINED
    assert delta is None


# ---------------------------------------------------------------------------
# Share-class conversion
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_brk_a_to_b_conversion_divides_by_1500():
    """A per-A book value of 450,000 becomes 300 per B share."""
    assert convert_share_class(450_000.0, BRK_A_TO_B_RATIO, "A", "B") == pytest.approx(300.0)


@pytest.mark.unit
def test_brk_b_to_a_conversion_multiplies():
    assert convert_share_class(300.0, BRK_A_TO_B_RATIO, "B", "A") == pytest.approx(450_000.0)


@pytest.mark.unit
def test_cross_class_price_to_book_comparison_is_an_error():
    """A BRK-B price against BRK-A BVPS is wrong by 1500x: blocked (DEF-006)."""
    result = validate_share_class_comparison(570.89, 450_000.0, "B", "A")
    assert result.status == QUARANTINED
    assert any(i.code == "SHARE_CLASS_MISMATCH" for i in result.issues)


@pytest.mark.unit
def test_same_class_comparison_passes():
    result = validate_share_class_comparison(570.89, 300.0, "B", "B")
    assert result.status == OK


@pytest.mark.unit
def test_conversion_rejects_bad_ratio_and_same_class():
    with pytest.raises(ValueError):
        convert_share_class(1.0, 0, "A", "B")
    with pytest.raises(ValueError):
        convert_share_class(1.0, 1500, "A", "A")


# ---------------------------------------------------------------------------
# Ticker identity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sibling_share_class_serving_is_an_error():
    """Asked for BRK-B, served BRK-A: different instrument, not interchangeable.

    Sibling detection comes from the InstrumentProfile (structural); without
    one, a bare string mismatch is only a normalization warning.
    """
    from tradingagents.dataflows.instrument_profiler import profile_instrument

    profile = profile_instrument("BRK-B", {"quoteType": "EQUITY", "currency": "USD"})
    result = check_ticker_identity("BRK-B", "BRK-A", profile=profile)
    assert result.status == QUARANTINED
    assert any(i.code == "TICKER_SIBLING_CLASS" for i in result.issues)


@pytest.mark.unit
def test_exact_match_passes():
    assert check_ticker_identity("BRK-B", "BRK-B").status == OK


@pytest.mark.unit
def test_legitimate_rewrite_is_a_warning_not_an_error():
    """Normalization may rewrite a symbol (e.g. 700.HK -> 0700.HK): warn only."""
    result = check_ticker_identity("700.HK", "0700.HK")
    assert result.status == UNVERIFIED
    assert any(i.code == "TICKER_REWRITTEN" for i in result.issues)
