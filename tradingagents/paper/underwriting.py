"""Koral Equities Discovery V2: conservative, industry-aware underwriting gate.

This is NOT a valuation engine or an AI price-target generator. It establishes
which valuation method is appropriate, reports mechanically calculable market
metrics, and lists missing primary evidence before underwriting a 10x case.

The inputs originate in current vendor snapshots; without dated financial
filings and an industry-specific economic model, the correct state is
INSUFFICIENT_EVIDENCE. All outputs are JSON-serialisable.

No imports from paper portfolios, trading agents, networks or broker APIs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class IndustryMethod:
    code: str
    title: str
    method: str
    required_primary_evidence: tuple[str, ...]


METHODS = {
    "MINING": IndustryMethod(
        "MINING", "Mining and mineral assets", "Mine-by-mine discounted NAV and cycle-normalised cash flows",
        ("dated mineral reserves and resources with mine lives", "mine-level production, unit costs and recoveries",
         "project capex, sustaining capex and buildout schedules", "commodity price deck and operating-cost sensitivities",
         "debt covenants, maturities and funding commitments")),
    "EXPLORATION_ENERGY": IndustryMethod(
        "EXPLORATION_ENERGY", "Hydrocarbon production", "Reserve-based NAV and cycle-normalised upstream FCF",
        ("proved/developed reserves, depletion and decline curves", "volume, realised prices, royalties and unit costs",
         "maintenance versus development capex", "oil and gas downside scenarios",
         "borrowing-base commitments and debt maturities")),
    "REFINING": IndustryMethod(
        "REFINING", "Refining and commodity processing", "Through-cycle normalised EV/EBITDA and FCF",
        ("refining margins and crack-spread sensitivity", "through-cycle operating margins and utilisation",
         "maintenance capex and turnaround commitments", "working-capital and commodity inventory swings",
         "net debt and debt refinancing schedule")),
    "SOFTWARE": IndustryMethod(
        "SOFTWARE", "Software / subscription economics", "Cohort cash-flow DCF and comparable recurring-revenue valuations",
        ("filing-verified revenue and gross-margin history", "ARR/retention/cohort churn disclosures",
         "sales efficiency and customer acquisition economics", "stock-based compensation and diluted share trajectory",
         "owner free cash flow after recurring costs")),
    "TECH_SERVICES": IndustryMethod(
        "TECH_SERVICES", "Technology products and services", "Normalised owner FCF, reinvestment returns and segment SOTP",
        ("segment revenue and margin trajectory", "capital intensity, stock compensation and owner FCF",
         "customer concentration, contract retention and growth", "competitive advantages and unit economics",
         "diluted shares and balance sheet obligations")),
    "BANKING": IndustryMethod(
        "BANKING", "Banks and lending", "Return on tangible equity, capital and justified P/TBV",
        ("regulatory capital ratios and capital adequacy", "credit loss provisions and nonperforming loans",
         "loan book mix and deposit cost trends", "through-cycle ROE and book-value reconciliation",
         "regulatory liquidity, dividends and dilution")),
    "INSURANCE": IndustryMethod(
        "INSURANCE", "Insurance underwriting", "Combined ratio, reserve adequacy and adjusted tangible equity",
        ("loss-reserve development triangles and actuarial review", "premium retention and combined ratios",
         "statutory capital and investment portfolio risks", "normalised underwriting return on equity",
         "share count and capital distributions")),
    "HEALTHCARE": IndustryMethod(
        "HEALTHCARE", "Medical technology and biotech", "Risk-adjusted product cash-flow DCF",
        ("regulatory approvals and product indication evidence", "clinical or customer adoption data",
         "reimbursement, retention and gross economics", "cash runway, trial/launch spending and dilution",
         "probability-adjusted milestones backed by filings")),
    "CONSUMER": IndustryMethod(
        "CONSUMER", "Consumer and retail", "Normalised owner FCF and unit-economics valuation",
        ("same-store growth, unit count and gross margins", "inventory cycles and lease commitments",
         "maintenance capex and store-level returns", "five-year comparable operating history",
         "diluted share counts and debt maturities")),
    "INDUSTRIAL": IndustryMethod(
        "INDUSTRIAL", "Industrials and other cyclicals", "Through-cycle EV/EBIT, capital returns and owner FCF",
        ("through-cycle EBIT and revenue history", "segment margins, volumes and operating leverage",
         "maintenance capex and working capital", "debt maturity and pension obligations",
         "diluted shares and organic versus acquisition growth")),
    "OTHER": IndustryMethod(
        "OTHER", "Unclassified business model", "Determine appropriate method from SEC filings before valuation",
        ("filed business-segment description", "verified revenue and margin history",
         "capital structure and diluted shares", "cash generation and capital intensity",
         "documented appropriate peer and valuation methodology")),
}


def _number(x):
    if isinstance(x, bool):
        return None
    try:
        value = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _money(value):
    return round(value, 2) if value is not None and math.isfinite(value) else None


def industry_method(sector: str, industry: str) -> IndustryMethod:
    s, i = (sector or "").lower(), (industry or "").lower()
    if any(t in i for t in ("copper", "gold", "silver", "metal mining", "other industrial metals", "uranium", "mining")):
        return METHODS["MINING"]
    if "refin" in i or "marketing" in i and "oil" in i:
        return METHODS["REFINING"]
    if any(t in i for t in ("oil & gas e&p", "oil and gas exploration", "oil & gas integrated", "oil & gas drilling")):
        return METHODS["EXPLORATION_ENERGY"]
    if "bank" in i:
        return METHODS["BANKING"]
    if "insur" in i:
        return METHODS["INSURANCE"]
    if "software" in i or "application" in i and "technolog" in s:
        return METHODS["SOFTWARE"]
    if any(t in i for t in ("medical device", "medical instrument", "biotechnology", "diagnostic", "drug manufacturer")):
        return METHODS["HEALTHCARE"]
    if any(t in s for t in ("consumer", "retail")) or any(t in i for t in ("restaurants", "apparel retail")):
        return METHODS["CONSUMER"]
    if "technology" in s or "communication services" in s:
        return METHODS["TECH_SERVICES"]
    if "industrials" in s or "basic materials" in s or "energy" in s:
        return METHODS["INDUSTRIAL"]
    return METHODS["OTHER"]


def underwriting(company: Mapping, *, years: int = 5, filing_evidence: Mapping | None = None) -> dict:
    """Produce an evidence-based underwriting checklist, NOT a return forecast."""
    if years < 1 or years > 15:
        raise ValueError("Underwriting horizon must be between 1 and 15 years")
    cap = _number(company.get("market_cap_usd"))
    revenue = _number(company.get("revenue_ttm_usd"))
    growth = _number(company.get("revenue_growth_vendor"))
    fcf = _number(company.get("free_cash_flow_usd"))
    cash = _number(company.get("cash_usd"))
    debt = _number(company.get("debt_usd"))
    earnings = _number(company.get("net_income_ttm_usd"))
    ebitda = _number(company.get("ebitda_ttm_usd"))
    shares = _number(company.get("shares_outstanding"))
    method = industry_method(company.get("sector", ""), company.get("industry", ""))
    balance = cash is not None and cash >= 0 and debt is not None and debt >= 0
    net_debt = debt - cash if balance else None
    ev = cap + net_debt if cap is not None and cap > 0 and net_debt is not None else None
    current = {
        "market_cap_usd": _money(cap),
        "net_debt_vendor_usd": _money(net_debt),
        "enterprise_value_vendor_usd": _money(ev) if method.code not in {"BANKING", "INSURANCE"} else None,
        "fcf_yield_vendor_pct": round(100 * fcf / cap, 2) if cap and cap > 0 and fcf is not None else None,
        "ev_to_ebitda_vendor_spot": round(ev / ebitda, 2) if (ev is not None and ev > 0 and
                                     ebitda is not None and ebitda > 0 and method.code not in {"BANKING", "INSURANCE"}) else None,
        "market_cap_to_revenue_vendor_spot": round(cap / revenue, 2) if cap and cap > 0 and revenue and revenue > 0 else None,
        "revenue_growth_vendor_snapshot_pct": round(100 * growth, 2) if growth is not None else None,
        "earnings_vendor_usd": _money(earnings),
        "shares_outstanding_vendor": _money(shares),
    }
    filing = dict(filing_evidence) if isinstance(filing_evidence, Mapping) else {"status": "NOT_CHECKED"}
    evidence = filing.get("status", "NOT_CHECKED")
    missing = list(method.required_primary_evidence)
    risks = []
    if not balance:
        risks.append("Cash and debt cannot both be verified from the current vendor snapshot")
    elif net_debt and net_debt > 0:
        risks.append("Net debt increases equity sensitivity to operating downside")
    if fcf is None:
        risks.append("Free cash flow missing; cannot validate conversion from earnings to cash")
    elif fcf <= 0:
        risks.append("Current vendor-reported free cash flow is non-positive")
    if method.code in {"MINING", "EXPLORATION_ENERGY", "REFINING", "INDUSTRIAL"}:
        risks.append("Cyclical profits require through-cycle normalization, not extrapolation")
    if method.code == "HEALTHCARE":
        risks.append("Approval, reimbursement and financing milestones may cause permanent loss")
    if method.code in {"SOFTWARE", "TECH_SERVICES"}:
        risks.append("Stock-based compensation and long-term dilution have not been reconciled")
    if growth is None:
        risks.append("Vendor revenue growth missing")
    elif growth > 0.5:
        risks.append("Exceptional snapshot growth may be cyclic, acquisition-led or non-recurring")
    if shares is None or shares <= 0:
        risks.append("No verified diluted share-count trajectory; 10x must be PER SHARE")
    if evidence != "AVAILABLE":
        risks.append("No verified primary-filing metadata attached to this candidate")
    hurdle = {
        "horizon_years": years, "existing_shareholder_multiple_required": 10,
        "annualised_shareholder_return_hurdle_pct": round(100 * (10 ** (1 / years) - 1), 2),
        "starting_equity_value_usd": _money(cap),
        "equity_value_at_unchanged_share_count_usd": _money(10 * cap) if cap and cap > 0 else None,
        "annual_dilution_rate": None, "implied_company_equity_value_with_dilution_usd": None,
        "forecast_price_target": None, "forecast_return_multiple": None,
        "plausibility_probability": None,
        "note": "This is the mathematical shareholder hurdle, not a forecast. Dilution, capital investment and industry risks are not predicted.",
    }
    return {
        "schema": "koral_underwriting_v2", "business_model": method.code,
        "business_model_label": method.title, "valuation_method": method.method,
        "rating": "INSUFFICIENT_EVIDENCE",
        "evidence_status": "PRIMARY_FILINGS_LINKED_NOT_FINANCIALS_VERIFIED" if evidence == "AVAILABLE" else "VENDOR_SNAPSHOT_ONLY",
        "research_priority": "REQUIRES_DEEP_DILIGENCE",
        "source": {"vendor": "Yahoo Finance current company profile (not audited, timestamped financial statements)",
                   "primary_filing_lookup": filing, "asof_daily_candle": company.get("price_asof")},
        "spot_metrics": current, "ten_x": hurdle,
        "required_primary_evidence": missing, "risk_flags": risks,
        "unsupported_models": ["Uniform 3x/6x sales valuation",
                               "Automatic 5-year revenue CAGR extrapolation",
                               "Calibrated probability of tenfold returns"],
        "orders_permitted": False,
    }
