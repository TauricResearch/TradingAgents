"""Tier 1 agents: Validation, Macro Regime, Liquidity.

Tier 1 is cheap and fast — runs on every stock. Validation is deterministic
(no LLM). Macro and Liquidity use the quick-thinking LLM.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import yfinance as yf

from tradingagents.models import (
    CompanyCard,
    DataFlag,
    LiquidityOutput,
    MacroRegimeOutput,
    ValidationOutput,
    invoke_structured,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_num(val):
    if val is None:
        return None
    if abs(val) >= 1e12:
        return f"${val / 1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"${val / 1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val / 1e6:.2f}M"
    return f"${val:,.0f}"


def _fetch_yf_info(ticker: str) -> dict:
    """Fetch yfinance info dict for a ticker."""
    try:
        t = yf.Ticker(ticker.upper())
        return t.info or {}
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return {}


def _fetch_macro_data() -> dict:
    """Fetch macro indicators via yfinance."""
    from tradingagents.dataflows.y_finance import get_macro_indicators

    try:
        raw = get_macro_indicators()
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        logger.warning("Macro data fetch failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Validation (deterministic — no LLM)
# ---------------------------------------------------------------------------

def create_validation_node(llm=None):
    """Validation + CompanyCard node. Does NOT use LLM — purely data-driven."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        info = _fetch_yf_info(ticker)

        # No data at all → hard veto
        company_name = info.get("longName") or info.get("shortName") or ""
        if not company_name:
            v = ValidationOutput(
                ticker_valid=False,
                ticker_resolved=ticker.upper(),
                company_name="",
                veto=True,
                veto_reason=f"No company data found for {ticker}",
                data_quality_flags=[
                    DataFlag(field="ticker", severity="severe",
                             message=f"No data for {ticker}")
                ],
            )
            return {
                "validation": v.model_dump(),
                "hard_veto": True,
                "hard_veto_reason": v.veto_reason,
                "global_flags": [
                    DataFlag(field="ticker", severity="severe",
                             message=f"No data for {ticker}").model_dump()
                ],
            }

        validation = ValidationOutput(
            ticker_valid=True,
            ticker_resolved=ticker.upper(),
            company_name=company_name,
            company_name_match=True,
            exchange=info.get("exchange"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            is_active=True,
        )

        # Build company card
        mc = info.get("marketCap")
        if mc and mc >= 10e9:
            mc_cat = "large_cap"
        elif mc and mc >= 2e9:
            mc_cat = "mid_cap"
        elif mc and mc >= 300e6:
            mc_cat = "small_cap"
        else:
            mc_cat = "micro_cap" if mc else "unknown"

        card = CompanyCard(
            company_name=company_name,
            ticker=ticker.upper(),
            sector=info.get("sector", "Unknown"),
            industry=info.get("industry", "Unknown"),
            description=(info.get("longBusinessSummary") or "")[:500],
            market_cap=mc,
            market_cap_formatted=_fmt_num(mc),
            market_cap_category=mc_cat,
            current_price=info.get("currentPrice") or info.get("regularMarketPrice"),
            revenue=info.get("totalRevenue"),
            profit_margins=info.get("profitMargins"),
            employees=info.get("fullTimeEmployees"),
        )

        return {
            "validation": validation.model_dump(),
            "company_card": card.model_dump(),
        }

    return node


# ---------------------------------------------------------------------------
# Macro Regime
# ---------------------------------------------------------------------------

def create_macro_node(llm):
    """Macro regime analysis node — uses quick LLM."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        macro_data = _fetch_macro_data()
        card = state.get("company_card") or {}
        sector = card.get("sector", "Unknown")

        spy_perf = (macro_data.get("sector_performance") or {}).get("SPY", {})
        sector_perfs = macro_data.get("sector_performance") or {}

        # Build compact sector table
        sector_lines = []
        for etf, data in sorted(sector_perfs.items()):
            r1 = data.get("return_1m")
            name = data.get("name", etf)
            if r1 is not None:
                sector_lines.append(f"  {etf} ({name}): {r1:+.1f}% 1M")

        prompt = f"""You are a Macro Regime Analyst in a structured equity ranking pipeline.

Ticker: {ticker} | Sector: {sector}

MACRO DATA:
- VIX: {macro_data.get('vix_level', 'N/A')}
- 10Y Yield: {macro_data.get('ten_year_yield', 'N/A')}%
- Dollar 1M: {macro_data.get('dollar_1m_return', 'N/A')}%
- Credit Spreads: {macro_data.get('credit_spread_direction', 'N/A')}
- SPY 1M: {spy_perf.get('return_1m', 'N/A')}%

SECTOR PERFORMANCE (1M):
{chr(10).join(sector_lines[:12]) or 'N/A'}

INSTRUCTIONS:
1. Classify risk_appetite: "risk-on" / "risk-off" / "transitional".
   - risk-on: VIX low, spreads tight, SPY up, breadth strong.
   - risk-off: VIX elevated, spreads widening, SPY down, flight to safety.
   - transitional: mixed signals.
2. Classify liquidity_regime: "expansion" / "contraction" / "neutral".
   - expansion: falling yields, dovish Fed, credit flowing, dollar weakening.
   - contraction: rising yields, hawkish Fed, tight credit, dollar strengthening.
3. Set regime_score_adjustment (-10 to +10):
   - +5 to +10 = strong macro tailwind for this specific stock/sector.
   - +1 to +4 = mild tailwind.
   -  0 = neutral.
   - -1 to -4 = mild headwind.
   - -5 to -10 = severe macro headwind (risk-off + contraction + hostile sector).
   This adjustment directly modifies the 0-100 master score for ALL stocks.
4. Score macro_alignment_0_to_10: how well macro supports {ticker} specifically.
5. Also provide score_0_to_10 (overall macro health).
6. Set regime_label: descriptive label (e.g., "Late Cycle Risk-Off").
7. List key positives, negatives, risks. Be concise."""

        try:
            result = invoke_structured(llm, MacroRegimeOutput, prompt)
        except Exception as e:
            logger.warning("Macro LLM call failed: %s", e)
            result = MacroRegimeOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Macro analysis unavailable",
                data_quality_flags=[
                    DataFlag(field="macro", severity="moderate", message=str(e))
                ],
            )

        # Override with actual fetched data
        result.vix_level = macro_data.get("vix_level")
        result.vix_regime = macro_data.get("vix_regime", "unknown")
        result.ten_year_yield = macro_data.get("ten_year_yield")
        result.dollar_strength = macro_data.get("dollar_strength", "unknown")
        result.credit_spread_direction = macro_data.get(
            "credit_spread_direction", "unknown"
        )
        result.spy_1m_return = spy_perf.get("return_1m")

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"macro": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Liquidity
# ---------------------------------------------------------------------------

def create_liquidity_node(llm):
    """Liquidity analysis node — uses quick LLM."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        macro_data = _fetch_macro_data()
        card = state.get("company_card") or {}

        prompt = f"""You are a Liquidity Analyst in a structured equity ranking pipeline.

Ticker: {ticker} | Sector: {card.get('sector', 'Unknown')}

AVAILABLE DATA:
- VIX: {macro_data.get('vix_level', 'N/A')}
- 10Y Yield: {macro_data.get('ten_year_yield', 'N/A')}%
- Credit Spreads: {macro_data.get('credit_spread_direction', 'N/A')}
- Dollar Strength: {macro_data.get('dollar_strength', 'N/A')}

INSTRUCTIONS:
1. Assess Fed stance (dovish / neutral / hawkish) based on yield environment.
2. Assess market breadth (strong / moderate / weak).
3. Assess volume profile (above_average / average / below_average).
4. Assess SPY trend (uptrend / downtrend / sideways).
5. Score overall liquidity favorability 0-10 for this stock.
6. Be concise."""

        try:
            result = invoke_structured(llm, LiquidityOutput, prompt)
        except Exception as e:
            logger.warning("Liquidity LLM call failed: %s", e)
            result = LiquidityOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Liquidity analysis unavailable",
            )

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"liquidity": result.model_dump(), "global_flags": flags}

    return node
