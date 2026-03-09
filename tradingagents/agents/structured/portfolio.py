"""Portfolio-level agents: Theme Substitution Engine, Position Replacement Agent.

These run after scoring, before the debate phase. They use the deep-thinking LLM
to evaluate the stock in context — is it the best expression of its theme? Should
it replace an existing holding?
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import yfinance as yf

from tradingagents.models import (
    PositionReplacementOutput,
    ThemeStock,
    ThemeSubstitutionOutput,
    invoke_structured,
)

logger = logging.getLogger(__name__)


def _fetch_peer_basics(tickers: List[str]) -> List[dict]:
    """Fetch basic yfinance data for a list of peer tickers."""
    peers = []
    for sym in tickers[:8]:  # cap at 8 to keep prompt manageable
        try:
            info = yf.Ticker(sym.upper()).info or {}
            peers.append({
                "ticker": sym.upper(),
                "company_name": info.get("longName") or info.get("shortName") or sym,
                "market_cap": info.get("marketCap"),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "revenue_growth": info.get("revenueGrowth"),
                "profit_margins": info.get("profitMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "52w_range_pct": _range_pct(info),
            })
        except Exception:
            peers.append({"ticker": sym.upper(), "error": "fetch failed"})
    return peers


def _range_pct(info: dict) -> float | None:
    hi = info.get("fiftyTwoWeekHigh")
    lo = info.get("fiftyTwoWeekLow")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if hi and lo and price and (hi - lo) > 0:
        return round((price - lo) / (hi - lo) * 100, 1)
    return None


def _summarize_for_theme(state: Dict[str, Any]) -> str:
    """Compact summary of the candidate stock for theme comparison."""
    card = state.get("company_card") or {}
    macro = state.get("macro") or {}
    bq = state.get("business_quality") or {}
    inst = state.get("institutional_flow") or {}
    val = state.get("valuation") or {}
    er = state.get("earnings_revisions") or {}
    arch = state.get("archetype") or {}

    return "\n".join([
        f"Ticker: {card.get('ticker', '?')} | {card.get('company_name', '?')}",
        f"Sector: {card.get('sector', '?')} | Industry: {card.get('industry', '?')}",
        f"Market Cap: {card.get('market_cap_formatted', 'N/A')}",
        f"Archetype: {arch.get('archetype', 'N/A')}",
        f"Master Score: {state.get('master_score', 'N/A')}",
        f"Adjusted Score: {state.get('adjusted_score', 'N/A')}",
        f"Position Role: {state.get('position_role', 'N/A')}",
        f"Macro Regime: {macro.get('regime_label', '?')} | Risk: {macro.get('risk_appetite', '?')} | Liq: {macro.get('liquidity_regime', '?')}",
        f"Business Quality: {bq.get('score_0_to_10', 'N/A')} | Moat: {bq.get('competitive_moat', '?')}",
        f"Inst Flow: {inst.get('score_0_to_10', 'N/A')} | Smart Money: {inst.get('smart_money_signal', '?')}",
        f"Valuation: {val.get('score_0_to_10', 'N/A')} | Verdict: {val.get('valuation_verdict', '?')}",
        f"Earnings Rev: {er.get('score_0_to_10', 'N/A')} | Direction: {er.get('eps_revision_direction', '?')}",
    ])


# ---------------------------------------------------------------------------
# Theme Substitution Engine
# ---------------------------------------------------------------------------

def create_theme_substitution_node(llm):
    """Identifies whether the stock is the best expression of its theme."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        card = state.get("company_card") or {}
        summary = _summarize_for_theme(state)
        master_score = state.get("master_score", 0)

        # Use yfinance to find peers in the same industry
        try:
            t = yf.Ticker(ticker.upper())
            info = t.info or {}
            industry = info.get("industry", "")
            sector = info.get("sector", "")
        except Exception:
            industry = card.get("industry", "")
            sector = card.get("sector", "")

        # Fetch competitor/peer data to ground the LLM's comparison
        competitors = card.get("competitors") or []
        peer_data = _fetch_peer_basics(competitors) if competitors else []
        peer_summary = ""
        if peer_data:
            lines = []
            for p in peer_data:
                if p.get("error"):
                    continue
                rg = p.get("revenue_growth")
                rg_str = f"{rg*100:.1f}%" if rg else "N/A"
                pm = p.get("profit_margins")
                pm_str = f"{pm*100:.1f}%" if pm else "N/A"
                lines.append(
                    f"  {p['ticker']}: P/E={p.get('trailing_pe', 'N/A')}, "
                    f"Fwd P/E={p.get('forward_pe', 'N/A')}, "
                    f"RevGrowth={rg_str}, "
                    f"Margins={pm_str}, "
                    f"52W={p.get('52w_range_pct', 'N/A')}%"
                )
            peer_summary = "\n".join(lines)

        theme_prompt = f"""You are a Theme Substitution Analyst. Your job: determine if {ticker} is the BEST
expression of its investment theme, or if better alternatives exist.

CANDIDATE STOCK:
{summary}

{f'PEER FUNDAMENTALS (live data):{chr(10)}{peer_summary}' if peer_summary else 'No live peer data available — use your knowledge of these companies.'}

INSTRUCTIONS — do this in order:

1. IDENTIFY THE THEME: What macro/sector theme does {ticker} express?
   Examples: "AI infrastructure buildout", "GLP-1 obesity drugs", "defense spending ramp",
   "EV supply chain", "cloud migration", "reshoring/nearshoring".
   Name it clearly in theme_name.

2. LIST THEME PEERS: Name 3-6 other publicly traded stocks that express the SAME theme.
   Use the peer data above if available. These should be the strongest competitors
   for capital allocation in this theme.
   For each peer, score master_score_estimate (0-10) based on fundamentals, momentum,
   and positioning vs {ticker}.

3. RANK WITHIN THEME: Rank all stocks (including {ticker}) by investment quality.
   The stock with the best combination of: business quality, valuation, momentum,
   and institutional positioning should rank #1.

4. DETERMINE BEST EXPRESSION:
   - Set best_expression_of_theme=true if {ticker} is rank #1 or close (#1-2).
   - Set best_expression_of_theme=false if clearly better alternatives exist.
   - List stronger_alternatives (tickers that rank above {ticker}).
   - Set relative_score_gap: how many score points {ticker} trails the best alternative
     (0 if {ticker} is best, positive number if it trails).

5. PORTFOLIO OVERLAP: Flag if {ticker} has high correlation with common holdings.
   Set portfolio_overlap_warning if this stock would add redundant exposure.

Be honest and rigorous. A stock can score well absolutely but still not be the best
way to express its theme."""

        try:
            result = invoke_structured(llm, ThemeSubstitutionOutput, theme_prompt)
        except Exception as e:
            logger.warning("ThemeSubstitution LLM failed: %s", e)
            result = ThemeSubstitutionOutput(
                theme_name="Unknown",
                best_expression_of_theme=True,
                reasoning="Theme analysis unavailable",
            )

        return {"theme_substitution": result.model_dump()}

    return node


# ---------------------------------------------------------------------------
# Position Replacement Agent
# ---------------------------------------------------------------------------

def create_position_replacement_node(llm):
    """Identifies when a new stock is a better use of capital than alternatives."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        summary = _summarize_for_theme(state)
        master_score = state.get("master_score", 0)
        theme = state.get("theme_substitution") or {}

        # Get the strongest alternative from theme analysis
        stronger = theme.get("stronger_alternatives", [])
        theme_stocks = theme.get("theme_stocks_ranked", [])
        theme_name = theme.get("theme_name", "Unknown")

        # If no stronger alternatives, this IS the best — skip deep comparison
        if not stronger and theme.get("best_expression_of_theme", True):
            result = PositionReplacementOutput(
                replace_candidate=ticker,
                replace_with="",
                score_difference=0.0,
                theme_overlap=theme_name,
                replacement_reason=f"{ticker} is the best expression of the '{theme_name}' theme.",
                conviction_level="high",
                should_replace=False,
            )
            return {"position_replacement": result.model_dump()}

        # Format theme peers for comparison
        peer_lines = []
        for ts in theme_stocks[:6]:
            if isinstance(ts, dict):
                peer_lines.append(
                    f"  {ts.get('ticker', '?')}: est. score {ts.get('master_score_estimate', '?')}/10 "
                    f"— advantage: {ts.get('key_advantage', 'N/A')}, weakness: {ts.get('key_weakness', 'N/A')}"
                )

        prompt = f"""You are a Position Replacement Analyst. Determine if {ticker} should be replaced
by a stronger alternative in the same theme.

CANDIDATE STOCK:
{summary}

THEME: {theme_name}
Best expression: {'Yes' if theme.get('best_expression_of_theme') else 'No'}
Score gap vs best: {theme.get('relative_score_gap', 0):.1f}

THEME PEERS:
{chr(10).join(peer_lines) or 'No peers available'}

STRONGER ALTERNATIVES: {', '.join(stronger) if stronger else 'None'}

INSTRUCTIONS:
1. Compare {ticker} to the strongest alternative in the theme.
2. Assess on these dimensions: master score, earnings revisions, institutional flow,
   risk profile, valuation, entry timing.
3. Set replace_with to the best alternative ticker (empty if none).
4. Set score_difference: how much better the replacement is (positive = replacement is stronger).
5. Set conviction_level: high / medium / low.
   - high: replacement is clearly better on 3+ dimensions.
   - medium: replacement is better on 1-2 dimensions, mixed on others.
   - low: marginal difference, keep current.
6. Set should_replace=true only if conviction_level is high.
7. List what the replacement is stronger_on and weaker_on vs {ticker}.

Be conservative. Don't recommend replacement for marginal differences."""

        try:
            result = invoke_structured(llm, PositionReplacementOutput, prompt)
        except Exception as e:
            logger.warning("PositionReplacement LLM failed: %s", e)
            result = PositionReplacementOutput(
                replace_candidate=ticker,
                should_replace=False,
                replacement_reason="Position replacement analysis unavailable",
            )

        result.replace_candidate = ticker
        result.theme_overlap = theme_name

        return {"position_replacement": result.model_dump()}

    return node
