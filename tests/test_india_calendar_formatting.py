from datetime import date

import pytest

from tradingagents.dataflows.india.calendar import (
    IndiaCalendarError,
    get_last_completed_india_trading_day,
    resolve_india_analysis_date,
)
from tradingagents.dataflows.india.formatting import (
    format_bps,
    format_inr,
    format_inr_crore_lakh,
    format_percent,
    quarter_fy_label,
)


@pytest.mark.unit
def test_weekend_rolls_back_to_previous_trading_day():
    resolved, warnings = resolve_india_analysis_date(
        "2026-06-07",
        today=date(2026, 6, 7),
        holidays_path="missing.yml",
    )
    assert resolved == "2026-06-05"
    assert warnings


@pytest.mark.unit
def test_future_date_rejected():
    with pytest.raises(IndiaCalendarError):
        resolve_india_analysis_date("2026-06-08", today=date(2026, 6, 7))


@pytest.mark.unit
def test_last_completed_trading_day_on_sunday():
    assert get_last_completed_india_trading_day(today=date(2026, 6, 7), holidays_path="missing.yml") == "2026-06-05"


@pytest.mark.unit
def test_inr_formatting():
    assert format_inr(1234.5) == "₹1,234.50"
    assert format_inr_crore_lakh(25_000_000) == "₹2.50 crore"
    assert format_inr_crore_lakh(250_000) == "₹2.50 lakh"
    assert format_bps(125) == "125 bps"
    assert format_percent(12.345) == "12.35%"
    assert quarter_fy_label(1, 2026) == "Q1FY26"
