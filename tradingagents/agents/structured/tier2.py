"""Tier 2 agents: Deep analysis that runs only on Tier 1 survivors.

Each agent fetches its own data via yfinance, calls the LLM once with
structured output, and returns a typed result into PipelineState.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import yfinance as yf

from tradingagents.models import (
    ArchetypeOutput,
    BacklogOrderMomentumOutput,
    BusinessQualityOutput,
    DataFlag,
    EarningsRevisionOutput,
    EntryTimingOutput,
    InstitutionalFlowOutput,
    NarrativeCrowdingOutput,
    SectorRotationOutput,
    ValuationOutput,
    invoke_structured,
)

logger = logging.getLogger(__name__)


def _safe(info, key, default=None):
    v = info.get(key)
    return default if v is None else v


def _pct(v):
    return f"{v * 100:.1f}%" if v is not None else "N/A"


# ---------------------------------------------------------------------------
# Business Quality
# ---------------------------------------------------------------------------

def create_business_quality_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        card = state.get("company_card") or {}

        try:
            t = yf.Ticker(ticker.upper())
            info = t.info or {}
        except Exception:
            info = {}

        prompt = f"""You are a Business Quality Analyst in a structured equity ranking pipeline.

Ticker: {ticker} | Sector: {card.get('sector', 'Unknown')} | Industry: {card.get('industry', 'Unknown')}
Market Cap: {card.get('market_cap_formatted', 'N/A')}

FINANCIALS:
- Revenue Growth: {_pct(_safe(info, 'revenueGrowth'))}
- Profit Margins: {_pct(_safe(info, 'profitMargins'))}
- Operating Margins: {_pct(_safe(info, 'operatingMargins'))}
- ROE: {_pct(_safe(info, 'returnOnEquity'))}
- ROA: {_pct(_safe(info, 'returnOnAssets'))}
- Debt/Equity: {_safe(info, 'debtToEquity', 'N/A')}
- Free Cash Flow: {_safe(info, 'freeCashflow', 'N/A')}
- Current Ratio: {_safe(info, 'currentRatio', 'N/A')}

INSTRUCTIONS:
1. Score business quality 0-10 based on margins, growth, returns, balance sheet.
2. Classify competitive moat: wide / narrow / none.
3. Classify management quality: strong / adequate / weak.
4. List positives, negatives, risks. Be concise."""

        try:
            result = invoke_structured(llm, BusinessQualityOutput, prompt)
        except Exception as e:
            logger.warning("BusinessQuality LLM failed: %s", e)
            result = BusinessQualityOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Business quality analysis unavailable",
            )

        # Override with actual data
        result.revenue_growth = _safe(info, "revenueGrowth")
        result.profit_margins = _safe(info, "profitMargins")
        result.operating_margins = _safe(info, "operatingMargins")
        result.return_on_equity = _safe(info, "returnOnEquity")
        result.return_on_assets = _safe(info, "returnOnAssets")
        result.debt_to_equity = _safe(info, "debtToEquity")
        result.free_cashflow = _safe(info, "freeCashflow")

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"business_quality": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Institutional Flow
# ---------------------------------------------------------------------------

def create_institutional_flow_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]

        from tradingagents.dataflows.y_finance import get_institutional_flow
        try:
            raw = get_institutional_flow(ticker)
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}

        # Format top holders for prompt
        holders = data.get("top_institutional_holders", [])
        holder_lines = []
        for h in holders[:5]:
            pct = h.get("pct_out")
            holder_lines.append(
                f"  {h.get('holder', '?')}: {pct:.1f}%" if pct else f"  {h.get('holder', '?')}"
            )

        prompt = f"""You are an Institutional Flow Analyst in a structured equity ranking pipeline.
Your job: track real smart-money movement — not just static ownership percentages.

Ticker: {ticker}

OWNERSHIP & VOLUME:
- Institutional Ownership: {data.get('held_percent_institutions', 'N/A')}%
- Insider Ownership: {data.get('held_percent_insiders', 'N/A')}%
- Volume Ratio (10d/avg): {data.get('volume_ratio', 'N/A')}
- Short % of Float: {data.get('short_pct_of_float', 'N/A')}%
- Short Ratio (days): {data.get('short_ratio', 'N/A')}
- Float Turnover 5d: {data.get('float_turnover_5d_pct', 'N/A')}%

SHORT INTEREST TREND:
- Short Interest Change (vs prior month): {data.get('short_interest_change_pct', 'N/A')}%
- Short Interest Trend: {data.get('short_interest_trend', 'N/A')}

TOP INSTITUTIONAL HOLDERS (13F):
{chr(10).join(holder_lines) or '  No data available'}
- Total top holders tracked: {data.get('top_holders_count', 'N/A')}

INSIDER TRANSACTIONS (recent):
- Insider Buys: {data.get('insider_buys_recent', 'N/A')}
- Insider Sells: {data.get('insider_sells_recent', 'N/A')}
- Insider Signal: {data.get('insider_transaction_signal', 'N/A')}

INSTRUCTIONS:
1. Score institutional flow signal 0-10 (this has 15% weight — make it count).
   High ownership + rising volume + low short interest + insider buying = bullish.
2. Classify accumulation_signal: accumulating / distributing / neutral.
3. Classify top_holders_change: increasing / decreasing / stable.
   (Based on holder concentration and any visible 13F patterns.)
4. Classify fund_accumulation_pattern: accumulating / distributing / holding.
   (Volume + ownership trends suggest funds are adding or reducing.)
5. Classify short_interest_trend: rising / falling / stable.
6. Classify insider_transaction_signal: buying / selling / none.
7. Classify smart_money_signal: bullish / bearish / neutral.
   (Synthesize all signals: 13F, insiders, short interest, volume.)
8. Be concise."""

        try:
            result = invoke_structured(llm, InstitutionalFlowOutput, prompt)
        except Exception as e:
            logger.warning("InstitutionalFlow LLM failed: %s", e)
            result = InstitutionalFlowOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Institutional flow analysis unavailable",
            )

        # Override with actual fetched data
        result.institutional_ownership_pct = data.get("held_percent_institutions")
        result.insider_ownership_pct = data.get("held_percent_insiders")
        result.volume_ratio = data.get("volume_ratio")
        result.short_interest_pct = data.get("short_pct_of_float")
        result.short_ratio = data.get("short_ratio")
        result.float_turnover_pct = data.get("float_turnover_5d_pct")
        # Override trend fields with actual data when available
        if data.get("short_interest_trend"):
            result.short_interest_trend = data["short_interest_trend"]
        if data.get("insider_transaction_signal"):
            result.insider_transaction_signal = data["insider_transaction_signal"]

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"institutional_flow": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

def create_valuation_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]

        from tradingagents.dataflows.y_finance import get_valuation_peers
        try:
            raw = get_valuation_peers(ticker)
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}

        prompt = f"""You are a Valuation Analyst in a structured equity ranking pipeline.

Ticker: {ticker}

VALUATION METRICS:
- Trailing P/E: {data.get('trailing_pe', 'N/A')}
- Forward P/E: {data.get('forward_pe', 'N/A')}
- PEG Ratio: {data.get('peg_ratio', 'N/A')}
- P/B: {data.get('price_to_book', 'N/A')}
- EV/EBITDA: {data.get('ev_to_ebitda', 'N/A')}
- P/S: {data.get('price_to_sales', 'N/A')}
- 52W Range Position: {data.get('vs_52w_range_pct', 'N/A')}%
- Revenue Growth: {data.get('revenue_growth', 'N/A')}
- Earnings Growth: {data.get('earnings_growth', 'N/A')}

INSTRUCTIONS:
1. Score valuation attractiveness 0-10.
   Low multiples relative to growth = high score.
2. Classify: undervalued / fair / overvalued.
3. Consider industry context (growth stocks deserve higher multiples)."""

        try:
            result = invoke_structured(llm, ValuationOutput, prompt)
        except Exception as e:
            logger.warning("Valuation LLM failed: %s", e)
            result = ValuationOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Valuation analysis unavailable",
            )

        result.trailing_pe = data.get("trailing_pe")
        result.forward_pe = data.get("forward_pe")
        result.peg_ratio = data.get("peg_ratio")
        result.price_to_book = data.get("price_to_book")
        result.ev_to_ebitda = data.get("ev_to_ebitda")
        result.price_to_sales = data.get("price_to_sales")
        result.vs_52w_range_pct = data.get("vs_52w_range_pct")

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"valuation": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Entry Timing
# ---------------------------------------------------------------------------

def create_entry_timing_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]

        price = ma50 = ma200 = hi52 = lo52 = range_pct = None

        # Try Alpaca first (computed from actual bar data — more reliable than yfinance info)
        try:
            from tradingagents.dataflows.alpaca_data import alpaca_available, get_moving_averages
            if alpaca_available():
                ma_data = get_moving_averages(ticker)
                if ma_data:
                    price = ma_data.get("current_price")
                    ma50 = ma_data.get("fifty_day_avg")
                    ma200 = ma_data.get("two_hundred_day_avg")
                    hi52 = ma_data.get("fifty_two_week_high")
                    lo52 = ma_data.get("fifty_two_week_low")
                    range_pct = ma_data.get("vs_52w_range_pct")
        except Exception as e:
            logger.debug("Alpaca MAs failed for %s: %s", ticker, e)

        # Fallback: yfinance info
        if price is None:
            try:
                t = yf.Ticker(ticker.upper())
                info = t.info or {}
            except Exception:
                info = {}

            price = _safe(info, "currentPrice") or _safe(info, "regularMarketPrice")
            ma50 = _safe(info, "fiftyDayAverage")
            ma200 = _safe(info, "twoHundredDayAverage")
            hi52 = _safe(info, "fiftyTwoWeekHigh")
            lo52 = _safe(info, "fiftyTwoWeekLow")

            if hi52 and lo52 and price and (hi52 - lo52) > 0:
                range_pct = round(((price - lo52) / (hi52 - lo52)) * 100, 1)

        ma_rel = "unknown"
        if ma50 and ma200:
            ma_rel = "above" if ma50 > ma200 else "below"

        prompt = f"""You are an Entry Timing Analyst in a structured equity ranking pipeline.

Ticker: {ticker}

TECHNICALS:
- Price: ${price or 'N/A'}
- 50-day MA: ${ma50 or 'N/A'}
- 200-day MA: ${ma200 or 'N/A'}
- 50d vs 200d: {ma_rel}
- 52W High: ${hi52 or 'N/A'}
- 52W Low: ${lo52 or 'N/A'}
- Position in 52W Range: {range_pct or 'N/A'}%

INSTRUCTIONS:
1. Score entry timing 0-10.
   Pullback to support in uptrend = high score. Overextended at highs = low score.
2. Classify timing_verdict: favorable / neutral / unfavorable.
3. Be concise."""

        try:
            result = invoke_structured(llm, EntryTimingOutput, prompt)
        except Exception as e:
            logger.warning("EntryTiming LLM failed: %s", e)
            result = EntryTimingOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Entry timing analysis unavailable",
            )

        result.current_price = price
        result.fifty_day_avg = ma50
        result.two_hundred_day_avg = ma200
        result.fifty_day_vs_200_day = ma_rel
        result.vs_52w_range_pct = range_pct

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"entry_timing": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Earnings Revisions
# ---------------------------------------------------------------------------

def create_earnings_revisions_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]

        from tradingagents.dataflows.y_finance import get_earnings_estimates
        try:
            raw = get_earnings_estimates(ticker)
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}

        recs = data.get("recent_recommendations", [])
        targets = data.get("price_targets", {})
        upside = data.get("price_target_upside_pct")

        prompt = f"""You are an Earnings Revisions Analyst in a structured equity ranking pipeline.

Ticker: {ticker}

EARNINGS DATA:
- Trailing EPS: {data.get('trailing_eps', 'N/A')}
- Forward EPS: {data.get('forward_eps', 'N/A')}
- Price Target Upside: {upside or 'N/A'}%
- Price Targets: {json.dumps(targets)[:300] if targets else 'N/A'}
- Recent Recommendations: {len(recs)} entries

INSTRUCTIONS:
1. Score earnings revision momentum 0-10.
   Rising estimates + strong buy consensus + upside = high score.
2. Classify eps_revision_direction: up / down / flat.
3. Classify revenue_revision_direction: up / down / flat.
4. Classify analyst_consensus: strong_buy / buy / hold / sell / strong_sell.
5. This score has 10% weight in the master score — must materially affect it."""

        try:
            result = invoke_structured(llm, EarningsRevisionOutput, prompt)
        except Exception as e:
            logger.warning("EarningsRevisions LLM failed: %s", e)
            result = EarningsRevisionOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Earnings revision analysis unavailable",
            )

        result.trailing_eps = data.get("trailing_eps")
        result.forward_eps = data.get("forward_eps")
        result.price_target_upside_pct = upside

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"earnings_revisions": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Sector Rotation
# ---------------------------------------------------------------------------

def create_sector_rotation_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]

        from tradingagents.dataflows.y_finance import get_sector_rotation
        try:
            raw = get_sector_rotation(ticker)
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}

        prompt = f"""You are a Sector Rotation Analyst in a structured equity ranking pipeline.

Ticker: {ticker} | Sector: {data.get('sector', 'Unknown')} | Sector ETF: {data.get('sector_etf', 'N/A')}

SECTOR DATA:
- Sector vs SPY 1M: {data.get('stock_sector_vs_spy_1m', 'N/A')}%
- Sector vs SPY 3M: {data.get('stock_sector_vs_spy_3m', 'N/A')}%
- Sector Rank: {data.get('stock_sector_rank', 'N/A')} / {data.get('total_sectors', 11)}

INSTRUCTIONS:
1. Score sector rotation favorability 0-10.
   Top-ranked sector with positive relative strength = high score.
2. Classify rotation_direction: inflow / outflow / neutral.
3. Be concise."""

        try:
            result = invoke_structured(llm, SectorRotationOutput, prompt)
        except Exception as e:
            logger.warning("SectorRotation LLM failed: %s", e)
            result = SectorRotationOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.1,
                summary_1_sentence="Sector rotation analysis unavailable",
            )

        result.sector = data.get("sector", "Unknown")
        result.sector_etf = data.get("sector_etf")
        result.sector_vs_spy_1m = data.get("stock_sector_vs_spy_1m")
        result.sector_vs_spy_3m = data.get("stock_sector_vs_spy_3m")
        result.sector_rank = data.get("stock_sector_rank")

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"sector_rotation": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Backlog / Order Momentum
# ---------------------------------------------------------------------------

def create_backlog_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        card = state.get("company_card") or {}
        sector = card.get("sector", "Unknown")
        industry = card.get("industry", "Unknown")

        # Backlog data is limited via yfinance — use revenue trajectory as proxy
        try:
            t = yf.Ticker(ticker.upper())
            info = t.info or {}
        except Exception:
            info = {}

        prompt = f"""You are a Backlog / Order Momentum Analyst in a structured equity ranking pipeline.

Ticker: {ticker} | Sector: {sector} | Industry: {industry}

AVAILABLE DATA:
- Revenue Growth: {_pct(_safe(info, 'revenueGrowth'))}
- Earnings Growth: {_pct(_safe(info, 'earningsGrowth'))}
- Revenue: {_safe(info, 'totalRevenue', 'N/A')}

INSTRUCTIONS:
1. Assess if this company type typically has meaningful backlog data
   (defense, industrials, semiconductors = yes; consumer, finance = no).
2. Score order momentum 0-10 based on revenue trajectory and industry context.
3. Set has_backlog_data=true only if this industry typically reports backlog.
4. This has 5% weight — be quick and concise."""

        try:
            result = invoke_structured(llm, BacklogOrderMomentumOutput, prompt)
        except Exception as e:
            logger.warning("Backlog LLM failed: %s", e)
            result = BacklogOrderMomentumOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.3,
                summary_1_sentence="Backlog analysis limited",
            )

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"backlog": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Narrative Crowding
# ---------------------------------------------------------------------------

def create_crowding_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state["ticker"]
        card = state.get("company_card") or {}

        try:
            t = yf.Ticker(ticker.upper())
            info = t.info or {}
        except Exception:
            info = {}

        short_pct = None
        float_shares = _safe(info, "floatShares")
        shares_short = _safe(info, "sharesShort")
        if float_shares and shares_short and float_shares > 0:
            short_pct = round(shares_short / float_shares * 100, 2)

        prompt = f"""You are a Narrative Crowding Analyst in a structured equity ranking pipeline.

Ticker: {ticker} | Company: {card.get('company_name', 'Unknown')}
Market Cap Category: {card.get('market_cap_category', 'unknown')}

DATA:
- Short % of Float: {short_pct or 'N/A'}%
- Short Ratio (days): {_safe(info, 'shortRatio', 'N/A')}
- Analyst Coverage: implied from market cap ({card.get('market_cap_category', 'unknown')})

INSTRUCTIONS:
1. Score narrative crowding 0-10.
   HIGH score = low crowding (contrarian, under-followed).
   LOW score = extremely crowded (everyone owns it, consensus trade).
2. Assess narrative_saturation: low / moderate / high.
3. Flag contrarian_opportunity if stock is hated but fundamentals are intact.
4. Flag short_squeeze_potential if short interest is high (>15% of float).
5. This has 5% weight — be concise."""

        try:
            result = invoke_structured(llm, NarrativeCrowdingOutput, prompt)
        except Exception as e:
            logger.warning("Crowding LLM failed: %s", e)
            result = NarrativeCrowdingOutput(
                score_0_to_10=5.0, confidence_0_to_1=0.3,
                summary_1_sentence="Crowding analysis limited",
            )

        flags = [f.model_dump() for f in result.data_quality_flags]
        return {"crowding": result.model_dump(), "global_flags": flags}

    return node


# ---------------------------------------------------------------------------
# Archetype
# ---------------------------------------------------------------------------

def create_archetype_node(llm):

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        card = state.get("company_card") or {}
        bq = state.get("business_quality") or {}

        prompt = f"""You are a Company Archetype Classifier.

Company: {card.get('company_name', 'Unknown')} ({card.get('ticker', '?')})
Sector: {card.get('sector', 'Unknown')} | Industry: {card.get('industry', 'Unknown')}
Market Cap: {card.get('market_cap_formatted', 'N/A')}
Description: {card.get('description', 'N/A')[:300]}

Competitive Moat: {bq.get('competitive_moat', 'N/A')}
Revenue Growth: {bq.get('revenue_growth', 'N/A')}

ARCHETYPES (pick exactly one):
- Infrastructure Builder: builds platforms/networks others depend on
- Bottleneck Supplier: controls scarce supply in a critical chain
- Platform Company: multi-sided marketplace with network effects
- Commodity Leverage: earnings levered to commodity prices
- Secular Growth Innovator: disrupting with new tech/business model
- Turnaround: beaten-down company with improving fundamentals
- Defensive Compounder: steady earnings, dividend grower, low vol

Return archetype, confidence (0-1), and one-sentence reasoning."""

        try:
            result = invoke_structured(llm, ArchetypeOutput, prompt)
        except Exception as e:
            logger.warning("Archetype LLM failed: %s", e)
            result = ArchetypeOutput()

        return {"archetype": result.model_dump()}

    return node
