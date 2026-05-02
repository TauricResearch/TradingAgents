"""Tests for _resolve_macro_brief and _parse_canonical_regime fallback logic."""

import json

import pytest

from agent_os.backend.services.langgraph_engine import (
    _parse_canonical_regime,
    _resolve_macro_brief,
)

_STRUCTURED_JSON = json.dumps(
    {
        "canonical_regime": {
            "label": "RISK-ON",
            "score": 3,
            "confidence": "high",
        }
    }
)

_REGIME_REPORT_TEXT = (
    "## Macro Regime Report\n\nCurrent Regime: RISK-ON (+3/6)\n\nMarket conditions are broadly constructive."
)

_UNPARSEABLE_TEXT = "This is just some random text with no regime information."


class TestResolveMacroBrief:
    def test_returns_first_parseable_structured_json(self) -> None:
        """Returns the structured JSON source when it parses successfully."""
        result = _resolve_macro_brief([_STRUCTURED_JSON, _REGIME_REPORT_TEXT, _UNPARSEABLE_TEXT])
        assert result == _STRUCTURED_JSON

    def test_skips_unparseable_and_returns_second_source(self) -> None:
        """Skips a raw JSON blob without canonical_regime and falls through to regime report."""
        raw_json_no_regime = json.dumps({"some_key": "some_value", "data": [1, 2, 3]})
        result = _resolve_macro_brief([raw_json_no_regime, _REGIME_REPORT_TEXT])
        assert result == _REGIME_REPORT_TEXT

    def test_returns_first_nonempty_when_all_sources_fail(self) -> None:
        """When no source parses, the first non-empty string is returned as fallback."""
        result = _resolve_macro_brief([_UNPARSEABLE_TEXT, "also unparseable"])
        assert result == _UNPARSEABLE_TEXT

    def test_returns_empty_string_when_all_sources_empty(self) -> None:
        """Returns empty string when every source is blank."""
        result = _resolve_macro_brief(["", "  ", ""])
        assert result == ""

    def test_skips_empty_sources_and_returns_valid_later_source(self) -> None:
        """Empty strings are skipped; a valid source later in the list is returned."""
        result = _resolve_macro_brief(["", "", _STRUCTURED_JSON])
        assert result == _STRUCTURED_JSON

    def test_empty_list_returns_empty_string(self) -> None:
        result = _resolve_macro_brief([])
        assert result == ""

    def test_uses_regime_report_when_scan_summary_lacks_canonical_regime(self) -> None:
        """Mirrors the real NOK/NVDA failure: scan_summary is non-empty JSON without
        canonical_regime; regime report has the ±N/6 text and should be returned."""
        old_style_summary = json.dumps(
            {
                "scan_date": "2026-03-31",
                "top_picks": ["AAPL", "MSFT"],
                # no canonical_regime key
            }
        )
        result = _resolve_macro_brief([old_style_summary, _REGIME_REPORT_TEXT])
        assert result == _REGIME_REPORT_TEXT


class TestParseCanonicalRegime:
    def test_parses_structured_json(self) -> None:
        parsed = _parse_canonical_regime(_STRUCTURED_JSON)
        assert parsed["label"] == "RISK-ON"
        assert parsed["score"] == 3
        assert parsed["confidence"] == "high"

    def test_parses_regime_report_text(self) -> None:
        parsed = _parse_canonical_regime(_REGIME_REPORT_TEXT)
        assert parsed["label"] == "RISK-ON"
        assert parsed["score"] == 3

    def test_returns_empty_dict_on_empty_string(self) -> None:
        result = _parse_canonical_regime("")
        assert result == {}

    def test_raises_on_unparseable_text(self) -> None:
        with pytest.raises(ValueError):
            _parse_canonical_regime(_UNPARSEABLE_TEXT)

    def test_raises_on_json_without_canonical_regime_key(self) -> None:
        with pytest.raises(ValueError):
            _parse_canonical_regime(json.dumps({"scan_date": "2026-03-31"}))
