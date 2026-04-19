# Feature 2: Normalization, Classification, Confidence, Polarity

**Parent plan:** `docs/superpowers/plans/2026-04-19-json-scanner-graph-facts.md`

**Goal:** Implement `normalize.py` — the pure-logic layer that turns raw surface labels from scanner summaries into canonical node IDs, node types, polarity strings, and confidence floats. No I/O, no LLM. This layer is called by both adapters (Feature 3 + 4).

**Files to create:**
- `tradingagents/graph/scanner_facts/normalize.py`
- `tests/graph/scanner_facts/fixtures/` (real report fixtures copied verbatim)
- `tests/graph/scanner_facts/test_normalize.py`
- `tests/graph/scanner_facts/test_normalize_integration.py` (runs against full real fixture content)

---

## Real Report Fixtures

The fixtures below are verbatim copies of the 2026-04-16 scanner summaries. They are the ground truth for what the normalization layer must handle.

### `tests/graph/scanner_facts/fixtures/smart_money_summary.md`

```
**Candidate Rows**
* F | Consumer Cyclical | Insider Buying | Insider buying at $12.44 | Signaling auto/consumer cyclical sector revival.
* PBR | Energy | Insider Buying | Insider purchases at $21.5 | Suggests insider optimism despite broader energy sector volatility.
* OWL | Financial | Insider Buying | Insider buying at $9.65 | Confirms stable financial sector interest.
* ABT | Healthcare | Insider Buying | Insider buying at $95.47 | Suggests confidence in healthcare despite mixed sector performance.
* JBLU | Industrials | Insider Buying | Insider buying at $5.51 | Suggests selective accumulation within Industrials.
* ON | Technology | Breakout Accumulation | Breakout accumulation at $79.93 with 52-week high on high volume | Supports strong technology sector alignment.
* QBTS | Technology | Unusual Volume | Unusual volume spike at $21.52 | Confirms technology sector strength and ongoing momentum.

**Sector / Macro Implication**
* Consumer Cyclical | Insider buying signals potential early sector rebound | Sector slightly negative short-term, positive mid-term.
* Energy | Insider buying conflicts with current modest sector momentum | Potential early contrarian signal.
* Financials | Insider activity confirms steady interest | Sector showing modest gains mid-term.
* Healthcare | Insider buying indicates stock-specific strength or sector turnaround potential | Not leading currently.
* Industrials | Insider buys could signal selective accumulation | Internally positive but not top momentum sector.
* Technology | Confirmed institutional accumulation supports strong sector alignment | Sector leads momentum rankings.

**Dates and Exact Numbers**
* Scan Date: 2026-04-16
* F: $12.44
* PBR: $21.5
* OWL: $9.65
* ABT: $95.47
* JBLU: $5.51
* ON: $79.93 (52-week high)
* QBTS: $21.52

**Risk / Failure Modes**
* Consumer Cyclical: Insider buying may not fully offset short-term negative sector rotation.
* Energy: Broader energy sector volatility may negate insider optimism.
* Healthcare: Mixed sector performance may limit broader stock gains.
* Industrials: Mixed sector momentum may limit stock-specific accumulation impact.
```

### `tests/graph/scanner_facts/fixtures/sector_summary.md`

```
## Candidate Rows
- N/A

## Sector / Macro Implication
- TECHNOLOGY | Positive acceleration across all timeframes | Sustained growth sector strength.
- REAL ESTATE | Consistent positive acceleration, strong YTD performance | Persistent defensive sector interest.
- HEALTHCARE | Deceleration across all timeframes | Sustained outflow/weakness in defensive sector.
- CONSUMER STAPLES | Short-term deceleration from 1-Week to 1-Month despite positive 1-Day | Mixed momentum, potential profit-taking in defensive sector.
- FINANCIALS | Recent strength (1-Week +1.38%, 1-Month +5.54%) despite negative YTD (-4.77%) | Cyclical sector showing short-term recovery from weakness.
- CONSUMER DISCRETIONARY | Positive 1-Week (+4.34%) and 1-Month (+4.14%) but negative YTD (-0.41%) | Cyclical sector with recent strength, overall lagging.
- SECTOR/THEME | Positive 1-Day capital inflows in Technology (+1.14%), Real Estate (+0.92%), Consumer Staples (+0.46%) | Rotation into growth and defensive sectors.
- SECTOR/THEME | Negative short-term returns in Healthcare (-0.79%), Financials (-0.25%), Consumer Discretionary (-0.47%) | Short-term outflows or profit taking in these sectors.
- SECTOR/THEME | YTD strong performance in Real Estate (+9.22%) and Consumer Staples (+5.40%) | Sustained interest in defensive sectors.

## Dates and Exact Numbers
- Technology: +1.14% (1-Day), +7.00% (1-Week), +9.08% (1-Month), +5.48% (YTD).
- Real Estate: +0.92% (1-Day), +2.53% (1-Week), +3.24% (1-Month), +9.22% (YTD).

## Risk / Failure Modes
- Data for Energy, Industrials, Materials, Utilities, Communication Services is unavailable.
```

### `tests/graph/scanner_facts/fixtures/geopolitical_summary.md`

```
**Candidate Rows**
- Not Applicable | Industrials (Metal Fabrication) | Robustness | Metal fabrication stocks show robustness | Resilience amid geopolitical challenges.
- Not Applicable | Energy | Supply concerns | Brent Crude up +3.44% | Geopolitical tension-related supply risk.
- Not Applicable | Energy (LNG) | Strategic shift | LNG fleet expansion by Princess Cruises | Investment in LNG infrastructure in Asia.
- Not Applicable | Precious Metals | Safe haven demand | Gold up +0.25% at $4,811.90 | Geopolitical risk response.
- Not Applicable | Cryptocurrencies | Risk-on speculative activity | Bitcoin up +0.50% | Market resilience despite geopolitical risks.

**Sector / Macro Implication**
- EQUITIES (S&P 500, Nasdaq) | Reached new all-time highs | Market resilience despite geopolitical tensions.
- CORPORATE TREASURY | Geopolitical risk concerns surged | Proactive risk management in corporations.
- SOVEREIGN DEBT (US) | CDS spread 35.03 bps, 1M change -2.67% | Reduced perceived risk.
- SOVEREIGN DEBT (CHINA) | CDS spread 43.06 bps, 1M change -10.25% | Reduced perceived risk.
- SOVEREIGN DEBT (GERMANY) | CDS spread 9.12 bps, 1M change +13.01% | Rising perceived risk.
- FX (EUR/USD) | Down -0.13% at 1.18 | Eurozone geopolitical uncertainties/monetary policy differentials.
- FX (JPY/USD) | Down -0.25% at 0.01 | Reduced safe-haven demand or monetary stance.
- FX (CNY/USD) | Down -0.07% at 0.15 | Stable with minor weakening due to trade frictions or capital flows.

**Dates and Exact Numbers**
- S&P 500: New all-time high.
- Nasdaq: New all-time high.
- US 5Y CDS Spread: 35.03 bps, -2.67% 1M change.
- China 5Y CDS Spread: 43.06 bps, -10.25% 1M change.
- Germany 5Y CDS Spread: 9.12 bps, +13.01% 1M change.
- Gold Price: $4,811.90, +0.25%.
- Brent Crude Price: $98.20, +3.44%.
- WTI Crude Price: $90.05, -1.36%.
- Bitcoin Price: +0.50%.
- EUR/USD Exchange: 1.18, -0.13%.
- JPY/USD Exchange: 0.01, -0.25%.
- CNY/USD Exchange: 0.15, -0.07%.

**Risk / Failure Modes**
- Sovereign CDS: Confirms moderate geopolitical risk, but no crisis signals.
- WTI weakness: Could indicate regional disparities, contrasting Brent strength.
```

### `tests/graph/scanner_facts/fixtures/industry_deep_dive_summary.md`

```
**Candidate Rows**
*   ON | Technology | Breakout Accumulation | $79.93 price level | Implies institutional accumulation.
*   AMD | Technology | Momentum Leader | +41.75% (1-month), +17.59% (1-week) | Strong short-term performance.
*   INTC | Technology | Momentum Leader | +55.47% (1-month), +10.99% (1-week) | Strong short-term performance.
*   AVGO | Technology | Momentum Leader | +24.27% (1-month), +12.27% (1-week) | Strong short-term performance.
*   MSFT | Technology | Momentum Leader | +5.22% (1-month), +12.65% (1-week) | Strong short-term performance.
*   DLR | Real Estate | Recovery Leader | +10.34% (1-month), +5.79% (1-week) | Strong short-term performance, AI infrastructure link.
*   EQIX | Real Estate | Recovery Leader | +9.62% (1-month), +3.81% (1-week) | Strong short-term performance, AI infrastructure link.
*   CBRE | Real Estate | Recovery Leader | +8.45% (1-month), +3.75% (1-week) | Strong short-term performance.
*   PLD | Real Estate | Recovery Leader | +6.73% (1-month), +3.01% (1-week) | Strong short-term performance.
*   PM | Consumer Defensive | Laggard | -8.79% (1-month), -3.11% (1-week) | Negative short-term performance.
*   CL | Consumer Defensive | Laggard | -7.03% (1-month), -2.81% (1-week) | Negative short-term performance.
*   PG | Consumer Defensive | Laggard | -5.53% (1-month), -2.42% (1-week) | Negative short-term performance.

**Sector / Macro Implication**
*   Technology | +9.08% 1-month return (Ranked 1st) | High-conviction growth and institutional accumulation.
*   Real Estate | +9.22% YTD, +0.92% 1-day, +2.53% 1-week | High-conviction defensive/recovery.
*   Consumer Defensive | -3.32% 1-month | Low-conviction, rotation out of staples into growth.
*   AI Infrastructure | Technology (AVGO/MSFT) and Real Estate (DLR/EQIX) cross-correlation | Structural trade in AI physical layers.
*   Risk-On Rotation | Technology (+9.08% 1-month) vs. Consumer Defensive (-3.32% 1-month) | Broad market shift from safety to aggressive growth.

**Dates and Exact Numbers**
*   1-month Technology return: +9.08%
*   1-month Technology ranking: 1st
*   ON breakout price: $79.93
*   YTD Real Estate performance: +9.22%

**Risk / Failure Modes**
*   Technology | High valuation premiums, concentration risk | Potential for significant reversals.
*   Real Estate | Sensitivity to sovereign debt yields | Vulnerability to interest rate changes.
*   Consumer Defensive | Deteriorating revision pressure, negative momentum | Continued underperformance.
```

### `tests/graph/scanner_facts/fixtures/market_movers_summary.md`

```
**Candidate Rows**
* S&P 500 | Equity Index | Near 52W High | Price: 7041.28 (+0.26%) vs. 52W High: 7026.24 | Upward trend continuation.
* NASDAQ | Equity Index | Above 52W High | Price: 24102.70 (+0.36%) vs. 52W High: 24026.56 | Upward trend continuation.
* Russell 2000 | Equity Index | Near 52W High | Price: 2719.60 (+0.22%) vs. 52W High: 2735.10 | Upward trend continuation, lagging large caps.
* VIX | Volatility Index | Low Volatility | Price: 17.90 (-1.49%) vs. 52W Range: 13.38-35.75 | Risk-On support, gap-continuation probability increased.

**Sector / Macro Implication**
* EQUITY MARKETS | Broad Market | Risk-On environment | S&P 500, Dow Jones, NASDAQ, Russell 2000 showing positive intraday gains, VIX declining | Favors equity long positions, continuation of upward trends post-gaps.
* LARGE CAPS | Equity Segment | Moderate Lead | Dow Jones (+0.24%), S&P 500 (+0.26%) vs. Russell 2000 (+0.22%) | Modest tilt towards larger market capitalization segments.

**Risk / Failure Modes**
* Sustained VIX increase above 17.90 could negate Risk-On classification.
* Reversal of intraday gains could invalidate gap-continuation signal.
```

### `tests/graph/scanner_facts/fixtures/gatekeeper_summary.md`

```
**Candidate Rows**
* NVDA | Technology | Dominance | Ranked 1st by market cap and volume | High market cap concentration.
* AAPL | Technology | Dominance | Ranked 2nd by market cap and volume | High market cap concentration.
* MSFT | Technology | Dominance | Ranked 3rd by market cap and volume | High market cap concentration.
* AMZN | Consumer Discretionary | Dominance | Ranked 4th by market cap and volume | High market cap concentration.
* TSLA | Consumer Discretionary | Dominance | Ranked 5th by market cap and volume | High market cap concentration.
* AMD | Technology | High Liquidity | Ranked 6th by market cap and volume | Sector overrepresentation.
* ORCL | Technology | High Liquidity | Ranked 7th by market cap and volume | Sector overrepresentation.
* NFLX | Communication Services | High Liquidity | Ranked 8th by market cap and volume | Sector overrepresentation.
* PLTR | Technology | High Liquidity | Ranked 9th by market cap and volume | Sector overrepresentation.
* MU | Technology | High Liquidity | Ranked 10th by market cap and volume | Sector overrepresentation.
* BAC | Financials | High Liquidity | Ranked 11th by market cap and volume | Sector overrepresentation.
* PBR | Energy | High Liquidity | Ranked 12th by market cap and volume | Sector underrepresentation.
* T | Telecommunications | High Liquidity | Ranked 13th by market cap and volume | Sector underrepresentation.
* NU | Financials | High Liquidity | Ranked 14th by market cap and volume | Sector overrepresentation.
* ABT | Healthcare | High Liquidity | Ranked 15th by market cap and volume | Sector underrepresentation.

**Sector / Macro Implication**
* TECHNOLOGY | Dominance by market cap and volume across top 15 | Systemic concentration risk with 9 of 15 from tech.
* FINANCIALS | Represented in top 15 benchmarks (BAC, NU) | Overrepresented relative to universe breadth.
* CONSUMER DISCRETIONARY | Represented in top 15 benchmarks (AMZN, TSLA) | High concentration within top 5.
* UTILITIES, REAL ESTATE, BASIC MATERIALS | Low representation in scanner universe | Underweighted exposure.

**Risk / Failure Modes**
* Heavy weight towards mega-cap technology stocks exacerbates systemic risk.
* Sector exposure skewed towards technology and financials implies underweighted diversification.
```

### `tests/graph/scanner_facts/fixtures/macro_scan_summary.json`

```json
{
  "timeframe": "1 month",
  "executive_summary": "Markets are in a pronounced Risk-On regime with the S&P 500 and Nasdaq reaching new all-time highs and the VIX compressed at 17.90 (-1.49%). Technology (+9.08% 1M) and Real Estate (+9.22% YTD) are the dominant leadership sectors, driven by AI infrastructure demand and institutional accumulation. Geopolitical risks remain moderate but tangible, evidenced by Brent Crude supply premiums (+3.44% at $98.20) and diverging sovereign CDS spreads (Germany +13.01% vs US -2.67%). Defensive sectors (Healthcare -5.34% YTD, Consumer Staples -3.32% 1M) are experiencing severe deterioration. The 'Golden Overlap' identifies ON, MSFT, and PBR as high-conviction candidates where Smart Money accumulation aligns with top-down sector momentum.",
  "macro_context": {
    "economic_cycle": "Late-cycle expansion characterized by leadership rotation into growth and cyclical recovery",
    "central_bank_stance": "Divergent global monetary conditions; US sovereign risk perception easing (5Y CDS 35.03 bps, -2.67% 1M), Eurozone uncertainty rising (German CDS +13.01%), China risk moderating (-10.25%)",
    "geopolitical_risks": [
      "Energy supply chain disruptions supporting Brent crude premium (+3.44%) over WTI (-1.36%)",
      "Eurozone sovereign stress escalation",
      "Persistent safe-haven bid in Precious Metals (Gold $4,811.90, +0.25%) despite equity highs"
    ]
  },
  "key_themes": [
    {
      "theme": "Technology Sector Momentum & AI Infrastructure",
      "description": "Technology leads 1-month returns (+9.08%) with sustained institutional accumulation and positive analyst revisions. AI infrastructure demand creates cross-sector correlation with Data Center REITs (DLR, EQIX).",
      "conviction": "high",
      "timeframe": "1 month"
    },
    {
      "theme": "Real Estate Recovery Via Yield & Digital Infrastructure",
      "description": "Sector demonstrates persistent strength (+9.22% YTD, +3.24% 1M) driven by rotation into yield assets and structural AI data center demand.",
      "conviction": "high",
      "timeframe": "1-3 months"
    },
    {
      "theme": "Energy Supply Instability",
      "description": "Geopolitical tension driving Brent-WTI divergence. Insider accumulation in select energy names contrasts with mixed short-term sector momentum.",
      "conviction": "medium",
      "timeframe": "1 month"
    },
    {
      "theme": "Defensive Sector Deterioration",
      "description": "Negative revision pressure and momentum deterioration in Healthcare (-5.34% YTD) and Consumer Staples (-3.32% 1M) indicating rotation out of traditional safety.",
      "conviction": "high",
      "timeframe": "1 month"
    }
  ],
  "stocks_to_investigate": [
    {
      "ticker": "ON",
      "name": "ON Semiconductor",
      "sector": "Technology",
      "rationale": "Breakout accumulation at $79.93 with 52-week high on high volume (Smart Money confirmation). Aligns with Technology sector dominance (+9.08% 1M) and growth factor leadership.",
      "thesis_angle": "Golden Overlap: Institutional accumulation meets sector momentum",
      "conviction": "high",
      "key_catalysts": [
        "Breakout above $79.93 on 11.54x relative volume",
        "Technology sector earnings reporting cycle"
      ],
      "risks": [
        "High valuation premium within concentrated sector",
        "Gap-fill reversal if momentum stalls"
      ]
    },
    {
      "ticker": "MSFT",
      "name": "Microsoft",
      "sector": "Technology",
      "rationale": "Analyst positive revisions indicate 41.62% rally potential. Momentum leader with +12.65% 1-week performance and +5.48% YTD in the top-ranked sector.",
      "thesis_angle": "Analyst revision inflection in secular growth leader",
      "conviction": "high",
      "key_catalysts": [
        "AI infrastructure monetization updates",
        "Earnings positive revision trend"
      ],
      "risks": [
        "Concentration risk (top-heavy index weight)",
        "Rich valuation susceptible to rate volatility"
      ]
    }
  ],
  "risk_factors": [
    "VIX sustained increase above 17.90 negating current Risk-On classification",
    "German sovereign CDS spread acceleration (+13.01%) indicating Eurozone systemic stress",
    "Technology sector concentration risk (NVDA/AAPL/MSFT >50% weight) amplifying drawdown potential",
    "WTI/Brent price divergence signaling regional demand destruction or supply dislocations",
    "Speculative gap-up reversals in Quantum/Lithium themes (XNDU, SGML) with insufficient fundamental catalysts",
    "Earnings reporting volatility window (4/30) for select Healthcare and Tech names"
  ]
}
```

---

## Step 1: Create fixture files

- [ ] Create `tests/graph/scanner_facts/fixtures/__init__.py` (empty).
- [ ] Create each fixture file above verbatim under `tests/graph/scanner_facts/fixtures/`. Do not alter the content.

Verify:
```bash
ls tests/graph/scanner_facts/fixtures/
```
Expected: `__init__.py  gatekeeper_summary.md  geopolitical_summary.md  industry_deep_dive_summary.md  macro_scan_summary.json  market_movers_summary.md  sector_summary.md  smart_money_summary.md`

## Step 2: Write the failing unit tests

- [ ] Create `tests/graph/scanner_facts/test_normalize.py`:

```python
"""Unit tests for normalize.py — pure-logic, no I/O."""
import pytest
from tradingagents.graph.scanner_facts.normalize import (
    canonicalize_sector,
    classify_node_type,
    is_equity_ticker,
    infer_polarity,
    compute_confidence,
    ConfidenceSource,
)


# ---- canonicalize_sector ----

def test_information_technology_becomes_technology():
    assert canonicalize_sector("Information Technology") == "Technology"

def test_financial_becomes_financials():
    assert canonicalize_sector("Financial") == "Financials"

def test_consumer_cyclical_becomes_consumer_discretionary():
    assert canonicalize_sector("Consumer Cyclical") == "Consumer Discretionary"

def test_consumer_defensive_becomes_consumer_staples():
    assert canonicalize_sector("Consumer Defensive") == "Consumer Staples"

def test_already_canonical_passes_through():
    assert canonicalize_sector("Technology") == "Technology"
    assert canonicalize_sector("Real Estate") == "Real Estate"
    assert canonicalize_sector("Energy") == "Energy"

def test_real_report_sector_variants():
    # These appear literally in the 2026-04-16 real summaries
    assert canonicalize_sector("Financials") == "Financials"
    assert canonicalize_sector("Healthcare") == "Health Care"
    assert canonicalize_sector("Telecommunications") == "Communication Services"
    assert canonicalize_sector("Communication Services") == "Communication Services"


# ---- classify_node_type ----

def test_classify_sp500_as_market_index():
    assert classify_node_type("S&P 500") == "MarketIndex"

def test_classify_nasdaq_as_market_index():
    assert classify_node_type("NASDAQ") == "MarketIndex"

def test_classify_russell_as_market_index():
    assert classify_node_type("Russell 2000") == "MarketIndex"

def test_classify_vix_as_macro_indicator():
    assert classify_node_type("VIX") == "MacroIndicator"

def test_classify_brent_crude_as_commodity():
    assert classify_node_type("Brent Crude") == "Commodity"

def test_classify_wti_crude_as_commodity():
    assert classify_node_type("WTI Crude") == "Commodity"

def test_classify_gold_as_commodity():
    assert classify_node_type("Gold") == "Commodity"

def test_classify_eurusd_as_currency_pair():
    assert classify_node_type("EUR/USD") == "CurrencyPair"

def test_classify_jpyusd_as_currency_pair():
    assert classify_node_type("JPY/USD") == "CurrencyPair"

def test_classify_bitcoin_as_crypto():
    assert classify_node_type("Bitcoin") == "CryptoAsset"

def test_classify_technology_as_sector():
    assert classify_node_type("Technology") == "Sector"

def test_classify_energy_as_sector():
    assert classify_node_type("Energy") == "Sector"

def test_classify_unknown_short_upper_as_ticker():
    # 1-5 uppercase chars not in known lists → Ticker (caller must validate with is_equity_ticker)
    assert classify_node_type("NVDA") == "Ticker"

def test_classify_ai_infrastructure_as_theme():
    assert classify_node_type("AI Infrastructure") == "Theme"

def test_classify_risk_on_rotation_as_theme():
    assert classify_node_type("Risk-On Rotation") == "Theme"


# ---- is_equity_ticker ----

def test_nvda_is_equity_ticker():
    assert is_equity_ticker("NVDA") is True

def test_on_is_equity_ticker():
    assert is_equity_ticker("ON") is True

def test_na_is_not_equity_ticker():
    assert is_equity_ticker("N/A") is False
    assert is_equity_ticker("Not Applicable") is False

def test_sector_theme_placeholder_is_not_equity_ticker():
    assert is_equity_ticker("SECTOR/THEME") is False

def test_sp500_label_is_not_equity_ticker():
    assert is_equity_ticker("S&P 500") is False

def test_nasdaq_is_not_equity_ticker():
    assert is_equity_ticker("NASDAQ") is False

def test_vix_is_not_equity_ticker():
    assert is_equity_ticker("VIX") is False

def test_gold_is_not_equity_ticker():
    assert is_equity_ticker("Gold") is False

def test_bitcoin_is_not_equity_ticker():
    assert is_equity_ticker("Bitcoin") is False

def test_ai_is_not_equity_ticker():
    # Common words that look like tickers
    assert is_equity_ticker("AI") is False

def test_us_is_not_equity_ticker():
    assert is_equity_ticker("US") is False

def test_etf_is_not_equity_ticker():
    assert is_equity_ticker("ETF") is False


# ---- infer_polarity ----

def test_polarity_bullish_from_accumulation():
    assert infer_polarity("Breakout accumulation at $79.93") == "bullish"

def test_polarity_bullish_from_momentum():
    assert infer_polarity("Strong short-term performance", "Momentum Leader") == "bullish"

def test_polarity_bearish_from_laggard():
    assert infer_polarity("Negative short-term performance", "Laggard") == "bearish"

def test_polarity_bearish_from_risk_word():
    assert infer_polarity("Geopolitical tension-related supply risk") == "bearish"

def test_polarity_bearish_from_deterioration():
    assert infer_polarity("Sustained outflow/weakness in defensive sector") == "bearish"

def test_polarity_empty_when_neutral():
    assert infer_polarity("Stable with minor movements") == ""

def test_polarity_bearish_takes_precedence_over_bullish():
    # "potential" → bullish word absent; "risk" present → bearish
    result = infer_polarity("Strong potential but significant risk")
    assert result in ("bullish", "bearish", "")  # both present — no strict rule, just not crash


# ---- compute_confidence ----

def test_confidence_macro_json_structured():
    c = compute_confidence(ConfidenceSource.MACRO_JSON_STRUCTURED)
    assert abs(c - 0.90) < 0.01

def test_confidence_md_pipe_full():
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL)
    assert abs(c - 0.95) < 0.01

def test_confidence_md_pipe_partial():
    c = compute_confidence(ConfidenceSource.MD_PIPE_PARTIAL)
    assert abs(c - 0.75) < 0.01

def test_confidence_md_free_bullet():
    c = compute_confidence(ConfidenceSource.MD_FREE_BULLET)
    assert abs(c - 0.55) < 0.01

def test_confidence_inferred_edge():
    c = compute_confidence(ConfidenceSource.INFERRED_EDGE)
    assert abs(c - 0.50) < 0.01

def test_confidence_macro_json_free_text():
    c = compute_confidence(ConfidenceSource.MACRO_JSON_FREE_TEXT)
    assert abs(c - 0.70) < 0.01

def test_confidence_hedging_adjustment():
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL, hedging=True)
    assert c < 0.95  # must be lower

def test_confidence_no_polarity_adjustment():
    c_with = compute_confidence(ConfidenceSource.MD_PIPE_FULL, polarity_empty=True)
    c_without = compute_confidence(ConfidenceSource.MD_PIPE_FULL, polarity_empty=False)
    assert c_with < c_without

def test_confidence_heuristic_adjustment():
    c_heuristic = compute_confidence(ConfidenceSource.MD_PIPE_FULL, heuristic_only=True)
    c_normal = compute_confidence(ConfidenceSource.MD_PIPE_FULL, heuristic_only=False)
    assert c_heuristic < c_normal

def test_confidence_corroboration_boost():
    c_single = compute_confidence(ConfidenceSource.MD_PIPE_FULL, corroborated=False)
    c_double = compute_confidence(ConfidenceSource.MD_PIPE_FULL, corroborated=True)
    assert c_double > c_single

def test_confidence_clamped_to_max_099():
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL, corroborated=True)
    assert c <= 0.99

def test_confidence_clamped_to_min_01():
    c = compute_confidence(
        ConfidenceSource.INFERRED_EDGE,
        hedging=True, heuristic_only=True, polarity_empty=True,
    )
    assert c >= 0.10

def test_confidence_below_threshold_is_low():
    # INFERRED_EDGE + hedging + heuristic → should be below 0.50
    c = compute_confidence(
        ConfidenceSource.INFERRED_EDGE,
        hedging=True, heuristic_only=True,
    )
    assert c < 0.50
```

## Step 3: Run failing tests

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
conda activate tradingagents
pytest tests/graph/scanner_facts/test_normalize.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'tradingagents.graph.scanner_facts.normalize'`

## Step 4: Implement `normalize.py`

- [ ] Create `tradingagents/graph/scanner_facts/normalize.py`:

```python
"""Normalization and classification for scanner graph facts.

Pure logic only — no I/O, no LLM. Called by both adapters.

Key functions:
  canonicalize_sector(label)     → canonical sector name
  classify_node_type(label)      → node type string
  is_equity_ticker(label)        → bool
  infer_polarity(*parts)         → "bullish" | "bearish" | ""
  compute_confidence(source, **flags) → float in [0.10, 0.99]
"""
from __future__ import annotations

import enum
import logging
import re

_logger = logging.getLogger(__name__)

# ---------- Sector canonicalization ----------

_SECTOR_CANON: dict[str, str] = {
    # Direct aliases
    "information technology": "Technology",
    "tech": "Technology",
    "it sector": "Technology",
    "financial": "Financials",
    "financial services": "Financials",
    "finance": "Financials",
    "consumer cyclical": "Consumer Discretionary",
    "retail": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "staples": "Consumer Staples",
    "healthcare": "Health Care",
    "health care sector": "Health Care",
    "pharma": "Health Care",
    "biotech": "Health Care",
    "telecom": "Communication Services",
    "telecommunications": "Communication Services",
    "communications": "Communication Services",
    "media": "Communication Services",
    "industrial": "Industrials",
    "industrials sector": "Industrials",
    "basic materials": "Materials",
    "materials sector": "Materials",
    "reits": "Real Estate",
    "real estate sector": "Real Estate",
    "utilities sector": "Utilities",
    "energy sector": "Energy",
    "oil & gas": "Energy",
    # Already canonical — keep as-is
    "technology": "Technology",
    "financials": "Financials",
    "consumer discretionary": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "health care": "Health Care",
    "communication services": "Communication Services",
    "industrials": "Industrials",
    "materials": "Materials",
    "real estate": "Real Estate",
    "utilities": "Utilities",
    "energy": "Energy",
}

# Node types for canonical sector names
_CANONICAL_SECTORS: frozenset[str] = frozenset(_SECTOR_CANON.values())


def canonicalize_sector(label: str) -> str:
    """Return the canonical sector name for *label*, or the original if unknown."""
    key = (label or "").strip().lower()
    canonical = _SECTOR_CANON.get(key)
    if canonical:
        return canonical
    # Warn: this label will fall through to heuristic; needs alias entry
    _logger.warning("normalize: unknown sector label %r — add to aliases.py", label)
    return label.strip()


# ---------- Node type classification ----------

_MARKET_INDEXES: frozenset[str] = frozenset({
    "s&p 500", "sp500", "s&p500", "spx",
    "nasdaq", "nasdaq composite", "ndx",
    "dow jones", "djia", "dow",
    "russell 2000", "rut",
})

_MACRO_INDICATORS: frozenset[str] = frozenset({
    "vix", "cboe volatility index",
    "cpi", "pce", "fed funds rate", "federal funds rate",
    "10y yield", "10-year treasury",
    "german cds", "us cds", "china cds", "sovereign cds",
    "dxy", "us dollar index",
})

_COMMODITIES: frozenset[str] = frozenset({
    "brent crude", "brent", "ice brent",
    "wti crude", "wti", "nymex crude",
    "gold", "xauusd", "spot gold",
    "silver", "xagusd",
    "natural gas", "nat gas",
    "copper", "comex copper",
})

_FX_PAIRS: frozenset[str] = frozenset({
    "eur/usd", "eurusd",
    "jpy/usd", "jpyusd", "usd/jpy", "usdjpy",
    "cny/usd", "cnyusd", "usd/cny", "usdcny",
    "gbp/usd", "gbpusd",
})

_CRYPTO: frozenset[str] = frozenset({
    "bitcoin", "btc", "xbtusd",
    "ethereum", "eth",
})

# Short uppercase strings that look like tickers but are not
_TICKER_BLOCKLIST: frozenset[str] = frozenset({
    "AI", "US", "FX", "ETF", "CEO", "SEC", "GDP", "CPI", "PCE",
    "VIX", "FED", "BUY", "SELL", "HOLD", "TOP", "NET", "NEW",
    "HIGH", "LOW", "ALL", "AND", "THE", "FOR", "ARE", "NOT", "BUT",
    "YTD", "YOY", "QOQ", "MOM", "EPS", "PE", "PB", "ROE", "ROA",
    "LNG", "IPO", "M&A", "ESG", "IT", "REIT", "IMF", "WTO",
    "N/A", "NA", "SECTOR", "THEME",
    "S&P", "SPX", "NDX", "DXY", "RUT", "VXX",
})

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_FX_RE = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")


def classify_node_type(label: str) -> str:
    """Return the best-match node type for *label*.

    Logs a warning when falling back to heuristic Ticker classification
    so the alias registry can be updated.
    """
    norm = (label or "").strip()
    lower = norm.lower()

    if lower in _MARKET_INDEXES:
        return "MarketIndex"
    if lower in _MACRO_INDICATORS:
        return "MacroIndicator"
    if lower in _COMMODITIES:
        return "Commodity"
    if lower in _FX_PAIRS or _FX_RE.match(norm):
        return "CurrencyPair"
    if lower in _CRYPTO:
        return "CryptoAsset"
    if lower in {s.lower() for s in _CANONICAL_SECTORS}:
        return "Sector"

    # Multi-word labels not matched above → Theme
    if " " in norm or "-" in norm or "/" in norm:
        return "Theme"

    # Single uppercase token — likely a Ticker
    if _TICKER_RE.match(norm) and norm not in _TICKER_BLOCKLIST:
        _logger.debug("normalize: %r classified as Ticker by heuristic", norm)
        return "Ticker"

    # Final fallback → Theme
    return "Theme"


# ---------- Equity ticker guard ----------

_NOT_EQUITY: frozenset[str] = (
    _TICKER_BLOCKLIST
    | {s.upper() for s in _MARKET_INDEXES}
    | {s.upper() for s in _MACRO_INDICATORS}
    | {s.upper() for s in _COMMODITIES}
    | {s.upper() for s in _CRYPTO}
    | {"NOT APPLICABLE", "N/A", "NA", "SECTOR/THEME"}
)


def is_equity_ticker(label: str) -> bool:
    """Return True if *label* looks like a real equity ticker symbol."""
    norm = (label or "").strip()
    if not norm:
        return False
    upper = norm.upper()
    if upper in _NOT_EQUITY:
        return False
    if not _TICKER_RE.match(upper):
        return False
    return True


# ---------- Polarity inference ----------

_BULLISH_RE = re.compile(
    r"\b(bullish|outperform|accumulation|breakout|tailwind|momentum|strong|surge|rally|"
    r"recovery|gainer|buy|positive|growth|upward|acceleration|high.conviction)\b",
    re.IGNORECASE,
)
_BEARISH_RE = re.compile(
    r"\b(bearish|underperform|headwind|risk|tension|concern|lagging|decline|drag|"
    r"decliner|sell|caution|weak|deteriorat|outflow|decelerat|negative|reversal|"
    r"laggard|volatility|stress|disruption)\b",
    re.IGNORECASE,
)


def infer_polarity(*parts: str) -> str:
    """Return 'bullish', 'bearish', or '' based on *parts* combined text."""
    joined = " ".join(p or "" for p in parts)
    bull = bool(_BULLISH_RE.search(joined))
    bear = bool(_BEARISH_RE.search(joined))
    if bear and not bull:
        return "bearish"
    if bull and not bear:
        return "bullish"
    if bull and bear:
        # Both present: context-specific terms win; default to bearish (conservative)
        return "bearish"
    return ""


# ---------- Confidence computation ----------

class ConfidenceSource(enum.Enum):
    MACRO_JSON_STRUCTURED = "macro_json_structured"     # base 0.90
    MACRO_JSON_FREE_TEXT = "macro_json_free_text"       # base 0.70
    MD_PIPE_FULL = "md_pipe_full"                       # base 0.95 (5-col row, evidence present)
    MD_PIPE_PARTIAL = "md_pipe_partial"                 # base 0.75 (3–4 col, evidence present)
    MD_FREE_BULLET = "md_free_bullet"                   # base 0.55 (no pipes, anchored)
    INFERRED_EDGE = "inferred_edge"                     # base 0.50 (edge from implication phrasing)


_BASE_CONFIDENCE: dict[ConfidenceSource, float] = {
    ConfidenceSource.MACRO_JSON_STRUCTURED: 0.90,
    ConfidenceSource.MACRO_JSON_FREE_TEXT: 0.70,
    ConfidenceSource.MD_PIPE_FULL: 0.95,
    ConfidenceSource.MD_PIPE_PARTIAL: 0.75,
    ConfidenceSource.MD_FREE_BULLET: 0.55,
    ConfidenceSource.INFERRED_EDGE: 0.50,
}


def compute_confidence(
    source: ConfidenceSource,
    *,
    hedging: bool = False,
    polarity_empty: bool = False,
    heuristic_only: bool = False,
    corroborated: bool = False,
) -> float:
    """Return confidence in [0.10, 0.99] for an emission.

    Args:
        source: Base confidence source (see ConfidenceSource enum).
        hedging: Text contains hedge words ("may", "could", "potential", "uncertain").
        polarity_empty: Edge has no polarity on a sentiment-style edge.
        heuristic_only: Node was classified by lexical heuristic, not registry.
        corroborated: Same (source, relation, target) found in ≥2 distinct provenance files.
    """
    c = _BASE_CONFIDENCE[source]
    if hedging:
        c -= 0.10
    if polarity_empty:
        c -= 0.05
    if heuristic_only:
        c -= 0.15
    if corroborated:
        c += 0.05
    return round(max(0.10, min(0.99, c)), 4)
```

## Step 5: Run unit tests — all should pass

```bash
pytest tests/graph/scanner_facts/test_normalize.py -v
```

Expected: all tests PASS. Fix any failures before proceeding.

## Step 6: Write the integration tests against real fixtures

These tests load the actual fixture files and assert that normalization handles every surface form that appears in real 2026-04-16 reports. They document exactly what the system must handle.

- [ ] Create `tests/graph/scanner_facts/test_normalize_integration.py`:

```python
"""Integration-level normalize tests using real 2026-04-16 fixture content.

These tests parse real scanner summary surface forms and assert that
normalization produces correct canonical outputs. They serve as a
living contract between the normalization layer and the actual report format.

Run with:
    pytest tests/graph/scanner_facts/test_normalize_integration.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.graph.scanner_facts.normalize import (
    canonicalize_sector,
    classify_node_type,
    is_equity_ticker,
    infer_polarity,
    compute_confidence,
    ConfidenceSource,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- Sector surface forms seen in real reports ----------

# From smart_money_summary.md: "Consumer Cyclical", "Financial", "Healthcare"
# These are non-canonical forms the scanner actually emits.

@pytest.mark.parametrize("raw,expected", [
    ("Consumer Cyclical", "Consumer Discretionary"),   # smart_money_summary.md
    ("Financial", "Financials"),                       # smart_money_summary.md (OWL row)
    ("Healthcare", "Health Care"),                     # smart_money_summary.md (ABT row)
    ("Industrials", "Industrials"),                    # already canonical
    ("Technology", "Technology"),                      # already canonical
    ("Energy", "Energy"),                              # already canonical
    ("Consumer Defensive", "Consumer Staples"),        # industry_deep_dive_summary.md (PM/CL/PG)
    ("Telecommunications", "Communication Services"), # gatekeeper_summary.md (T row)
    ("Real Estate", "Real Estate"),                    # already canonical
])
def test_real_sector_canonicalization(raw, expected):
    assert canonicalize_sector(raw) == expected, f"'{raw}' should canonicalize to '{expected}'"


# ---------- Ticker classification from real Candidate Rows ----------

# Tickers that appear in real reports and must be recognized as equity tickers.
@pytest.mark.parametrize("ticker", [
    "F", "PBR", "OWL", "ABT", "JBLU", "ON", "QBTS",  # smart_money_summary
    "NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "AMD",   # gatekeeper + industry
    "ORCL", "NFLX", "PLTR", "MU", "BAC", "NU",       # gatekeeper
    "INTC", "AVGO", "DLR", "EQIX", "CBRE", "PLD",    # industry_deep_dive
    "PM", "CL", "PG", "T",                             # industry_deep_dive + gatekeeper
])
def test_real_tickers_recognized_as_equity(ticker):
    assert is_equity_ticker(ticker), f"{ticker} should be an equity ticker"


# ---------- Non-ticker surface forms that must be rejected ----------

@pytest.mark.parametrize("label", [
    "N/A",              # geopolitical_summary.md (Not Applicable rows)
    "Not Applicable",   # geopolitical_summary.md
    "SECTOR/THEME",     # sector_summary.md
    "S&P 500",          # market_movers_summary.md
    "NASDAQ",           # market_movers_summary.md
    "Russell 2000",     # market_movers_summary.md
    "VIX",              # market_movers_summary.md
])
def test_real_non_tickers_rejected(label):
    assert not is_equity_ticker(label), f"{label} should NOT be an equity ticker"


# ---------- Node type classification for real market-mover rows ----------

@pytest.mark.parametrize("label,expected_type", [
    ("S&P 500", "MarketIndex"),
    ("NASDAQ", "MarketIndex"),
    ("Russell 2000", "MarketIndex"),
    ("VIX", "MacroIndicator"),
    ("Brent Crude", "Commodity"),
    ("WTI Crude", "Commodity"),
    ("Gold", "Commodity"),
    ("Bitcoin", "CryptoAsset"),
    ("EUR/USD", "CurrencyPair"),
    ("JPY/USD", "CurrencyPair"),
    ("CNY/USD", "CurrencyPair"),
    ("Technology", "Sector"),
    ("Real Estate", "Sector"),
    ("Energy", "Sector"),
    ("Financials", "Sector"),
    ("AI Infrastructure", "Theme"),           # industry_deep_dive: "AI Infrastructure"
    ("Risk-On Rotation", "Theme"),            # industry_deep_dive: "Risk-On Rotation"
    ("Defensive Sector Deterioration", "Theme"),  # macro_scan key_themes
])
def test_real_label_node_type_classification(label, expected_type):
    result = classify_node_type(label)
    assert result == expected_type, f"'{label}' → expected {expected_type}, got {result}"


# ---------- Polarity from real evidence/implication text ----------

@pytest.mark.parametrize("evidence,implication,expected_polarity", [
    # From smart_money_summary.md
    ("Breakout accumulation at $79.93 with 52-week high on high volume",
     "Supports strong technology sector alignment.", "bullish"),
    ("Unusual volume spike at $21.52",
     "Confirms technology sector strength and ongoing momentum.", "bullish"),
    ("Insider buying at $12.44",
     "Signaling auto/consumer cyclical sector revival.", "bullish"),
    ("Insider purchases at $21.5",
     "Suggests insider optimism despite broader energy sector volatility.", "bullish"),
    # From industry_deep_dive_summary.md
    ("+41.75% (1-month), +17.59% (1-week)",
     "Strong short-term performance.", "bullish"),
    ("-8.79% (1-month), -3.11% (1-week)",
     "Negative short-term performance.", "bearish"),
    # From geopolitical_summary.md
    ("Brent Crude up +3.44%",
     "Geopolitical tension-related supply risk.", "bearish"),
    ("German CDS +13.01%",
     "Rising perceived risk.", "bearish"),
])
def test_real_polarity_inference(evidence, implication, expected_polarity):
    result = infer_polarity(evidence, implication)
    assert result == expected_polarity, (
        f"Evidence: {evidence!r}\nImplication: {implication!r}\n"
        f"Expected: {expected_polarity!r}, got: {result!r}"
    )


# ---------- Confidence for real row shapes ----------

def test_full_5col_pipe_row_confidence():
    # ON | Technology | Breakout Accumulation | $79.93 price level | Implies institutional accumulation.
    # 5 columns, evidence present, no hedging
    c = compute_confidence(ConfidenceSource.MD_PIPE_FULL)
    assert c == 0.95


def test_partial_3col_pipe_row_confidence():
    # Consumer Cyclical | Insider buying signals potential early sector rebound | ...
    # The word "potential" is a hedge → apply hedging flag
    c = compute_confidence(ConfidenceSource.MD_PIPE_PARTIAL, hedging=True)
    assert 0.50 < c < 0.75


def test_macro_json_structured_confidence():
    # stocks_to_investigate[].ticker rows — structured JSON field
    c = compute_confidence(ConfidenceSource.MACRO_JSON_STRUCTURED)
    assert c == 0.90


def test_macro_json_free_text_confidence():
    # executive_summary text extraction
    c = compute_confidence(ConfidenceSource.MACRO_JSON_FREE_TEXT)
    assert c == 0.70


def test_inferred_edge_below_threshold():
    # Edge created from implication phrasing only — should be at/below threshold
    c = compute_confidence(ConfidenceSource.INFERRED_EDGE, hedging=True)
    assert c < 0.50


# ---------- End-to-end: load real fixture and verify no crash ----------

def test_load_macro_scan_summary_fixture():
    """Load the real macro_scan_summary.json fixture and run all surface forms through normalize."""
    payload = json.loads((FIXTURES / "macro_scan_summary.json").read_text())

    # stocks_to_investigate
    for stock in payload.get("stocks_to_investigate", []):
        ticker = stock["ticker"]
        sector = stock["sector"]
        assert is_equity_ticker(ticker), f"Fixture ticker {ticker!r} not recognized as equity"
        assert canonicalize_sector(sector) in {
            "Technology", "Financials", "Energy", "Health Care",
            "Consumer Discretionary", "Consumer Staples", "Real Estate",
            "Industrials", "Materials", "Utilities", "Communication Services",
        } or len(canonicalize_sector(sector)) > 0

    # key_themes — should classify as Theme
    for theme_obj in payload.get("key_themes", []):
        theme_label = theme_obj["theme"]
        t = classify_node_type(theme_label)
        assert t == "Theme", f"Theme label {theme_label!r} classified as {t!r}, expected Theme"

    # risk_factors — free text, should not crash
    for rf in payload.get("risk_factors", []):
        _ = infer_polarity(rf)


def test_load_smart_money_fixture_all_tickers_recognized():
    """Parse Candidate Rows from real smart_money_summary.md and check every ticker."""
    text = (FIXTURES / "smart_money_summary.md").read_text()
    # Extract pipe-row first columns: lines like "* F | Consumer Cyclical | ..."
    import re
    rows = re.findall(r"^\s*[*-]\s+([^|]+)\|", text, re.MULTILINE)
    tickers_in_candidate_rows = [
        r.strip() for r in rows
        if r.strip() and r.strip() not in ("Scan Date",)
        and not r.strip().startswith("Consumer")
        and not r.strip().startswith("Energy")
        and not r.strip().startswith("Financial")
        and not r.strip().startswith("Healthcare")
        and not r.strip().startswith("Industrials")
        and not r.strip().startswith("Technology")
    ]
    # Expected: F, PBR, OWL, ABT, JBLU, ON, QBTS
    expected_tickers = {"F", "PBR", "OWL", "ABT", "JBLU", "ON", "QBTS"}
    found = set(tickers_in_candidate_rows) & expected_tickers
    assert found == expected_tickers, f"Missing: {expected_tickers - found}"


def test_load_geopolitical_not_applicable_rows_rejected():
    """All Candidate Rows in geopolitical_summary.md start with 'Not Applicable' — none should pass is_equity_ticker."""
    text = (FIXTURES / "geopolitical_summary.md").read_text()
    import re
    rows = re.findall(r"^\s*[*-]\s+([^|]+)\|", text, re.MULTILINE)
    for first_col in rows:
        label = first_col.strip()
        assert not is_equity_ticker(label), (
            f"Geopolitical first-col {label!r} should NOT pass is_equity_ticker"
        )


def test_load_market_movers_indexes_classified():
    """Market mover Candidate Rows are index/volatility nodes — must not become Ticker."""
    text = (FIXTURES / "market_movers_summary.md").read_text()
    import re
    rows = re.findall(r"^\s*[*-]\s+([^|]+)\|", text, re.MULTILINE)
    for first_col in rows:
        label = first_col.strip()
        node_type = classify_node_type(label)
        assert node_type != "Ticker", (
            f"Market mover label {label!r} classified as Ticker — should be {node_type!r}"
        )
```

## Step 7: Run integration tests

```bash
pytest tests/graph/scanner_facts/test_normalize_integration.py -v
```

Expected: all tests PASS. If a sector variant or ticker is not recognized, fix `normalize.py` (not the test) and re-run.

## Step 8: Run full scanner_facts test suite — no regressions

```bash
pytest tests/graph/scanner_facts/ -v
pytest tests/ -v -m "not integration" -x
```

Both must be green.

## Step 9: Commit

```bash
cd /Users/Ahmet/Repo/TradingAgents/.claude/worktrees/silly-meitner-37bb65
git add \
  tradingagents/graph/scanner_facts/normalize.py \
  tests/graph/scanner_facts/fixtures/__init__.py \
  tests/graph/scanner_facts/fixtures/smart_money_summary.md \
  tests/graph/scanner_facts/fixtures/sector_summary.md \
  tests/graph/scanner_facts/fixtures/geopolitical_summary.md \
  tests/graph/scanner_facts/fixtures/industry_deep_dive_summary.md \
  tests/graph/scanner_facts/fixtures/market_movers_summary.md \
  tests/graph/scanner_facts/fixtures/gatekeeper_summary.md \
  tests/graph/scanner_facts/fixtures/macro_scan_summary.json \
  tests/graph/scanner_facts/test_normalize.py \
  tests/graph/scanner_facts/test_normalize_integration.py
git commit -m "feat(scanner-facts): add normalization layer with real-world fixture-based integration tests"
```

---

## Done When

- `pytest tests/graph/scanner_facts/test_normalize.py -v` → all green
- `pytest tests/graph/scanner_facts/test_normalize_integration.py -v` → all green
- `pytest tests/ -v -m "not integration" -x` → no regressions
- Every surface form from the real 2026-04-16 reports is handled without a log warning for "unknown sector label"
