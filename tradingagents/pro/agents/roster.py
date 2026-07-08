"""The Pro agent roster: 59 evidence agents as configuration (ADR-0014).

Executive roles are deliberately absent — they synthesize evidence rather
than emit it, and become graph nodes in Phase 4 (their charters live in
prompts/executive_team.md).

Specs may select inputs that today's feeds don't provide (ADX, VWAP,
Supertrend; X/Twitter items). Those agents abstain at runtime until the
input exists — an honest gap, never a fabricated opinion. Each such spec
carries a ``notes`` entry naming the missing dependency.
"""

from __future__ import annotations

from tradingagents.contracts import AgentTeam, Timeframe
from tradingagents.pro.agents.specs import AgentSpec

_T = AgentTeam.TECHNICAL
_M = AgentTeam.MACRO
_N = AgentTeam.NEWS_SENTIMENT
_Q = AgentTeam.QUANT
_R = AgentTeam.RISK


def _spec(agent_id: str, team: AgentTeam, persona: str, **kw) -> AgentSpec:
    return AgentSpec(agent_id=agent_id, team=team, persona=persona, **kw)


TECHNICAL_SPECS: tuple[AgentSpec, ...] = (
    _spec("trend", _T,
          "Primary trend direction and strength from moving-average structure "
          "(50/200 SMA posture, 10 EMA slope) confirmed against recent bars.",
          indicators=("SMA_50", "SMA_200", "EMA_10"), include_bars=30),
    _spec("ema", _T,
          "Short-horizon momentum via the 10-period EMA: price-vs-EMA posture "
          "and what it says about immediate directional pressure.",
          indicators=("EMA_10",), include_bars=10),
    _spec("sma", _T,
          "Long-horizon structure via the 50 and 200 SMAs: golden/death cross "
          "posture and mean-reversion distance.",
          indicators=("SMA_50", "SMA_200"), include_bars=10),
    _spec("vwap", _T,
          "Volume-weighted average price positioning: institutional fair-value "
          "anchor and deviation from it.",
          indicators=("VWAP",),
          notes="abstains until a VWAP indicator lands in the engine"),
    _spec("rsi", _T,
          "RSI(14) momentum: overbought/oversold zones, 50-line posture, and "
          "failure swings.",
          indicators=("RSI_14",)),
    _spec("macd", _T,
          "MACD line/signal/histogram: momentum inflections, crossovers, and "
          "histogram direction.",
          indicators=("MACD",)),
    _spec("adx", _T,
          "ADX(14) trend strength: trending vs directionless conditions and "
          "what that implies for signal reliability.",
          indicators=("ADX_14",),
          notes="abstains until an ADX indicator lands in the engine"),
    _spec("atr", _T,
          "ATR(14) volatility: range expansion/contraction and what current "
          "volatility means for stops and breakout odds.",
          indicators=("ATR_14",), include_bars=10),
    _spec("bollinger", _T,
          "Bollinger bands: band width (squeeze/expansion), band walks, and "
          "closes relative to the envelope.",
          indicators=("BOLL",), include_bars=10),
    _spec("supertrend", _T,
          "Supertrend flip state and distance as a trailing trend filter.",
          indicators=("SUPERTREND",),
          notes="abstains until a Supertrend indicator lands in the engine"),
    _spec("volume_profile", _T,
          "Volume distribution across the shown bars: where volume clustered, "
          "acceptance vs rejection of price areas.",
          include_bars=60),
    _spec("market_profile", _T,
          "Session structure across the shown bars: balance vs imbalance, "
          "range extension, and where value migrated.",
          include_bars=60),
    _spec("wyckoff", _T,
          "Wyckoff method: accumulation/distribution phase evidence, springs, "
          "upthrusts, and effort-vs-result from the shown bars.",
          include_bars=60),
    _spec("elliott_wave", _T,
          "Elliott wave structure: plausible wave count from the shown swing "
          "sequence, stated as scenario with invalidation level from the data.",
          include_bars=60),
    _spec("harmonic_patterns", _T,
          "Harmonic patterns: identifiable XABCD-style structures in the shown "
          "swings; state completion zones only from shown prices.",
          include_bars=60),
    _spec("candlestick", _T,
          "Candlestick analysis of the most recent bars: reversal/continuation "
          "formations and their context.",
          include_bars=10),
    _spec("smart_money_concepts", _T,
          "Smart-money concepts: displacement, inducement, and premium/discount "
          "positioning within the shown range.",
          include_bars=60),
    _spec("ict_concepts", _T,
          "ICT framework: draw on liquidity, session-based delivery, and "
          "displacement legs visible in the shown bars.",
          include_bars=60, include_session=True),
    _spec("fair_value_gap", _T,
          "Fair value gaps: three-bar imbalances in the shown sequence, filled "
          "vs unfilled, and their magnet effect.",
          include_bars=30),
    _spec("order_block", _T,
          "Order blocks: last opposing bars before displacement in the shown "
          "sequence and whether price is returning to them.",
          include_bars=60),
    _spec("liquidity_sweep", _T,
          "Liquidity sweeps: wicks through obvious prior highs/lows in the "
          "shown bars followed by reclaim, and what they imply.",
          include_bars=30),
    _spec("break_of_structure", _T,
          "Break of structure: violations of the prior swing sequence in the "
          "shown bars and whether they confirm or fake out.",
          include_bars=60),
    _spec("market_structure", _T,
          "Overall market structure: higher-high/higher-low integrity, range "
          "boundaries, and the currently controlling side.",
          include_bars=60),
    _spec("multi_timeframe", _T,
          "Cross-timeframe alignment: do momentum and trend readings agree "
          "across every timeframe present, or conflict?",
          indicators=("RSI_14", "MACD", "SMA_50"), all_timeframes=True,
          include_bars=20),
)

MACRO_SPECS: tuple[AgentSpec, ...] = (
    _spec("federal_reserve", _M,
          "Fed policy stance: the policy rate and real-yield backdrop and its "
          "transmission to the asset.",
          metrics=("FED_FUNDS_RATE", "US10Y_REAL")),
    _spec("treasury_yield", _M,
          "Treasury complex: nominal and real 10Y levels; opportunity cost of "
          "holding the asset.",
          metrics=("US10Y", "US10Y_REAL")),
    _spec("dollar_index", _M,
          "Dollar strength via DXY (futures index and broad measure) and its "
          "inverse pressure on dollar-denominated assets.",
          metrics=("DXY", "DXY_BROAD")),
    _spec("inflation", _M,
          "Inflation regime from CPI and PPI year-over-year and the case for "
          "inflation hedges.",
          metrics=("CPI_YOY", "PPI_YOY")),
    _spec("gdp", _M,
          "Growth backdrop from GDP momentum; risk-on/risk-off implications.",
          metrics=("GDP_YOY",)),
    _spec("cpi", _M,
          "Consumer inflation specifically: CPI YoY level vs the 2% anchor and "
          "its policy implications.",
          metrics=("CPI_YOY",)),
    _spec("ppi", _M,
          "Producer prices as a pipeline-inflation leading signal.",
          metrics=("PPI_YOY",)),
    _spec("nfp", _M,
          "Labor market via nonfarm payroll changes; strength vs cooling and "
          "the policy-path read-through.",
          metrics=("NFP_CHANGE",)),
    _spec("commodity_correlation", _M,
          "Cross-commodity confirmation: gold/silver correlation regime and "
          "whether the complex moves together.",
          metrics=("XAU_XAG_CORR_30D",)),
    _spec("central_bank", _M,
          "Global central-bank behavior: policy signals in the news flow plus "
          "the current policy-rate anchor.",
          metrics=("FED_FUNDS_RATE",), include_news=10,
          notes="richer once central-bank purchase data (WGC) lands"),
    _spec("geopolitical_risk", _M,
          "Geopolitical risk premium: conflict, sanctions, and safe-haven "
          "catalysts present in the shown news items.",
          include_news=10),
)

NEWS_SENTIMENT_SPECS: tuple[AgentSpec, ...] = (
    _spec("reuters_news", _N,
          "Wire-service coverage: weigh only items whose outlet is Reuters; "
          "treat them as high-reliability factual reporting.",
          include_news=15),
    _spec("bloomberg_news", _N,
          "Financial-press coverage: weigh only items whose outlet is "
          "Bloomberg; separate reporting from editorial framing.",
          include_news=15),
    _spec("general_news", _N,
          "Aggregate news flow: dominant narratives, catalysts, and coverage "
          "intensity across all shown items.",
          include_news=15),
    _spec("reddit_sentiment", _N,
          "Retail crowd sentiment in forum items: crowd positioning and "
          "contrarian extremes.",
          include_news=10,
          notes="typed Reddit feed pending; reads forum-source items when present"),
    _spec("twitter_sentiment", _N,
          "Real-time social pulse from X/Twitter-sourced items: velocity and "
          "influencer skew.",
          include_news=10,
          notes="no X/Twitter feed integrated; abstains unless such items appear"),
    _spec("fear_greed", _N,
          "Crowd emotion via the Fear & Greed index: extremes as contrarian "
          "signals, mid-range as trend fuel.",
          metrics=("FEAR_GREED_INDEX",)),
    _spec("economic_calendar", _N,
          "Upcoming scheduled releases mentioned in the shown items and the "
          "event risk they pose.",
          include_news=10,
          notes="dedicated calendar feed is a Phase 2.1 candidate"),
)

QUANT_SPECS: tuple[AgentSpec, ...] = (
    _spec("statistical_arbitrage", _Q,
          "Relative-value dislocations: cross-asset correlation state and "
          "z-score stretch as mean-reversion setups.",
          metrics=("XAU_XAG_CORR_30D", "CLOSE_ZSCORE_50")),
    _spec("regime_detection", _Q,
          "Market regime from realized volatility and trend-fit statistics; "
          "which strategy class the regime rewards.",
          metrics=("REALIZED_VOL_ANN", "TREND_SLOPE_PCT", "TREND_R2")),
    _spec("bayesian", _Q,
          "Bayesian read: treat the trend statistics as the prior and the "
          "z-score as the likelihood surprise; how should beliefs update?",
          metrics=("TREND_SLOPE_PCT", "TREND_R2", "CLOSE_ZSCORE_50")),
    _spec("monte_carlo", _Q,
          "Distributional risk: what current volatility and tail measures "
          "imply about the plausible forward path spread.",
          metrics=("REALIZED_VOL_ANN", "VAR_95"),
          notes="full Monte Carlo simulation arrives with the Phase 7 backtester"),
    _spec("walk_forward", _Q,
          "Signal robustness: is the trend fit strong enough to have survived "
          "out-of-sample validation, or is it curve-fit noise?",
          metrics=("TREND_R2", "REALIZED_VOL_ANN"),
          notes="true walk-forward validation arrives with the Phase 7 backtester"),
    _spec("reinforcement_learning", _Q,
          "Trained-policy read: the RL advisor's action values for the "
          "current state, their edge, and how much training support they "
          "carry — advisory input for the judge, never a directive.",
          metrics=("RL_Q_BUY", "RL_Q_SELL", "RL_Q_HOLD", "RL_POLICY_EDGE",
                   "RL_STATE_VISITS"),
          primary=("RL_Q_BUY",),
          notes="abstains unless a trained RLAdvisor is attached to the pipeline"),
    _spec("time_series_forecast", _Q,
          "Extrapolation discipline: what the fitted trend and its R² justify "
          "forecasting, and where extrapolation breaks.",
          metrics=("TREND_SLOPE_PCT", "TREND_R2", "CLOSE_ZSCORE_50")),
    _spec("volatility_forecast", _Q,
          "Forward volatility: realized vol vs current ATR — expanding or "
          "compressing, and consequences for position sizing.",
          metrics=("REALIZED_VOL_ANN",), indicators=("ATR_14",)),
)

RISK_SPECS: tuple[AgentSpec, ...] = (
    _spec("position_sizing", _R,
          "Whether the engine-computed position size is appropriate: size vs "
          "cap, and what it means for portfolio impact.",
          metrics=("POSITION_SIZE_UNITS", "POSITION_NOTIONAL",
                   "POSITION_PCT_EQUITY", "MAX_POSITION_PCT"),
          primary=("POSITION_SIZE_UNITS",)),
    _spec("kelly_criterion", _R,
          "Kelly-optimal capital fraction vs the configured per-trade risk: "
          "is the desk over- or under-betting its edge?",
          metrics=("KELLY_FRACTION", "MAX_RISK_PER_TRADE_PCT"),
          primary=("KELLY_FRACTION",),
          notes="Kelly appears once Phase 5 memory supplies win statistics"),
    _spec("var", _R,
          "Value-at-Risk: the 95% one-bar loss floor and whether it is "
          "tolerable at the proposed size.",
          metrics=("VAR_95", "POSITION_PCT_EQUITY"), primary=("VAR_95",)),
    _spec("cvar", _R,
          "Tail risk beyond VaR: expected shortfall and what the tail would "
          "do to the account.",
          metrics=("CVAR_95", "VAR_95"), primary=("CVAR_95",)),
    _spec("portfolio_risk", _R,
          "Aggregate portfolio risk posture vs configured drawdown tolerance.",
          metrics=("VAR_95", "CVAR_95", "POSITION_PCT_EQUITY", "MAX_DRAWDOWN_PCT")),
    _spec("correlation_risk", _R,
          "Concentration through correlation: does cross-asset co-movement "
          "amplify the true exposure?",
          metrics=("XAU_XAG_CORR_30D", "POSITION_PCT_EQUITY")),
    _spec("exposure", _R,
          "Gross exposure and leverage vs limits.",
          metrics=("POSITION_PCT_EQUITY", "MAX_POSITION_PCT", "MAX_LEVERAGE")),
    _spec("dynamic_stop_loss", _R,
          "Stop placement for whichever side might be taken: the ATR-scaled "
          "stop levels for a hypothetical long and short — tight enough to "
          "protect, wide enough to breathe. You assess geometry, not "
          "direction.",
          metrics=("ENTRY_REF_PRICE", "ATR_STOP_LONG", "ATR_STOP_SHORT"),
          indicators=("ATR_14",), primary=("ATR_STOP_LONG", "ATR_STOP_SHORT")),
    _spec("dynamic_take_profit", _R,
          "Target placement for whichever side might be taken: the ATR "
          "ladders for a hypothetical long and short and their reward-to-"
          "risk geometry. You assess geometry, not direction.",
          metrics=("ENTRY_REF_PRICE", "ATR_TP1_LONG", "ATR_TP2_LONG",
                   "ATR_TP1_SHORT", "ATR_TP2_SHORT",
                   "ATR_STOP_LONG", "ATR_STOP_SHORT"),
          indicators=("ATR_14",),
          primary=("ATR_TP1_LONG", "ATR_TP1_SHORT")),
)

ROSTER: tuple[AgentSpec, ...] = (
    *TECHNICAL_SPECS,
    *MACRO_SPECS,
    *NEWS_SENTIMENT_SPECS,
    *QUANT_SPECS,
    *RISK_SPECS,
)

SPECS_BY_TEAM: dict[AgentTeam, tuple[AgentSpec, ...]] = {
    AgentTeam.TECHNICAL: TECHNICAL_SPECS,
    AgentTeam.MACRO: MACRO_SPECS,
    AgentTeam.NEWS_SENTIMENT: NEWS_SENTIMENT_SPECS,
    AgentTeam.QUANT: QUANT_SPECS,
    AgentTeam.RISK: RISK_SPECS,
}


def spec_by_id(agent_id: str) -> AgentSpec:
    for spec in ROSTER:
        if spec.agent_id == agent_id:
            return spec
    raise KeyError(agent_id)


# Intraday-focused defaults for BTC (crypto runs on H4 by default); gold
# stays on D1. Timeframe overrides happen here rather than per-spec so the
# roster itself stays asset-agnostic.
def specs_for_asset(timeframe: Timeframe = Timeframe.D1) -> tuple[AgentSpec, ...]:
    from dataclasses import replace

    return tuple(replace(spec, timeframe=timeframe) for spec in ROSTER)
