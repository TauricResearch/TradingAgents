import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from tradingagents.dataflows.discovery.discovery_config import DiscoveryConfig
from tradingagents.dataflows.discovery.utils import append_llm_log, resolve_llm_name
from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


def extract_json_from_markdown(text: str) -> Optional[str]:
    """
    Extract JSON from markdown code blocks.

    Handles cases where LLMs return JSON wrapped in ```json...``` or just ```...```
    """
    if not text:
        return None

    # Try to find JSON in markdown code blocks
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",  # ```json ... ```
        r"```\s*([\s\S]*?)\s*```",  # ``` ... ```
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # If no code blocks, check if the text itself is valid JSON
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text

    return None


class StockRanking(BaseModel):
    """Single stock ranking."""

    rank: int = Field(description="Rank 1-N")
    ticker: str = Field(description="Stock ticker symbol")
    company_name: str = Field(description="Company name")
    current_price: float = Field(description="Current stock price")
    strategy_match: str = Field(description="Strategy that matched")
    final_score: int = Field(description="Score 0-100")
    confidence: int = Field(description="Confidence 1-10")
    risk_level: str = Field(description="Risk level: low, moderate, high, or speculative")
    reason: str = Field(
        description="Detailed investment thesis (4-6 sentences) defending the trade with specific catalysts, risk/reward, and timing"
    )
    description: str = Field(description="Company description")


class RankingResponse(BaseModel):
    """LLM ranking response."""

    rankings: List[StockRanking] = Field(description="List of ranked stocks")


class CandidateRanker:
    """
    Handles ranking of filtered candidates using Deep Thinking LLM.
    """

    def __init__(self, config: Dict[str, Any], llm: BaseChatModel, analytics: Any):
        self.config = config
        self.llm = llm
        self.analytics = analytics

        dc = DiscoveryConfig.from_config(config)
        self.max_candidates_to_analyze = dc.ranker.max_candidates_to_analyze
        self.final_recommendations = dc.ranker.final_recommendations
        self.min_score_threshold = dc.ranker.min_score_threshold
        self.return_target_pct = dc.ranker.return_target_pct
        self.holding_period_days = dc.ranker.holding_period_days

        # Truncation settings
        self.truncate_context = dc.ranker.truncate_ranking_context
        self.max_news_chars = dc.ranker.max_news_chars
        self.max_insider_chars = dc.ranker.max_insider_chars
        self.max_recommendations_chars = dc.ranker.max_recommendations_chars

        # Prompt logging
        self.log_prompts_console = dc.logging.log_prompts_console

    def rank(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Rank all filtered candidates and select the top opportunities."""
        candidates = state.get("candidate_metadata", [])
        trade_date = state.get("trade_date", datetime.now().strftime("%Y-%m-%d"))

        if len(candidates) == 0:
            logger.warning("⚠️ No candidates to rank.")
            return {
                "opportunities": [],
                "final_ranking": "[]",
                "status": "complete",
                "tool_logs": state.get("tool_logs", []),
            }

        # Limit candidates to prevent token overflow
        max_candidates = min(self.max_candidates_to_analyze, 200)
        if len(candidates) > max_candidates:
            logger.warning(
                f"⚠️ Too many candidates ({len(candidates)}), limiting to top {max_candidates} by priority"
            )
            candidates = candidates[:max_candidates]

        logger.info(
            f"🏆 Ranking {len(candidates)} candidates to select top {self.final_recommendations}..."
        )

        # Load historical performance statistics
        historical_stats = self.analytics.load_historical_stats()
        if historical_stats.get("available"):
            logger.info(
                f"📊 Loaded historical stats: {historical_stats.get('total_tracked', 0)} tracked recommendations"
            )

        # Build RICH context for each candidate
        candidate_summaries = []
        for cand in candidates:
            ticker = cand.get("ticker", "UNKNOWN")
            strategy = cand.get("strategy", "unknown")
            priority = cand.get("priority", "unknown")
            context = cand.get("context", "No context available")
            all_sources = cand.get("all_sources", [cand.get("source", "unknown")])
            technical_indicators = cand.get("technical_indicators", "")
            avg_volume = cand.get("average_volume", "N/A")
            intraday_change = cand.get("intraday_change_pct", "N/A")
            current_price = cand.get("current_price")

            # Formatting helpers
            volume_str = (
                f"{avg_volume:,.0f}" if isinstance(avg_volume, (int, float)) else str(avg_volume)
            )
            intraday_str = (
                f"{intraday_change:+.1f}%"
                if isinstance(intraday_change, (int, float))
                else str(intraday_change)
            )
            price_str = f"${current_price:.2f}" if current_price else "N/A"

            # Use fundamentals already fetched - pass more complete data
            fund = cand.get("fundamentals", {})
            fundamentals_summary = self._format_fundamentals_expanded(fund)

            # Use full technical indicators instead of extracting only RSI
            tech_summary = (
                technical_indicators if technical_indicators else "No technical data available."
            )

            # Get options activity
            options_activity = cand.get("options_activity", "")

            # Get business description for context
            business_description = cand.get("business_description", "")

            # News summary - handle both batch news (string) and discovery news (list of dicts)
            news_items = cand.get("news", [])
            news_summary = ""
            if isinstance(news_items, list) and news_items:
                # List format from discovery scanner
                headlines = []
                for item in news_items[:3]:
                    if isinstance(item, dict):
                        # Discovery news format: {'news_title': '...', 'news_summary': '...', 'sentiment': '...', 'published_at': '...'}
                        title = item.get("news_title", item.get("title", ""))
                        summary = item.get("news_summary", "")
                        # Get timestamp from various possible fields
                        timestamp = item.get("published_at") or item.get("timestamp") or ""
                        # Format timestamp for display (extract date/time portion)
                        time_str = self._format_news_timestamp(timestamp)
                        if title:
                            if time_str:
                                headlines.append(
                                    f"[{time_str}] {title}: {summary}"
                                    if summary
                                    else f"[{time_str}] {title}"
                                )
                            else:
                                headlines.append(f"{title}: {summary}" if summary else title)
                    elif isinstance(item, str):
                        headlines.append(item)
                news_summary = "; ".join(headlines) if headlines else ""
            elif isinstance(news_items, str):
                news_summary = news_items

            # Apply truncation if configured
            if self.truncate_context and self.max_news_chars > 0:
                if len(news_summary) > self.max_news_chars:
                    news_summary = news_summary[: self.max_news_chars] + "..."

            source_str = (
                ", ".join(all_sources) if isinstance(all_sources, list) else str(all_sources)
            )

            # Format insider/analyst data
            insider_text = cand.get("insider_transactions", "N/A")
            recommendations_text = cand.get("recommendations", "N/A")

            # Apply truncation if configured
            if self.truncate_context:
                if (
                    self.max_insider_chars > 0
                    and isinstance(insider_text, str)
                    and len(insider_text) > self.max_insider_chars
                ):
                    insider_text = insider_text[: self.max_insider_chars] + "..."
                if (
                    self.max_recommendations_chars > 0
                    and isinstance(recommendations_text, str)
                    and len(recommendations_text) > self.max_recommendations_chars
                ):
                    recommendations_text = (
                        recommendations_text[: self.max_recommendations_chars] + "..."
                    )

            # New enrichment fields
            confluence_score = cand.get("confluence_score", 1)
            quant_score = cand.get("quant_score", "N/A")
            z_score = cand.get("z_score", "N/A")
            f_score = cand.get("f_score", "N/A")

            # ML prediction
            ml_win_prob = cand.get("ml_win_probability")
            ml_prediction = cand.get("ml_prediction")
            if ml_win_prob is not None:
                ml_str = f"{ml_win_prob:.1%} (Predicted: {ml_prediction})"
            else:
                ml_str = "N/A"
            short_interest_pct = cand.get("short_interest_pct")
            high_short = cand.get("high_short_interest", False)
            short_str = f"{short_interest_pct:.1f}%" if short_interest_pct else "N/A"
            if high_short:
                short_str += " (HIGH)"

            # Earnings estimate
            if cand.get("has_upcoming_earnings"):
                days = cand.get("days_to_earnings", "?")
                eps_est = cand.get("eps_estimate")
                rev_est = cand.get("revenue_estimate")
                earnings_date = cand.get("earnings_date", "N/A")
                eps_str = f"${eps_est:.2f}" if isinstance(eps_est, (int, float)) else "N/A"
                rev_str = f"${rev_est:,.0f}" if isinstance(rev_est, (int, float)) else "N/A"
                earnings_section = f"Earnings in {days} days ({earnings_date}): EPS Est {eps_str}, Rev Est {rev_str}"
            else:
                earnings_section = "No upcoming earnings within 30 days"

            summary = f"""### {ticker} (Priority: {priority.upper()})
- **Strategy Match**: {strategy}
- **Sources**: {source_str} | **Confluence**: {confluence_score} source(s)
- **Quant Pre-Score**: {quant_score}/100 | **ML Win Probability**: {ml_str} | **Altman Z-Score**: {z_score} | **Piotroski F-Score**: {f_score}
- **Price**: {price_str} | **Current Price (numeric)**: {current_price if isinstance(current_price, (int, float)) else "N/A"} | **Intraday**: {intraday_str} | **Avg Volume**: {volume_str}
- **Short Interest**: {short_str}
- **Discovery Context**: {context}
- **Business**: {business_description}
- **News**: {news_summary}

**Technical Analysis**:
{tech_summary}

**Fundamentals**: {fundamentals_summary}

**Insider Transactions**:
{insider_text}

**Analyst Recommendations**:
{recommendations_text}

**Options Activity**:
{options_activity if options_activity else "N/A"}

**Upcoming Earnings**: {earnings_section}
"""
            candidate_summaries.append(summary)

        combined_candidates_text = "\n".join(candidate_summaries)

        # Build Prompt
        prompt = f"""You are a professional stock analyst selecting the best short-term trading opportunities from a pre-filtered candidate list.

CURRENT DATE: {trade_date}

GOAL: Select UP TO {self.final_recommendations} stocks with the highest probability of generating >{self.return_target_pct}% returns within {self.holding_period_days} days. If fewer than {self.final_recommendations} candidates meet the quality bar, return only the ones that do. Quality over quantity — never pad the list with weak picks.

MINIMUM QUALITY BAR:
- Only include candidates where you have genuine conviction (final_score >= {self.min_score_threshold}).
- If a candidate lacks a clear catalyst or has contradictory signals, SKIP it.
- It is better to return 5 excellent picks than 15 mediocre ones.

STRATEGY-SPECIFIC EVALUATION CRITERIA:
Each candidate was discovered by a specific scanner. Evaluate them using the criteria most relevant to their strategy:
- **insider_buying**: Focus on insider transaction SIZE relative to market cap, insider ROLE (CEO/CFO > Director), number of distinct insiders buying, and whether the stock is near support. Large cluster buys are strongest.
- **options_flow**: Focus on put/call ratio, absolute call VOLUME vs open interest, premium size, and whether flow aligns with the technical trend. Unusually low P/C ratios (<0.1) with high volume are strongest.
- **momentum / technical_breakout**: Focus on volume confirmation (>2x average), trend alignment (above key SMAs), and whether momentum is accelerating or fading. Avoid chasing extended moves (RSI >80).
- **earnings_play**: Focus on short interest (squeeze potential), pre-earnings accumulation signals, analyst estimate trends, and historical earnings surprise rate. Binary risk must be acknowledged.
- **social_dd**: Has shown 55% 30d win rate — strongest long-hold scanner. These setups combine social sentiment WITH technical confirmation (OBV, short interest, MACD). Score based on quality of technical/fundamental corroboration. A strong OBV + high short interest + bullish MACD warrants 65-75. DO NOT conflate with social_hype.
- **social_hype**: Treat as SPECULATIVE (14.3% 7d win rate, -4.84% avg 7d return). Require strong corroborating evidence. Pure social sentiment without data backing should score below 50.
- **short_squeeze**: Focus on short interest %, days to cover, cost to borrow, and whether a catalyst exists to trigger covering. High SI alone is not enough.
- **contrarian_value**: Focus on oversold technicals (RSI <30), fundamental support (earnings stability), and a clear reason why the selloff is overdone.
- **news_catalyst**: **AVOID by default** — 0% historical 7d win rate (-8.37% avg 7d return, n=8). Only score ≥55 if the catalyst is (1) not yet reflected in the intraday move, (2) mechanistic and specific (FDA decision, contract win, regulatory approval), NOT macroeconomic framing ('geopolitical tension', 'oil price', 'rate expectations'). Macro news_catalyst setups should score <50.
- **sector_rotation**: Focus on relative strength vs sector ETF, whether the stock is a laggard in an accelerating sector.
- **minervini**: Focus on the RS Rating (top 30% = RS>=70, top 10% = RS>=90) as the primary signal. Verify all 6 trend template conditions are met (price structure above rising SMAs). Strongest setups combine RS>=85 with price consolidating near highs (within 10-15% of 52w high) — these have minimal overhead supply. Penalize if RS Rating is borderline (70-75) without other confirming signals.
- **ml_signal**: Use the ML Win Probability as a strong quantitative signal. Scores above 65% deserve significant weight.

HISTORICAL INSIGHTS:
{json.dumps(historical_stats.get('summary', 'N/A'), indent=2)}

CANDIDATES FOR REVIEW:
{combined_candidates_text}

RANKING INSTRUCTIONS:
1. Evaluate each candidate through the lens of its specific strategy (see criteria above).
2. Cross-reference the strategy signal with Technicals, Fundamentals, and Options data for confirmation.
3. Use the Quantitative Pre-Score as an objective baseline — scores above 50 indicate strong multi-factor alignment.
4. The ML Win Probability is a trained model's estimate of hitting +{self.return_target_pct}% within 7 days. Treat >60% as strong confirmation, >70% as very strong.
5. Prioritize LEADING indicators (Insider Buying, Pre-Earnings Accumulation, Options Flow) over lagging ones (momentum chasing, social hype).
6. Penalize contradictory signals: e.g., bullish options but heavy insider SELLING, or strong momentum but overbought RSI with declining volume.
7. Use ONLY the information provided in the candidates section. Do NOT invent catalysts, prices, or metrics that are not explicitly stated.
8. If a data field is missing, note it as N/A — do not fabricate values.
9. Only rank tickers from the candidates list.
10. Each reason MUST cite at least two specific data points from the candidate context (e.g., "P/C ratio of 0.02", "Director purchased $5.2M").

OUTPUT FORMAT — JSON object with a 'rankings' list. Each item:
- rank: sequential from 1
- ticker: stock symbol (must be from candidate list)
- company_name: company name
- current_price: numeric price from candidate data
- strategy_match: the candidate's strategy (use the value from the candidate, do not change it)
- final_score: 0-100 (your holistic assessment: {self.min_score_threshold}+ = included, 80+ = high conviction, 90+ = exceptional)
- confidence: 1-10 (how confident are you in THIS specific trade)
- risk_level: one of "low", "moderate", "high", "speculative"
- reason: Investment thesis in 4-6 sentences. Structure: (1) What is the edge/catalyst, (2) Why NOW — what makes the timing urgent, (3) Risk/reward profile, (4) Key risk or what could invalidate the thesis. Cite specific numbers.
- description: One-sentence company description

IMPORTANT: Return ONLY valid JSON. No markdown wrapping, no commentary outside the JSON. All numeric fields must be numbers, not strings."""

        # Invoke LLM with structured output
        logger.info("🧠 Deep Thinking Ranker analyzing opportunities...")
        logger.info(
            f"Invoking ranking LLM with {len(candidates)} candidates, prompt length: {len(prompt)} chars"
        )
        if self.log_prompts_console:
            logger.info(f"Full ranking prompt:\n{prompt}")

        try:
            # Invoke LLM directly — avoids with_structured_output which fails
            # when the LLM wraps JSON in ```json...``` markdown blocks
            response = self.llm.invoke([HumanMessage(content=prompt)])

            # Extract text content from response
            raw_text = ""
            if hasattr(response, "content"):
                content = response.content
                if isinstance(content, str):
                    raw_text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            raw_text = block.get("text", "")
                            break
                        elif isinstance(block, str):
                            raw_text = block
                            break

            tool_logs = state.get("tool_logs", [])
            append_llm_log(
                tool_logs,
                node="ranker",
                step="Rank candidates",
                model=resolve_llm_name(self.llm),
                prompt=prompt,
                output=raw_text[:2000],
            )
            state["tool_logs"] = tool_logs

            if not raw_text.strip():
                raise ValueError(
                    "LLM returned empty response. This may be due to content filtering or prompt length."
                )

            # Strip markdown wrapper (```json...```) and parse JSON
            json_str = extract_json_from_markdown(raw_text)
            if not json_str:
                raise ValueError(
                    f"LLM response did not contain valid JSON. Preview: {raw_text[:500]}"
                )

            try:
                parsed_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse JSON from LLM response: {e}")

            result = RankingResponse.model_validate(parsed_data)
            logger.info(f"Parsed {len(result.rankings)} rankings from LLM response")

            final_ranking_list = [ranking.model_dump() for ranking in result.rankings]

            logger.info(f"✅ Selected {len(final_ranking_list)} top recommendations")
            logger.info(
                f"Successfully ranked {len(final_ranking_list)} opportunities: "
                f"{[r['ticker'] for r in final_ranking_list]}"
            )

            # Update state with opportunities for downstream use (deep dive)
            state_opportunities = []
            for rank_dict in final_ranking_list:
                ticker = rank_dict["ticker"].upper()
                # Find original candidate metadata
                meta = next((c for c in candidates if c.get("ticker") == ticker), {})

                state_opportunities.append(
                    {
                        "ticker": ticker,
                        "strategy": rank_dict["strategy_match"],
                        "reason": rank_dict["reason"],
                        "score": rank_dict["final_score"],
                        "rank": rank_dict["rank"],
                        "metadata": meta,
                    }
                )

            return {
                "final_ranking": final_ranking_list,  # List of dicts
                "opportunities": state_opportunities,
                "status": "ranked",
            }

        except ValueError as e:
            tool_logs = state.get("tool_logs", [])
            append_llm_log(
                tool_logs,
                node="ranker",
                step="Rank candidates",
                model=resolve_llm_name(self.llm),
                prompt=prompt,
                output="",
                error=str(e),
            )
            state["tool_logs"] = tool_logs
            # Structured output validation failed
            logger.error(f"❌ Error: {e}")
            logger.error(f"Structured output validation error: {e}")
            return {"final_ranking": [], "opportunities": [], "status": "ranking_failed"}

        except Exception as e:
            tool_logs = state.get("tool_logs", [])
            append_llm_log(
                tool_logs,
                node="ranker",
                step="Rank candidates",
                model=resolve_llm_name(self.llm),
                prompt=prompt,
                output="",
                error=str(e),
            )
            state["tool_logs"] = tool_logs
            logger.error(f"❌ Error during ranking: {e}")
            logger.exception(f"Unexpected error during ranking: {e}")
            return {"final_ranking": [], "opportunities": [], "status": "error"}

    def _format_news_timestamp(self, timestamp: str) -> str:
        """
        Format news timestamp for display in ranking prompt.

        Handles various timestamp formats:
        - ISO-8601: 2026-01-31T14:30:00Z -> Jan 31 14:30
        - Date only: 2026-01-31 -> Jan 31
        - Already formatted strings pass through
        """
        if not timestamp:
            return ""

        try:
            # Try ISO-8601 format first
            if "T" in timestamp:
                # Parse ISO format: 2026-01-31T14:30:00Z or 2026-01-31T14:30:00+00:00
                dt_str = timestamp.replace("Z", "+00:00")
                # Handle timezone suffix
                if "+" in dt_str:
                    dt_str = dt_str.split("+")[0]
                elif dt_str.count("-") > 2:
                    # Handle negative timezone offset like -05:00
                    parts = dt_str.rsplit("-", 1)
                    if ":" in parts[-1]:
                        dt_str = parts[0]

                dt = datetime.fromisoformat(dt_str)
                return dt.strftime("%b %d %H:%M")

            # Try date-only format
            if len(timestamp) == 10 and timestamp.count("-") == 2:
                dt = datetime.strptime(timestamp, "%Y-%m-%d")
                return dt.strftime("%b %d")

            # Try compact format from Alpha Vantage: 20260131T143000
            if len(timestamp) >= 8 and timestamp[:8].isdigit():
                dt = datetime.strptime(timestamp[:8], "%Y%m%d")
                if len(timestamp) >= 15 and timestamp[8] == "T":
                    dt = datetime.strptime(timestamp[:15], "%Y%m%dT%H%M%S")
                    return dt.strftime("%b %d %H:%M")
                return dt.strftime("%b %d")

            # If it's already a short readable format, return as-is
            if len(timestamp) <= 20:
                return timestamp

        except (ValueError, AttributeError):
            # If parsing fails, return empty to avoid cluttering output
            pass

        return ""

    def _format_fundamentals_expanded(self, fund: Dict[str, Any]) -> str:
        """Format fundamentals dictionary with comprehensive data for ranking LLM."""
        if not fund:
            return "N/A"

        def fmt_pct(val):
            if val == "N/A" or val is None:
                return "N/A"
            try:
                return f"{float(val)*100:.1f}%"
            except Exception:
                return str(val)

        def fmt_large(val, prefix="$"):
            if val == "N/A" or val is None:
                return "N/A"
            try:
                n = float(val)
                if n >= 1e12:
                    return f"{prefix}{n/1e12:.2f}T"
                if n >= 1e9:
                    return f"{prefix}{n/1e9:.2f}B"
                if n >= 1e6:
                    return f"{prefix}{n/1e6:.1f}M"
                return f"{prefix}{n:,.0f}"
            except Exception:
                return str(val)

        def fmt_ratio(val):
            if val == "N/A" or val is None:
                return "N/A"
            try:
                return f"{float(val):.2f}"
            except Exception:
                return str(val)

        parts = []

        # Basic info
        sector = fund.get("Sector", "N/A")
        industry = fund.get("Industry", "N/A")
        if sector != "N/A":
            parts.append(f"Sector: {sector}")
        if industry != "N/A":
            parts.append(f"Industry: {industry}")

        # Valuation
        mc = fmt_large(fund.get("MarketCapitalization"))
        pe = fmt_ratio(fund.get("PERatio"))
        fwd_pe = fmt_ratio(fund.get("ForwardPE"))
        peg = fmt_ratio(fund.get("PEGRatio"))
        pb = fmt_ratio(fund.get("PriceToBookRatio"))
        ps = fmt_ratio(fund.get("PriceToSalesRatioTTM"))

        valuation_parts = []
        if mc != "N/A":
            valuation_parts.append(f"Cap: {mc}")
        if pe != "N/A":
            valuation_parts.append(f"P/E: {pe}")
        if fwd_pe != "N/A":
            valuation_parts.append(f"Fwd P/E: {fwd_pe}")
        if peg != "N/A":
            valuation_parts.append(f"PEG: {peg}")
        if pb != "N/A":
            valuation_parts.append(f"P/B: {pb}")
        if ps != "N/A":
            valuation_parts.append(f"P/S: {ps}")
        if valuation_parts:
            parts.append("Valuation: " + ", ".join(valuation_parts))

        # Growth metrics
        rev_growth = fmt_pct(fund.get("QuarterlyRevenueGrowthYOY"))
        earnings_growth = fmt_pct(fund.get("QuarterlyEarningsGrowthYOY"))

        growth_parts = []
        if rev_growth != "N/A":
            growth_parts.append(f"Rev Growth: {rev_growth}")
        if earnings_growth != "N/A":
            growth_parts.append(f"Earnings Growth: {earnings_growth}")
        if growth_parts:
            parts.append("Growth: " + ", ".join(growth_parts))

        # Profitability
        profit_margin = fmt_pct(fund.get("ProfitMargin"))
        oper_margin = fmt_pct(fund.get("OperatingMarginTTM"))
        roe = fmt_pct(fund.get("ReturnOnEquityTTM"))
        roa = fmt_pct(fund.get("ReturnOnAssetsTTM"))

        profit_parts = []
        if profit_margin != "N/A":
            profit_parts.append(f"Profit Margin: {profit_margin}")
        if oper_margin != "N/A":
            profit_parts.append(f"Oper Margin: {oper_margin}")
        if roe != "N/A":
            profit_parts.append(f"ROE: {roe}")
        if roa != "N/A":
            profit_parts.append(f"ROA: {roa}")
        if profit_parts:
            parts.append("Profitability: " + ", ".join(profit_parts))

        # Dividend info
        div_yield = fmt_pct(fund.get("DividendYield"))
        if div_yield != "N/A" and div_yield != "0.0%":
            parts.append(f"Dividend: {div_yield} yield")

        # Financial health
        current_ratio = fmt_ratio(fund.get("CurrentRatio"))
        debt_to_equity = fmt_ratio(fund.get("DebtToEquity"))
        if current_ratio != "N/A" or debt_to_equity != "N/A":
            health_parts = []
            if current_ratio != "N/A":
                health_parts.append(f"Current Ratio: {current_ratio}")
            if debt_to_equity != "N/A":
                health_parts.append(f"D/E: {debt_to_equity}")
            parts.append("Financial Health: " + ", ".join(health_parts))

        # Analyst targets
        target_high = fmt_large(fund.get("AnalystTargetPrice"))
        if target_high != "N/A":
            parts.append(f"Analyst Target: {target_high}")

        # Earnings info
        eps = fund.get("EPS", "N/A")
        if eps != "N/A":
            try:
                eps = f"${float(eps):.2f}"
                parts.append(f"EPS: {eps}")
            except Exception:
                pass

        # Beta (volatility)
        beta = fund.get("Beta", "N/A")
        if beta != "N/A":
            try:
                beta = f"{float(beta):.2f}"
                parts.append(f"Beta: {beta}")
            except Exception:
                pass

        # 52-week range
        week52_high = fund.get("52WeekHigh", "N/A")
        week52_low = fund.get("52WeekLow", "N/A")
        if week52_high != "N/A" and week52_low != "N/A":
            try:
                parts.append(f"52W Range: ${float(week52_low):.2f} - ${float(week52_high):.2f}")
            except Exception:
                pass

        # Short interest
        short_pct = fund.get("ShortPercentFloat", "N/A")
        if short_pct != "N/A":
            try:
                parts.append(f"Short Interest: {float(short_pct)*100:.1f}%")
            except Exception:
                pass

        return " | ".join(parts) if parts else "N/A"
