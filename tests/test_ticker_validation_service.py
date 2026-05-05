from __future__ import annotations

import pytest

from tradingagents_service.ticker_validation import validate_ticker_for_shadow_run


@pytest.mark.unit
def test_ticker_validation_rejects_known_appl_typo() -> None:
    result = validate_ticker_for_shadow_run("APPL")

    assert result.accepted is False
    assert result.suggestion == "AAPL"
    assert result.validator == "known-correction"


@pytest.mark.unit
def test_ticker_validation_rejects_bad_symbol_shape() -> None:
    result = validate_ticker_for_shadow_run("AAPL;DROP")

    assert result.accepted is False
    assert result.suggestion is None


@pytest.mark.unit
def test_ticker_validation_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADINGAGENTS_TICKER_VALIDATION", "off")

    result = validate_ticker_for_shadow_run("NVDA")

    assert result.accepted is True
    assert result.validator == "disabled"
