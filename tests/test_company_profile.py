from datetime import date

from tradingagents.research_platform.company_profile import build_company_profile
from tradingagents.research_platform.data_contracts import DataProvenance, FundamentalSnapshot


def test_company_profile_reads_vendor_identity_fields_from_latest_daily_snapshot():
    profile = build_company_profile(
        [
            FundamentalSnapshot(
                symbol="600519",
                period_end=date(2026, 7, 10),
                fiscal_period="daily_snapshot",
                metrics={
                    "company_name": "Kweichow Moutai",
                    "company_area": "Guizhou",
                    "company_industry": "Liquor",
                    "company_market": "Main board",
                    "company_exchange": "SSE",
                    "company_list_date": "20010827",
                },
                provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 7, 10)),
            )
        ],
        symbol="600519",
    )

    assert profile.available is True
    assert profile.name == "Kweichow Moutai"
    assert profile.industry == "Liquor"
    assert profile.list_date == "2001-08-27"


def test_company_profile_is_unavailable_without_vendor_identity_fields():
    profile = build_company_profile([], symbol="0700.HK")

    assert profile.available is False
    assert profile.name is None


def test_company_profile_ignores_newer_cache_snapshot_without_profile_fields():
    profile_snapshot = FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 7, 10),
        fiscal_period="daily_snapshot",
        metrics={"company_name": "Kweichow Moutai"},
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 7, 10)),
    )
    newer_snapshot = FundamentalSnapshot(
        symbol="600519",
        period_end=date(2026, 7, 10),
        fiscal_period="daily_snapshot",
        metrics={"pe_ratio_ttm": 18.0},
        provenance=DataProvenance(provider="fixture", as_of_date=date(2026, 7, 11)),
    )

    profile = build_company_profile([profile_snapshot, newer_snapshot], symbol="600519")

    assert profile.available is True
    assert profile.name == "Kweichow Moutai"
    assert profile.as_of_date == "2026-07-10"
