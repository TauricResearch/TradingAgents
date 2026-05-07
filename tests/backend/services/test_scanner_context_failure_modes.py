"""Unit tests for scanner context failure modes.

Tests that:
1. Missing scan_date causes the node to fail with a clear error message.
2. validate_commodity_block() rejects bare percentages without timeframe labels.
3. validate_commodity_block() accepts properly labeled percentages.

Validates: Requirements 6.4, 6.5
"""

from __future__ import annotations

import pytest

from agent_os.backend.services.scanner_context import (
    build_scanner_context_packet,
    validate_commodity_block,
)

# ---------------------------------------------------------------------------
# Requirement 6.5: Missing scan_date fails the node with a clear error
# ---------------------------------------------------------------------------


class TestMissingScanDateFailure:
    """build_scanner_context_packet must fail loudly when scan_date is missing."""

    def test_missing_scan_date_raises_runtime_error(self) -> None:
        """When scan_date is absent from scan_state, a RuntimeError is raised."""
        scan_state: dict = {}
        with pytest.raises(RuntimeError, match="scan_date is missing"):
            build_scanner_context_packet(scan_state, "AAPL")

    def test_none_scan_date_raises_runtime_error(self) -> None:
        """When scan_date is explicitly None, a RuntimeError is raised."""
        scan_state: dict = {"scan_date": None}
        with pytest.raises(RuntimeError, match="scan_date is missing"):
            build_scanner_context_packet(scan_state, "AAPL")

    def test_empty_string_scan_date_raises_runtime_error(self) -> None:
        """When scan_date is an empty string, a RuntimeError is raised."""
        scan_state: dict = {"scan_date": ""}
        with pytest.raises(RuntimeError, match="scan_date is missing"):
            build_scanner_context_packet(scan_state, "AAPL")

    def test_error_message_mentions_determinism(self) -> None:
        """The error message explains the scanner determinism requirement."""
        scan_state: dict = {}
        with pytest.raises(RuntimeError, match="deterministic scan date"):
            build_scanner_context_packet(scan_state, "TSLA")

    def test_malformed_scan_date_raises_runtime_error(self) -> None:
        """When scan_date is present but not YYYY-MM-DD, a RuntimeError is raised."""
        scan_state: dict = {"scan_date": "2025/03/15"}
        with pytest.raises(RuntimeError, match="malformed"):
            build_scanner_context_packet(scan_state, "AAPL")

    def test_invalid_date_string_raises_runtime_error(self) -> None:
        """When scan_date is a non-date string, a RuntimeError is raised."""
        scan_state: dict = {"scan_date": "not-a-date"}
        with pytest.raises(RuntimeError, match="malformed"):
            build_scanner_context_packet(scan_state, "MSFT")


# ---------------------------------------------------------------------------
# Requirement 6.4: validate_commodity_block rejects bare percentages
# ---------------------------------------------------------------------------


class TestValidateCommodityBlockRejectsBare:
    """validate_commodity_block must reject bare percentages without labels."""

    def test_rejects_bare_positive_percentage(self) -> None:
        """A bare '+5.2%' without daily/YoY label is rejected."""
        text = "Gold: $2000.00 (+5.2%)"
        assert validate_commodity_block(text) is False

    def test_rejects_bare_negative_percentage(self) -> None:
        """A bare '-12%' without daily/YoY label is rejected."""
        text = "Oil: $75.00 (-12%)"
        assert validate_commodity_block(text) is False

    def test_rejects_bare_percentage_no_sign(self) -> None:
        """A bare '3.5%' without sign or label is rejected."""
        text = "DXY: $104.50 (3.5%)"
        assert validate_commodity_block(text) is False

    def test_rejects_mixed_bare_and_labeled(self) -> None:
        """If any percentage is bare, the block is rejected even if others are labeled."""
        text = (
            "Gold: $2000.00 (+1.50% daily, +8.00% YoY)\n"
            "Oil: $75.00 (-3.2%)"
        )
        assert validate_commodity_block(text) is False

    def test_rejects_multiline_bare_percentages(self) -> None:
        """Multiple bare percentages across lines are all rejected."""
        text = (
            "- Gold $4583 (-12%)\n"
            "- Oil $68 (+2.5%)\n"
        )
        assert validate_commodity_block(text) is False


# ---------------------------------------------------------------------------
# Requirement 6.4: validate_commodity_block accepts properly labeled percentages
# ---------------------------------------------------------------------------


class TestValidateCommodityBlockAcceptsLabeled:
    """validate_commodity_block must accept properly labeled percentages."""

    def test_accepts_daily_and_yoy_labels(self) -> None:
        """Standard format with both daily and YoY labels passes."""
        text = "Gold: $2000.00 (+1.50% daily, +8.00% YoY)"
        assert validate_commodity_block(text) is True

    def test_accepts_negative_daily_and_yoy(self) -> None:
        """Negative percentages with labels pass."""
        text = "Oil: $68.50 (-2.30% daily, -15.00% YoY)"
        assert validate_commodity_block(text) is True

    def test_accepts_multiline_all_labeled(self) -> None:
        """Multiple commodity lines all properly labeled pass."""
        text = (
            "- Gold: $2000.00 (+1.50% daily, +8.00% YoY)\n"
            "- Oil: $68.50 (-2.30% daily, -15.00% YoY)\n"
            "- Bitcoin: $45000.00 (+0.80% daily, +120.00% YoY)"
        )
        assert validate_commodity_block(text) is True

    def test_accepts_text_without_percentages(self) -> None:
        """Text with no percentages at all is valid (nothing to reject)."""
        text = "Gold: $2000.00 (no change data available)"
        assert validate_commodity_block(text) is True

    def test_accepts_empty_string(self) -> None:
        """Empty string has no bare percentages, so it passes."""
        assert validate_commodity_block("") is True

    def test_accepts_na_fallback(self) -> None:
        """N/A fallback lines have no percentages, so they pass."""
        text = "- N/A\n- N/A"
        assert validate_commodity_block(text) is True
