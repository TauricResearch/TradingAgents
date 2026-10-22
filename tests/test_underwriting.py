"""Discovery V2: industry-aware valuation gates never invent 10x price targets."""
import pytest
from tradingagents.paper.underwriting import industry_method, underwriting

def company(**changes):
    base={"market_cap_usd":3.16e9,"revenue_ttm_usd":1.045e9,
          "revenue_growth_vendor":.739,"sector":"Basic Materials","industry":"Copper",
          "free_cash_flow_usd":47e6,"cash_usd":101.7e6,"debt_usd":573e6,
          "price_asof":"2026-10-21"}
    base.update(changes)
    return base

@pytest.mark.parametrize("sector,industry,code",[
    ("Basic Materials","Copper","MINING"),
    ("Energy","Oil & Gas Refining & Marketing","REFINING"),
    ("Technology","Software - Application","SOFTWARE"),
    ("Technology","Information Technology Services","TECH_SERVICES"),
    ("Financial Services","Banks - Regional","BANKING"),
    ("Financial Services","Insurance - Diversified","INSURANCE"),
    ("Healthcare","Biotechnology","HEALTHCARE"),
    ("Consumer Cyclical","Specialty Retail","CONSUMER"),
    ("Industrials","Industrial Distribution","INDUSTRIAL"),
    ("","","OTHER"),
])
def test_business_classification(sector,industry,code):
    assert industry_method(sector,industry).code==code

def test_ero_requires_mine_nav_and_real_reserves():
    result=underwriting(company())
    assert result["business_model"]=="MINING"
    assert "NAV" in result["valuation_method"]
    assert result["rating"]=="INSUFFICIENT_EVIDENCE"
    assert result["ten_x"]["forecast_return_multiple"] is None
    assert result["ten_x"]["annualised_shareholder_return_hurdle_pct"]==58.49
    assert result["spot_metrics"]["net_debt_vendor_usd"]==471.3e6
    assert any("reserves" in x for x in result["required_primary_evidence"])
    assert result["orders_permitted"] is False

def test_refiner_cannot_get_unjustified_101_times_return():
    result=underwriting(company(sector="Energy",industry="Oil & Gas Refining & Marketing",
                                market_cap_usd=9.44e9,revenue_ttm_usd=44e9))
    assert result["business_model"]=="REFINING"
    assert "normalised" in result["valuation_method"].lower()
    assert result["ten_x"]["forecast_return_multiple"] is None
    assert any("crack-spread" in x for x in result["required_primary_evidence"])

def test_software_uses_retention_while_vendor_fcf_yield_is_descriptive():
    result=underwriting(company(sector="Technology",industry="Software - Application",
                                market_cap_usd=1e9,free_cash_flow_usd=100e6,
                                shares_outstanding=100e6))
    assert result["spot_metrics"]["fcf_yield_vendor_pct"]==10
    assert any("retention" in x for x in result["required_primary_evidence"])
    assert result["ten_x"]["annual_dilution_rate"] is None

def test_banks_are_not_valued_on_enterprise_value():
    result=underwriting(company(sector="Financial Services",industry="Banks - Regional",
                                ebitda_ttm_usd=100e6))
    assert result["spot_metrics"]["enterprise_value_vendor_usd"] is None
    assert result["spot_metrics"]["ev_to_ebitda_vendor_spot"] is None

def test_missing_cash_debt_or_nonfinite_fcf_never_becomes_zero():
    result=underwriting(company(cash_usd=None,debt_usd=None,
                                free_cash_flow_usd=float("nan")))
    assert result["spot_metrics"]["net_debt_vendor_usd"] is None
    assert result["spot_metrics"]["fcf_yield_vendor_pct"] is None
    assert result["rating"]=="INSUFFICIENT_EVIDENCE"

def test_sec_filing_does_not_automatically_verify_vendor_financials():
    result=underwriting(company(),filing_evidence={"status":"AVAILABLE",
            "filings":[{"form":"6-K","filed":"2026-08-05"}]})
    assert result["evidence_status"]=="PRIMARY_FILINGS_LINKED_NOT_FINANCIALS_VERIFIED"
    assert result["rating"]=="INSUFFICIENT_EVIDENCE"

@pytest.mark.parametrize("years",[0,-1,16,40])
def test_invalid_tenfold_horizons_fail(years):
    with pytest.raises(ValueError):
        underwriting(company(),years=years)

def test_time_horizon_changes_math_not_price_forecast():
    result=underwriting(company(),years=10)
    assert result["ten_x"]["annualised_shareholder_return_hurdle_pct"]==25.89
    assert result["ten_x"]["forecast_price_target"] is None

def test_infinite_market_cap_is_rejected_not_rendered_as_nan():
    result=underwriting(company(market_cap_usd=float("inf")))
    assert result["spot_metrics"]["market_cap_usd"] is None
    assert result["ten_x"]["equity_value_at_unchanged_share_count_usd"] is None
