import type { DailyRecommendation, Decision, BacktestResult, AccuracyMetrics, PricePoint, DateStats, OverallStats, Nifty50IndexPoint, RiskMetrics, ReturnBucket, AccuracyTrendPoint } from '../types';
import { NIFTY_50_STOCKS as nifty50List } from '../types';

// Generate AI analysis dynamically based on decision type and stock info
function generateAIAnalysis(symbol: string, companyName: string, decision: Decision, confidence: string, risk: string): string {
  const sector = getSectorForStock(symbol);

  if (decision === 'BUY') {
    return `## Summary
${confidence} confidence BUY signal for ${companyName} based on positive momentum and favorable sector conditions.

## Technical Analysis
- Stock showing upward momentum in recent sessions
- RSI in bullish zone (55-65 range)
- Trading above key moving averages
- Volume supporting the uptrend
- Support levels holding firm

## Fundamental Analysis
- Company fundamentals remain solid
- Revenue growth trajectory positive
- Margins stable or improving
- ${sector} sector showing strength
- Valuation reasonable relative to peers

## Sentiment
- Analyst ratings predominantly positive
- Institutional interest increasing
- News flow supportive
- Management commentary optimistic

## Risks
- ${risk === 'HIGH' ? 'Elevated volatility and market risk' : risk === 'MEDIUM' ? 'Moderate market and sector-specific risks' : 'Lower risk profile but general market exposure'}
- Sector-specific regulatory concerns
- Global macro headwinds possible`;
  } else if (decision === 'SELL') {
    return `## Summary
${confidence} confidence SELL signal for ${companyName} due to concerning technical and fundamental factors.

## Technical Analysis
- Stock in clear downtrend pattern
- Trading below major moving averages
- RSI showing weakness (below 40)
- Volume increasing on down days
- Key support levels at risk

## Fundamental Analysis
- Earnings momentum slowing
- Margin pressure evident
- ${sector} sector facing headwinds
- Competitive challenges increasing
- Valuation not justified by growth

## Sentiment
- Analyst downgrades recent
- Institutional selling observed
- Negative news flow
- Management guidance cautious

## Risks
- ${risk === 'HIGH' ? 'High downside risk if support breaks' : risk === 'MEDIUM' ? 'Further weakness likely' : 'Gradual decline expected'}
- Sector underperformance may persist
- Recovery timeline uncertain`;
  } else {
    return `## Summary
HOLD recommendation for ${companyName} as the stock consolidates with mixed signals.

## Technical Analysis
- Stock in consolidation phase
- Trading within defined range
- RSI neutral (45-55 range)
- Volume average, no clear direction
- Awaiting breakout confirmation

## Fundamental Analysis
- Business fundamentals stable
- Growth trajectory moderate
- ${sector} sector showing mixed trends
- Valuation fair at current levels
- No immediate catalysts visible

## Sentiment
- Analyst views mixed
- Institutional activity balanced
- News flow neutral
- Wait-and-watch mode prevailing

## Risks
- ${risk === 'HIGH' ? 'Volatility may increase' : risk === 'MEDIUM' ? 'Range-bound action likely to continue' : 'Stable but limited upside near-term'}
- Direction dependent on broader market
- Sector rotation risk`;
  }
}

// Get sector for a stock
function getSectorForStock(symbol: string): string {
  const sectors: Record<string, string> = {
    'RELIANCE': 'Energy & Retail', 'TCS': 'IT Services', 'HDFCBANK': 'Banking',
    'INFY': 'IT Services', 'ICICIBANK': 'Banking', 'HINDUNILVR': 'FMCG',
    'ITC': 'FMCG', 'SBIN': 'Banking', 'BHARTIARTL': 'Telecom',
    'KOTAKBANK': 'Banking', 'LT': 'Infrastructure', 'AXISBANK': 'Banking',
    'ASIANPAINT': 'Paints', 'MARUTI': 'Automobile', 'HCLTECH': 'IT Services',
    'SUNPHARMA': 'Pharma', 'TITAN': 'Consumer Durables', 'BAJFINANCE': 'NBFC',
    'WIPRO': 'IT Services', 'ULTRACEMCO': 'Cement', 'NESTLEIND': 'FMCG',
    'NTPC': 'Power', 'POWERGRID': 'Power', 'M&M': 'Automobile',
    'TATAMOTORS': 'Automobile', 'ONGC': 'Oil & Gas', 'JSWSTEEL': 'Steel',
    'TATASTEEL': 'Steel', 'ADANIENT': 'Conglomerate', 'ADANIPORTS': 'Ports',
    'COALINDIA': 'Mining', 'BAJAJFINSV': 'Financial Services', 'TECHM': 'IT Services',
    'HDFCLIFE': 'Insurance', 'SBILIFE': 'Insurance', 'GRASIM': 'Diversified',
    'DIVISLAB': 'Pharma', 'DRREDDY': 'Pharma', 'CIPLA': 'Pharma',
    'BRITANNIA': 'FMCG', 'EICHERMOT': 'Automobile', 'APOLLOHOSP': 'Healthcare',
    'INDUSINDBK': 'Banking', 'HEROMOTOCO': 'Automobile', 'TATACONSUM': 'FMCG',
    'BPCL': 'Oil & Gas', 'UPL': 'Chemicals', 'HINDALCO': 'Metals',
    'BAJAJ-AUTO': 'Automobile', 'LTIM': 'IT Services',
  };
  return sectors[symbol] || 'Diversified';
}

// Raw analysis content for detailed AI reasoning
const rawAnalysisData: Record<string, string> = {
  'BAJFINANCE': `## Summary
Strong BUY signal based on exceptional momentum and sector strength in the NBFC space.

## Technical Analysis
- Price up 13.7% in 30 days (₹678 → ₹771)
- RSI at 62: Bullish but not overbought
- MACD showing positive crossover on daily chart
- Trading above 50-day and 200-day moving averages
- Volume spike on breakout confirms institutional interest

## Fundamental Analysis
- Q3 FY25 results: 18% YoY profit growth
- AUM growth of 25% indicating strong business expansion
- NIM stable at 10.2%, best in class
- Credit costs under control at 1.8%
- ROE of 22% among highest in sector

## Sentiment
- 12 analyst buy ratings, 3 hold
- FII net buyers in financial sector last 2 weeks
- Management guidance raised for FY25
- Positive mentions on analyst calls

## Risks
- Interest rate sensitivity remains key concern
- Unsecured lending exposure at 45% of book
- Premium valuation at 5.2x P/B vs sector avg of 3.1x`,

  'BAJAJFINSV': `## Summary
BUY recommendation driven by strong holding company performance and insurance business growth.

## Technical Analysis
- 14% gain in one month (₹1,567 → ₹1,789)
- Breaking out of 3-month consolidation range
- RSI at 58, room for further upside
- Strong support at ₹1,650 level

## Fundamental Analysis
- Insurance subsidiary showing 28% premium growth
- Asset management AUM up 35% YoY
- Sum-of-parts valuation suggests 15% upside
- Healthy subsidiaries across financial services

## Sentiment
- Institutional holding increased by 2.3% in Q3
- Positive outlook from major brokerages
- Benefits from Bajaj Finance momentum

## Risks
- Dependent on subsidiary performance
- Insurance sector regulatory changes
- Holding company discount may persist`,

  'KOTAKBANK': `## Summary
BUY signal triggered by significant technical breakout with high volume confirmation.

## Technical Analysis
- Significant breakout on January 20th
- 9.2% gain on exceptionally high volume (66.6M shares)
- Breaking above ₹1,850 resistance, now support
- Bullish engulfing pattern on weekly chart

## Fundamental Analysis
- CASA ratio at 53%, best among private banks
- Asset quality stable with GNPA at 1.7%
- Q3 profit up 12% YoY
- Strong capital adequacy at 21%

## Sentiment
- Inclusion in major index reshuffling positive
- Foreign investor interest increasing
- New CEO initiatives well received

## Risks
- Margin compression in deposit rate war
- Competition from fintech players
- Slower loan growth vs peers at 15% YoY`,

  'DRREDDY': `## Summary
HIGH CONFIDENCE SELL due to severe downtrend and deteriorating fundamentals.

## Technical Analysis
- 14.9% decline in one month
- Trading below all major moving averages
- RSI at 28, approaching oversold but no reversal signs
- Death cross (50-day below 200-day) formed
- Volume increasing on down days

## Fundamental Analysis
- US generics pricing pressure intensifying
- Q3 margins contracted 300bps YoY
- R&D pipeline delays for key molecules
- Forex headwinds from rupee depreciation

## Sentiment
- 5 downgrades from major brokerages in January
- FDA inspection concerns linger
- Negative news flow on generic drug pricing

## Risks
- Further downside if ₹1,150 support breaks
- US regulatory environment uncertain
- Peer competition in key therapeutic areas`,

  'AXISBANK': `## Summary
HIGH CONFIDENCE SELL with persistent downtrend and structural concerns.

## Technical Analysis
- 10.5% sustained decline over 4 weeks
- Clear lower highs and lower lows pattern
- Below 200-day moving average
- Support at ₹1,020 being tested

## Fundamental Analysis
- Asset quality concerns in SME book
- NIM compression of 15bps QoQ
- Restructured book higher than peers
- Growth lagging private bank peers

## Sentiment
- Management transition uncertainty
- FII selling observed in January
- Mixed analyst ratings with more holds than buys

## Risks
- Economic slowdown impact on corporate loans
- Digital banking competitive pressure
- Capital adequacy adequate but tight for growth`,

  'RELIANCE': `## Summary
HOLD recommendation as stock consolidates near all-time highs with mixed signals.

## Technical Analysis
- Trading in tight range between ₹2,850-₹2,950
- RSI neutral at 52
- Consolidating after strong Q4 2024 rally
- Volume declining, suggesting indecision

## Fundamental Analysis
- Jio Platforms showing steady growth
- Retail business margins improving
- O2C segment facing global headwinds
- New energy investments progressing

## Sentiment
- Neutral analyst stance, waiting for Q4 results
- Domestic institutional support strong
- Global energy transition narrative supportive

## Risks
- Oil & Gas volatility impacts earnings
- Telecom ARPU growth slowing
- Execution risk on new initiatives`,

  'TCS': `## Summary
HOLD as IT sector faces near-term headwinds despite strong long-term positioning.

## Technical Analysis
- Range-bound between ₹3,800-₹4,100
- 50-day MA acting as resistance
- No clear directional momentum
- Volume average, no accumulation signs

## Fundamental Analysis
- Deal pipeline remains healthy at $12B TCV
- Attrition stabilizing at 13%
- Margins stable at 25%+
- Cloud and AI investments on track

## Sentiment
- Client spending outlook cautious for H1 FY26
- BFSI vertical showing early recovery signs
- Management guidance conservative but achievable

## Risks
- US recession fears impacting IT budgets
- Wage inflation pressure
- Currency volatility`,

  'HDFCBANK': `## Summary
HOLD as merger integration continues with near-term pressure on ratios.

## Technical Analysis
- Sideways movement in ₹1,650-₹1,750 range
- Testing 200-day moving average
- Neutral momentum indicators
- Support at ₹1,620 holding firm

## Fundamental Analysis
- Merger integration progressing well
- CASA ratio dilution temporary
- Credit costs elevated but manageable
- Strong franchise value intact

## Sentiment
- Institutional view remains constructive long-term
- Near-term concerns on deposit costs
- Wait-and-watch mode for most analysts

## Risks
- Deposit mobilization challenges
- Net interest margin pressure
- Integration execution risks`,
};

// Generate mock price history for sparklines with high volatility for visual impact
function generatePriceHistory(basePrice: number, trend: 'up' | 'down' | 'flat', days: number = 30, symbol?: string): PricePoint[] {
  const history: PricePoint[] = [];
  let price = basePrice;
  // Much higher trend bias and volatility for very visible chart movements
  const trendBias = trend === 'up' ? 0.015 : trend === 'down' ? -0.015 : 0.002;
  const baseSeed = symbol ? getSymbolSeed(symbol) + 5000 : Date.now();
  const volatility = 0.12; // 12% daily volatility for very visible movements

  for (let i = days; i >= 0; i--) {
    const date = new Date();
    date.setDate(date.getDate() - i);

    // Use seeded random if symbol provided, otherwise use Math.random
    const randomValue = symbol ? seededRandom(baseSeed + i * 100) : Math.random();
    // Add some wave pattern for more interesting charts
    const wavePattern = Math.sin(i * 0.3) * 0.02;
    const dailyReturn = trendBias + (randomValue - 0.5) * volatility + wavePattern;
    price = price * (1 + dailyReturn);

    history.push({
      date: date.toISOString().split('T')[0],
      price: Math.round(price * 100) / 100,
    });
  }

  return history;
}

// Mock backtest results based on decision type - with next-day returns
export const mockBacktestResults: Record<string, BacktestResult> = {
  'BAJFINANCE': {
    prediction_correct: true,
    actual_return_1d: 2.1,  // Next trading day return
    actual_return_1w: 3.2,
    actual_return_1m: 8.5,
    price_at_prediction: 771,
    current_price: 836,
    price_history: generatePriceHistory(771, 'up', 30, 'BAJFINANCE'),
  },
  'BAJAJFINSV': {
    prediction_correct: true,
    actual_return_1d: 1.8,
    actual_return_1w: 2.1,
    actual_return_1m: 6.8,
    price_at_prediction: 1789,
    current_price: 1911,
    price_history: generatePriceHistory(1789, 'up', 30, 'BAJAJFINSV'),
  },
  'KOTAKBANK': {
    prediction_correct: true,
    actual_return_1d: 1.5,
    actual_return_1w: 1.8,
    actual_return_1m: 4.2,
    price_at_prediction: 1850,
    current_price: 1928,
    price_history: generatePriceHistory(1850, 'up', 30, 'KOTAKBANK'),
  },
  'DRREDDY': {
    prediction_correct: true,
    actual_return_1d: -1.8,
    actual_return_1w: -2.8,
    actual_return_1m: -7.2,
    price_at_prediction: 1180,
    current_price: 1095,
    price_history: generatePriceHistory(1180, 'down', 30, 'DRREDDY'),
  },
  'AXISBANK': {
    prediction_correct: true,
    actual_return_1d: -1.2,
    actual_return_1w: -1.5,
    actual_return_1m: -5.3,
    price_at_prediction: 1045,
    current_price: 990,
    price_history: generatePriceHistory(1045, 'down', 30, 'AXISBANK'),
  },
  'HCLTECH': {
    prediction_correct: false,
    actual_return_1d: 0.6,
    actual_return_1w: 0.8,
    actual_return_1m: 2.1,
    price_at_prediction: 1720,
    current_price: 1756,
    price_history: generatePriceHistory(1720, 'up', 30, 'HCLTECH'),
  },
  'RELIANCE': {
    prediction_correct: true,
    actual_return_1d: 0.3,
    actual_return_1w: 0.5,
    actual_return_1m: 1.2,
    price_at_prediction: 2890,
    current_price: 2925,
    price_history: generatePriceHistory(2890, 'flat', 30, 'RELIANCE'),
  },
  'TCS': {
    prediction_correct: true,
    actual_return_1d: 0.2,
    actual_return_1w: -0.3,
    actual_return_1m: 0.8,
    price_at_prediction: 3950,
    current_price: 3982,
    price_history: generatePriceHistory(3950, 'flat', 30, 'TCS'),
  },
  'HDFCBANK': {
    prediction_correct: true,
    actual_return_1d: -0.1,
    actual_return_1w: 0.2,
    actual_return_1m: -0.5,
    price_at_prediction: 1680,
    current_price: 1672,
    price_history: generatePriceHistory(1680, 'flat', 30, 'HDFCBANK'),
  },
  'ICICIBANK': {
    prediction_correct: true,
    actual_return_1d: 1.1,
    actual_return_1w: 1.5,
    actual_return_1m: 3.8,
    price_at_prediction: 1120,
    current_price: 1163,
    price_history: generatePriceHistory(1120, 'up', 30, 'ICICIBANK'),
  },
  'SUNPHARMA': {
    prediction_correct: true,
    actual_return_1d: -0.9,
    actual_return_1w: -1.2,
    actual_return_1m: -3.5,
    price_at_prediction: 1850,
    current_price: 1785,
    price_history: generatePriceHistory(1850, 'down', 30, 'SUNPHARMA'),
  },
  'ADANIPORTS': {
    prediction_correct: true,
    actual_return_1d: -1.5,
    actual_return_1w: -2.1,
    actual_return_1m: -6.8,
    price_at_prediction: 1180,
    current_price: 1100,
    price_history: generatePriceHistory(1180, 'down', 30, 'ADANIPORTS'),
  },
};

// Calculate accuracy metrics from backtest results for all 50 stocks
export function calculateAccuracyMetrics(): AccuracyMetrics {
  const latestRec = sampleRecommendations[0];
  if (!latestRec) {
    return {
      total_predictions: 0,
      correct_predictions: 0,
      success_rate: 0,
      buy_accuracy: 0,
      sell_accuracy: 0,
      hold_accuracy: 0,
    };
  }

  let totalBuy = 0, correctBuy = 0;
  let totalSell = 0, correctSell = 0;
  let totalHold = 0, correctHold = 0;

  // Calculate accuracy for each stock
  Object.keys(latestRec.analysis).forEach(symbol => {
    const stockAnalysis = latestRec.analysis[symbol];
    const backtest = getBacktestResult(symbol);

    if (!backtest || !stockAnalysis?.decision) return;

    if (stockAnalysis.decision === 'BUY') {
      totalBuy++;
      if (backtest.prediction_correct) correctBuy++;
    } else if (stockAnalysis.decision === 'SELL') {
      totalSell++;
      if (backtest.prediction_correct) correctSell++;
    } else {
      totalHold++;
      if (backtest.prediction_correct) correctHold++;
    }
  });

  const total = totalBuy + totalSell + totalHold;
  const correct = correctBuy + correctSell + correctHold;

  return {
    total_predictions: total,
    correct_predictions: correct,
    success_rate: total > 0 ? correct / total : 0,
    buy_accuracy: totalBuy > 0 ? correctBuy / totalBuy : 0,
    sell_accuracy: totalSell > 0 ? correctSell / totalSell : 0,
    hold_accuracy: totalHold > 0 ? correctHold / totalHold : 0,
  };
}

// Cache for dynamically generated backtest results
const generatedBacktestCache: Record<string, BacktestResult> = {};

// Seeded random number generator for consistent results
function seededRandom(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

// Get a consistent seed from symbol string
function getSymbolSeed(symbol: string): number {
  let hash = 0;
  for (let i = 0; i < symbol.length; i++) {
    hash = ((hash << 5) - hash) + symbol.charCodeAt(i);
    hash = hash & hash;
  }
  return Math.abs(hash);
}

// Get backtest result for a symbol - generates dynamically if not in static data
export function getBacktestResult(symbol: string): BacktestResult | undefined {
  // Return existing backtest data if available
  if (mockBacktestResults[symbol]) {
    return mockBacktestResults[symbol];
  }

  // Return cached generated result if available
  if (generatedBacktestCache[symbol]) {
    return generatedBacktestCache[symbol];
  }

  // Get the stock's decision from the latest recommendation
  const latestRec = sampleRecommendations[0];
  const stockAnalysis = latestRec?.analysis[symbol];

  if (!stockAnalysis || !stockAnalysis.decision) {
    return undefined;
  }

  // Generate backtest result based on decision type with consistent seeding
  const decision = stockAnalysis.decision;
  const seed = getSymbolSeed(symbol);
  const basePrice = 1000 + seededRandom(seed) * 2000; // Consistent base price between 1000-3000

  // Determine trend and accuracy based on decision
  let trend: 'up' | 'down' | 'flat';
  let predictionCorrect: boolean;
  let returnMultiplier: number;

  // Simulate varied but consistent outcomes based on symbol seed
  const randomOutcome = seededRandom(seed + 1);

  if (decision === 'BUY') {
    // 75% chance BUY predictions are correct (stock goes up)
    predictionCorrect = randomOutcome < 0.75;
    trend = predictionCorrect ? 'up' : 'down';
    returnMultiplier = predictionCorrect ? (1 + seededRandom(seed + 2) * 0.08) : (1 - seededRandom(seed + 2) * 0.05);
  } else if (decision === 'SELL') {
    // 83% chance SELL predictions are correct (stock goes down)
    predictionCorrect = randomOutcome < 0.83;
    trend = predictionCorrect ? 'down' : 'up';
    returnMultiplier = predictionCorrect ? (1 - seededRandom(seed + 2) * 0.08) : (1 + seededRandom(seed + 2) * 0.05);
  } else {
    // HOLD - 70% chance it stays relatively flat
    predictionCorrect = randomOutcome < 0.70;
    trend = 'flat';
    returnMultiplier = 1 + (seededRandom(seed + 2) - 0.5) * 0.04; // +/- 2%
  }

  const currentPrice = basePrice * returnMultiplier;
  const actualReturn1m = ((currentPrice - basePrice) / basePrice) * 100;
  const actualReturn1w = actualReturn1m * 0.3; // Approximate
  // Next trading day return - about 15-25% of weekly return with some variance
  const actualReturn1d = actualReturn1w * (0.4 + seededRandom(seed + 3) * 0.3);

  const result: BacktestResult = {
    prediction_correct: predictionCorrect,
    actual_return_1d: Math.round(actualReturn1d * 10) / 10,
    actual_return_1w: Math.round(actualReturn1w * 10) / 10,
    actual_return_1m: Math.round(actualReturn1m * 10) / 10,
    price_at_prediction: Math.round(basePrice * 100) / 100,
    current_price: Math.round(currentPrice * 100) / 100,
    price_history: generatePriceHistory(basePrice, trend, 30, symbol),
  };

  // Cache the result for consistency
  generatedBacktestCache[symbol] = result;

  return result;
}

// Get raw analysis for a symbol - returns custom analysis if available, otherwise generates one
export function getRawAnalysis(symbol: string): string | undefined {
  // Return custom detailed analysis if available
  if (rawAnalysisData[symbol]) {
    return rawAnalysisData[symbol];
  }

  // Generate analysis dynamically for other stocks
  const latestRec = sampleRecommendations[0];
  const stockAnalysis = latestRec?.analysis[symbol];

  if (stockAnalysis && stockAnalysis.decision) {
    return generateAIAnalysis(
      symbol,
      stockAnalysis.company_name,
      stockAnalysis.decision,
      stockAnalysis.confidence || 'MEDIUM',
      stockAnalysis.risk || 'MEDIUM'
    );
  }

  return undefined;
}

// Generate 10 days of historical recommendations with varied but consistent data
function generateHistoricalRecommendations(): DailyRecommendation[] {
  // Trading days (skip weekends)
  const dates = [
    '2025-01-30', '2025-01-29', '2025-01-28', '2025-01-27',
    '2025-01-24', '2025-01-23', '2025-01-22', '2025-01-21',
    '2025-01-20', '2025-01-17'
  ];

  const recommendations: DailyRecommendation[] = [];

  for (let dayIndex = 0; dayIndex < dates.length; dayIndex++) {
    const date = dates[dayIndex];
    const dateSeed = dayIndex * 1000; // Different seed for each day

    // Generate analysis for all 50 stocks
    const analysis: Record<string, {
      symbol: string;
      company_name: string;
      decision: Decision;
      confidence?: 'HIGH' | 'MEDIUM' | 'LOW';
      risk?: 'HIGH' | 'MEDIUM' | 'LOW';
      raw_analysis?: string;
    }> = {};

    let buyCount = 0;
    let sellCount = 0;
    let holdCount = 0;

    for (const stock of nifty50List) {
      const stockSeed = getSymbolSeed(stock.symbol) + dateSeed;
      const rand = seededRandom(stockSeed);

      // Determine decision with some variation per day
      let decision: Decision;
      if (rand < 0.14) {
        decision = 'BUY';
        buyCount++;
      } else if (rand < 0.34) {
        decision = 'SELL';
        sellCount++;
      } else {
        decision = 'HOLD';
        holdCount++;
      }

      // Determine confidence and risk
      const confRand = seededRandom(stockSeed + 1);
      const riskRand = seededRandom(stockSeed + 2);

      const confidence: 'HIGH' | 'MEDIUM' | 'LOW' = confRand < 0.2 ? 'HIGH' : confRand < 0.7 ? 'MEDIUM' : 'LOW';
      const risk: 'HIGH' | 'MEDIUM' | 'LOW' = riskRand < 0.25 ? 'HIGH' : riskRand < 0.75 ? 'MEDIUM' : 'LOW';

      analysis[stock.symbol] = {
        symbol: stock.symbol,
        company_name: stock.company_name,
        decision,
        confidence,
        risk,
        raw_analysis: rawAnalysisData[stock.symbol],
      };
    }

    // Generate top picks and stocks to avoid based on analysis
    const topPicks = Object.values(analysis)
      .filter(s => s.decision === 'BUY' && (s.confidence === 'HIGH' || s.confidence === 'MEDIUM'))
      .slice(0, 3)
      .map((stock, idx) => ({
        rank: idx + 1,
        symbol: stock.symbol,
        company_name: stock.company_name,
        decision: stock.decision,
        reason: `Strong ${stock.confidence?.toLowerCase()} confidence BUY signal based on positive momentum and sector conditions.`,
        risk_level: stock.risk || 'MEDIUM' as const,
      }));

    const stocksToAvoid = Object.values(analysis)
      .filter(s => s.decision === 'SELL' && (s.confidence === 'HIGH' || s.risk === 'HIGH'))
      .slice(0, 4)
      .map(stock => ({
        symbol: stock.symbol,
        company_name: stock.company_name,
        reason: `${stock.confidence} confidence SELL with ${stock.risk} risk profile. Downward pressure detected.`,
      }));

    recommendations.push({
      date,
      analysis,
      ranking: {
        ranking: '',
        stocks_analyzed: 50,
        timestamp: `${date}T15:30:00.000Z`,
      },
      summary: {
        total: 50,
        buy: buyCount,
        sell: sellCount,
        hold: holdCount,
      },
      top_picks: topPicks,
      stocks_to_avoid: stocksToAvoid,
    });
  }

  // Override the first day (latest) with manually curated data for better demo
  if (recommendations.length > 0) {
    recommendations[0] = createLatestRecommendation();
  }

  return recommendations;
}

// Create the latest (curated) recommendation for demo purposes
function createLatestRecommendation(): DailyRecommendation {
  return {
    date: '2025-01-30',
    analysis: {
      'RELIANCE': { symbol: 'RELIANCE', company_name: 'Reliance Industries Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM', raw_analysis: rawAnalysisData['RELIANCE'] },
      'TCS': { symbol: 'TCS', company_name: 'Tata Consultancy Services Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM', raw_analysis: rawAnalysisData['TCS'] },
      'HDFCBANK': { symbol: 'HDFCBANK', company_name: 'HDFC Bank Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM', raw_analysis: rawAnalysisData['HDFCBANK'] },
      'INFY': { symbol: 'INFY', company_name: 'Infosys Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'ICICIBANK': { symbol: 'ICICIBANK', company_name: 'ICICI Bank Ltd', decision: 'BUY', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'HINDUNILVR': { symbol: 'HINDUNILVR', company_name: 'Hindustan Unilever Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'ITC': { symbol: 'ITC', company_name: 'ITC Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'SBIN': { symbol: 'SBIN', company_name: 'State Bank of India', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'BHARTIARTL': { symbol: 'BHARTIARTL', company_name: 'Bharti Airtel Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'KOTAKBANK': { symbol: 'KOTAKBANK', company_name: 'Kotak Mahindra Bank Ltd', decision: 'BUY', confidence: 'MEDIUM', risk: 'MEDIUM', raw_analysis: rawAnalysisData['KOTAKBANK'] },
      'LT': { symbol: 'LT', company_name: 'Larsen & Toubro Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'AXISBANK': { symbol: 'AXISBANK', company_name: 'Axis Bank Ltd', decision: 'SELL', confidence: 'HIGH', risk: 'HIGH', raw_analysis: rawAnalysisData['AXISBANK'] },
      'ASIANPAINT': { symbol: 'ASIANPAINT', company_name: 'Asian Paints Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'MARUTI': { symbol: 'MARUTI', company_name: 'Maruti Suzuki India Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'HCLTECH': { symbol: 'HCLTECH', company_name: 'HCL Technologies Ltd', decision: 'SELL', confidence: 'MEDIUM', risk: 'HIGH' },
      'SUNPHARMA': { symbol: 'SUNPHARMA', company_name: 'Sun Pharmaceutical Industries Ltd', decision: 'SELL', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'TITAN': { symbol: 'TITAN', company_name: 'Titan Company Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'BAJFINANCE': { symbol: 'BAJFINANCE', company_name: 'Bajaj Finance Ltd', decision: 'BUY', confidence: 'HIGH', risk: 'MEDIUM', raw_analysis: rawAnalysisData['BAJFINANCE'] },
      'WIPRO': { symbol: 'WIPRO', company_name: 'Wipro Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'ULTRACEMCO': { symbol: 'ULTRACEMCO', company_name: 'UltraTech Cement Ltd', decision: 'BUY', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'NESTLEIND': { symbol: 'NESTLEIND', company_name: 'Nestle India Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'NTPC': { symbol: 'NTPC', company_name: 'NTPC Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'POWERGRID': { symbol: 'POWERGRID', company_name: 'Power Grid Corporation of India Ltd', decision: 'SELL', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'M&M': { symbol: 'M&M', company_name: 'Mahindra & Mahindra Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'TATAMOTORS': { symbol: 'TATAMOTORS', company_name: 'Tata Motors Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'ONGC': { symbol: 'ONGC', company_name: 'Oil & Natural Gas Corporation Ltd', decision: 'SELL', confidence: 'MEDIUM', risk: 'HIGH' },
      'JSWSTEEL': { symbol: 'JSWSTEEL', company_name: 'JSW Steel Ltd', decision: 'BUY', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'TATASTEEL': { symbol: 'TATASTEEL', company_name: 'Tata Steel Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'ADANIENT': { symbol: 'ADANIENT', company_name: 'Adani Enterprises Ltd', decision: 'HOLD', confidence: 'LOW', risk: 'HIGH' },
      'ADANIPORTS': { symbol: 'ADANIPORTS', company_name: 'Adani Ports and SEZ Ltd', decision: 'SELL', confidence: 'MEDIUM', risk: 'HIGH' },
      'COALINDIA': { symbol: 'COALINDIA', company_name: 'Coal India Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'BAJAJFINSV': { symbol: 'BAJAJFINSV', company_name: 'Bajaj Finserv Ltd', decision: 'BUY', confidence: 'HIGH', risk: 'MEDIUM', raw_analysis: rawAnalysisData['BAJAJFINSV'] },
      'TECHM': { symbol: 'TECHM', company_name: 'Tech Mahindra Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'HDFCLIFE': { symbol: 'HDFCLIFE', company_name: 'HDFC Life Insurance Company Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'SBILIFE': { symbol: 'SBILIFE', company_name: 'SBI Life Insurance Company Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'GRASIM': { symbol: 'GRASIM', company_name: 'Grasim Industries Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'DIVISLAB': { symbol: 'DIVISLAB', company_name: "Divi's Laboratories Ltd", decision: 'SELL', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'DRREDDY': { symbol: 'DRREDDY', company_name: "Dr. Reddy's Laboratories Ltd", decision: 'SELL', confidence: 'HIGH', risk: 'HIGH', raw_analysis: rawAnalysisData['DRREDDY'] },
      'CIPLA': { symbol: 'CIPLA', company_name: 'Cipla Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'BRITANNIA': { symbol: 'BRITANNIA', company_name: 'Britannia Industries Ltd', decision: 'BUY', confidence: 'MEDIUM', risk: 'LOW' },
      'EICHERMOT': { symbol: 'EICHERMOT', company_name: 'Eicher Motors Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'APOLLOHOSP': { symbol: 'APOLLOHOSP', company_name: 'Apollo Hospitals Enterprise Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'INDUSINDBK': { symbol: 'INDUSINDBK', company_name: 'IndusInd Bank Ltd', decision: 'SELL', confidence: 'HIGH', risk: 'HIGH' },
      'HEROMOTOCO': { symbol: 'HEROMOTOCO', company_name: 'Hero MotoCorp Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'TATACONSUM': { symbol: 'TATACONSUM', company_name: 'Tata Consumer Products Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'BPCL': { symbol: 'BPCL', company_name: 'Bharat Petroleum Corporation Ltd', decision: 'SELL', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'UPL': { symbol: 'UPL', company_name: 'UPL Ltd', decision: 'HOLD', confidence: 'LOW', risk: 'HIGH' },
      'HINDALCO': { symbol: 'HINDALCO', company_name: 'Hindalco Industries Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'BAJAJ-AUTO': { symbol: 'BAJAJ-AUTO', company_name: 'Bajaj Auto Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
      'LTIM': { symbol: 'LTIM', company_name: 'LTIMindtree Ltd', decision: 'HOLD', confidence: 'MEDIUM', risk: 'MEDIUM' },
    },
    ranking: {
      ranking: '',
      stocks_analyzed: 50,
      timestamp: '2025-01-30T15:30:00.000Z',
    },
    summary: {
      total: 50,
      buy: 7,
      sell: 10,
      hold: 33,
    },
    top_picks: [
      {
        rank: 1,
        symbol: 'BAJFINANCE',
        company_name: 'Bajaj Finance Ltd',
        decision: 'BUY',
        reason: '13.7% gain over 30 days (₹678 → ₹771), strongest bullish momentum with robust upward trend.',
        risk_level: 'MEDIUM',
      },
      {
        rank: 2,
        symbol: 'BAJAJFINSV',
        company_name: 'Bajaj Finserv Ltd',
        decision: 'BUY',
        reason: '14% gain in one month (₹1,567 → ₹1,789) demonstrates clear bullish momentum with sector-wide tailwinds.',
        risk_level: 'MEDIUM',
      },
      {
        rank: 3,
        symbol: 'KOTAKBANK',
        company_name: 'Kotak Mahindra Bank Ltd',
        decision: 'BUY',
        reason: 'Significant breakout on January 20th with 9.2% gain on exceptionally high volume (66.6M shares).',
        risk_level: 'MEDIUM',
      },
    ],
    stocks_to_avoid: [
      {
        symbol: 'DRREDDY',
        company_name: "Dr. Reddy's Laboratories Ltd",
        reason: 'HIGH CONFIDENCE SELL with 14.9% decline in one month. Severe downtrend with high risk.',
      },
      {
        symbol: 'AXISBANK',
        company_name: 'Axis Bank Ltd',
        reason: 'HIGH CONFIDENCE SELL with 10.5% sustained decline. Clear and persistent downtrend.',
      },
      {
        symbol: 'HCLTECH',
        company_name: 'HCL Technologies Ltd',
        reason: 'SELL with 9.4% drop from recent highs. High risk rating with continued selling pressure.',
      },
      {
        symbol: 'ADANIPORTS',
        company_name: 'Adani Ports and SEZ Ltd',
        reason: 'SELL with 12% monthly decline and consistently lower lows. High risk profile.',
      },
    ],
  };
}

// Generate and export sample recommendations (10 days of historical data)
export const sampleRecommendations: DailyRecommendation[] = generateHistoricalRecommendations();

// Function to get recommendation for a specific date
export function getRecommendationByDate(date: string): DailyRecommendation | undefined {
  return sampleRecommendations.find(r => r.date === date);
}

// Function to get latest recommendation
export function getLatestRecommendation(): DailyRecommendation | undefined {
  return sampleRecommendations[0];
}

// Function to get all available dates
export function getAvailableDates(): string[] {
  return sampleRecommendations.map(r => r.date);
}

// Function to get stock history across all dates
export function getStockHistory(symbol: string): { date: string; decision: Decision }[] {
  return sampleRecommendations
    .filter(r => r.analysis[symbol])
    .map(r => ({
      date: r.date,
      decision: r.analysis[symbol].decision as Decision,
    }))
    .reverse();
}

// Get decision counts for charts
export function getDecisionCounts(date: string): { buy: number; sell: number; hold: number } {
  const rec = getRecommendationByDate(date);
  if (!rec) return { buy: 0, sell: 0, hold: 0 };
  return rec.summary;
}

// Get extended price history with more data points for charting
// Generates price history ending at the latest recommendation date
export function getExtendedPriceHistory(symbol: string, days: number = 60): PricePoint[] {
  // Use getBacktestResult to get data for any stock (including dynamically generated)
  const backtest = getBacktestResult(symbol);
  const latestRec = sampleRecommendations[0];

  // Get the end date from the latest recommendation, or use today
  const endDate = latestRec ? new Date(latestRec.date) : new Date();

  const basePrice = backtest ? backtest.price_at_prediction * 0.9 : 1000;
  const trend = backtest
    ? (backtest.actual_return_1m > 2 ? 'up' : backtest.actual_return_1m < -2 ? 'down' : 'flat')
    : 'flat';

  return generatePriceHistoryWithEndDate(basePrice, trend, days, endDate, symbol);
}

// Generate price history ending at a specific date with consistent seeding
function generatePriceHistoryWithEndDate(
  basePrice: number,
  trend: 'up' | 'down' | 'flat',
  days: number,
  endDate: Date,
  symbol?: string
): PricePoint[] {
  const history: PricePoint[] = [];
  let price = basePrice;
  const trendBias = trend === 'up' ? 0.003 : trend === 'down' ? -0.003 : 0;
  const baseSeed = symbol ? getSymbolSeed(symbol) : Date.now();

  for (let i = days; i >= 0; i--) {
    const date = new Date(endDate);
    date.setDate(date.getDate() - i);

    // Use seeded random for consistent results
    const dailyReturn = trendBias + (seededRandom(baseSeed + i * 100) - 0.5) * 0.02;
    price = price * (1 + dailyReturn);

    history.push({
      date: date.toISOString().split('T')[0],
      price: Math.round(price * 100) / 100,
    });
  }

  return history;
}

// Get prediction points for the chart with actual prices
// Only returns predictions that exist in the actual saved historical recommendations
export function getPredictionPointsWithPrices(
  symbol: string,
  priceHistory: PricePoint[]
): { date: string; decision: Decision; price: number }[] {
  // Get actual historical recommendations for this stock
  const stockHistory = getStockHistory(symbol);

  if (stockHistory.length === 0 || priceHistory.length === 0) {
    return [];
  }

  // Map actual historical recommendations to prediction points
  const predictions: { date: string; decision: Decision; price: number }[] = [];

  for (const historyEntry of stockHistory) {
    const historyDate = new Date(historyEntry.date).getTime();

    // Find the closest date in price history
    let closestPricePoint = priceHistory[0];
    let closestDiff = Math.abs(new Date(closestPricePoint.date).getTime() - historyDate);

    for (const pricePoint of priceHistory) {
      const diff = Math.abs(new Date(pricePoint.date).getTime() - historyDate);
      if (diff < closestDiff) {
        closestDiff = diff;
        closestPricePoint = pricePoint;
      }
    }

    // Use the closest price point's date (so it aligns with the chart's x-axis)
    predictions.push({
      date: closestPricePoint.date,
      decision: historyEntry.decision,
      price: closestPricePoint.price,
    });
  }

  return predictions.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
}

// Detailed return breakdown for explanation modal
export interface ReturnBreakdown {
  correctPredictions: {
    count: number;
    totalReturn: number;
    avgReturn: number;
    stocks: { symbol: string; decision: string; return1d: number }[];
  };
  incorrectPredictions: {
    count: number;
    totalReturn: number;
    avgReturn: number;
    stocks: { symbol: string; decision: string; return1d: number }[];
  };
  weightedReturn: number;
  formula: string;
}

// Get statistics for a specific recommendation date
// Uses weighted average: correct predictions contribute positively, incorrect negatively
export function getDateStats(date: string): DateStats | null {
  const rec = getRecommendationByDate(date);
  if (!rec) return null;

  const symbols = Object.keys(rec.analysis);
  let correctCount = 0;
  let incorrectCount = 0;
  let correctTotalReturn = 0;  // Sum of gains from correct predictions
  let incorrectTotalReturn = 0; // Sum of losses from incorrect predictions

  for (const symbol of symbols) {
    const stockAnalysis = rec.analysis[symbol];
    const backtest = getBacktestResult(symbol);
    if (!backtest || !stockAnalysis?.decision) continue;

    const decision = stockAnalysis.decision;
    const return1d = backtest.actual_return_1d;

    if (backtest.prediction_correct) {
      correctCount++;
      // For correct predictions:
      // - BUY that went up: add the positive return
      // - SELL that went down: add the absolute value (we gained by not holding/shorting)
      // - HOLD that stayed flat: add the small return (we correctly avoided volatility)
      if (decision === 'BUY') {
        correctTotalReturn += return1d; // Positive return
      } else if (decision === 'SELL') {
        correctTotalReturn += Math.abs(return1d); // We avoided this loss
      } else {
        correctTotalReturn += Math.abs(return1d) < 2 ? 0.1 : 0; // Small gain for correct hold
      }
    } else {
      incorrectCount++;
      // For incorrect predictions:
      // - BUY that went down: subtract the loss
      // - SELL that went up: subtract the missed gain
      // - HOLD that moved significantly: subtract the missed opportunity
      if (decision === 'BUY') {
        incorrectTotalReturn += return1d; // Negative return (loss)
      } else if (decision === 'SELL') {
        incorrectTotalReturn += -Math.abs(return1d); // We missed this gain
      } else {
        incorrectTotalReturn += -Math.abs(return1d); // Missed the move
      }
    }
  }

  const totalStocks = correctCount + incorrectCount;

  // Calculate weighted average
  // correct_avg * (correct_count/total) + incorrect_avg * (incorrect_count/total)
  const correctAvg = correctCount > 0 ? correctTotalReturn / correctCount : 0;
  const incorrectAvg = incorrectCount > 0 ? incorrectTotalReturn / incorrectCount : 0;

  const weightedReturn = totalStocks > 0
    ? (correctAvg * (correctCount / totalStocks)) + (incorrectAvg * (incorrectCount / totalStocks))
    : 0;

  return {
    date,
    avgReturn1d: Math.round(weightedReturn * 10) / 10,
    avgReturn1m: 0, // Not used with new calculation
    totalStocks,
    correctPredictions: correctCount,
    accuracy: totalStocks > 0 ? Math.round((correctCount / totalStocks) * 100) : 0,
    buyCount: rec.summary.buy,
    sellCount: rec.summary.sell,
    holdCount: rec.summary.hold,
  };
}

// Get detailed return breakdown for the explanation modal
export function getReturnBreakdown(date: string): ReturnBreakdown | null {
  const rec = getRecommendationByDate(date);
  if (!rec) return null;

  const correctStocks: { symbol: string; decision: string; return1d: number }[] = [];
  const incorrectStocks: { symbol: string; decision: string; return1d: number }[] = [];
  let correctTotalReturn = 0;
  let incorrectTotalReturn = 0;

  const symbols = Object.keys(rec.analysis);
  for (const symbol of symbols) {
    const stockAnalysis = rec.analysis[symbol];
    const backtest = getBacktestResult(symbol);
    if (!backtest || !stockAnalysis?.decision) continue;

    const decision = stockAnalysis.decision;
    const return1d = backtest.actual_return_1d;

    if (backtest.prediction_correct) {
      let effectiveReturn = 0;
      if (decision === 'BUY') {
        effectiveReturn = return1d;
      } else if (decision === 'SELL') {
        effectiveReturn = Math.abs(return1d);
      } else {
        effectiveReturn = Math.abs(return1d) < 2 ? 0.1 : 0;
      }
      correctTotalReturn += effectiveReturn;
      correctStocks.push({ symbol, decision, return1d: effectiveReturn });
    } else {
      let effectiveReturn = 0;
      if (decision === 'BUY') {
        effectiveReturn = return1d;
      } else if (decision === 'SELL') {
        effectiveReturn = -Math.abs(return1d);
      } else {
        effectiveReturn = -Math.abs(return1d);
      }
      incorrectTotalReturn += effectiveReturn;
      incorrectStocks.push({ symbol, decision, return1d: effectiveReturn });
    }
  }

  const correctCount = correctStocks.length;
  const incorrectCount = incorrectStocks.length;
  const totalStocks = correctCount + incorrectCount;

  const correctAvg = correctCount > 0 ? correctTotalReturn / correctCount : 0;
  const incorrectAvg = incorrectCount > 0 ? incorrectTotalReturn / incorrectCount : 0;

  const weightedReturn = totalStocks > 0
    ? (correctAvg * (correctCount / totalStocks)) + (incorrectAvg * (incorrectCount / totalStocks))
    : 0;

  const formula = totalStocks > 0
    ? `(${correctAvg.toFixed(2)}% × ${correctCount}/${totalStocks}) + (${incorrectAvg.toFixed(2)}% × ${incorrectCount}/${totalStocks}) = ${weightedReturn.toFixed(2)}%`
    : 'No data';

  return {
    correctPredictions: {
      count: correctCount,
      totalReturn: Math.round(correctTotalReturn * 10) / 10,
      avgReturn: Math.round(correctAvg * 10) / 10,
      stocks: correctStocks.sort((a, b) => b.return1d - a.return1d).slice(0, 5), // Top 5
    },
    incorrectPredictions: {
      count: incorrectCount,
      totalReturn: Math.round(incorrectTotalReturn * 10) / 10,
      avgReturn: Math.round(incorrectAvg * 10) / 10,
      stocks: incorrectStocks.sort((a, b) => a.return1d - b.return1d).slice(0, 5), // Bottom 5
    },
    weightedReturn: Math.round(weightedReturn * 10) / 10,
    formula,
  };
}

// Get overall statistics across all recommendation dates
// Uses compound returns (multiplier approach) for realistic portfolio simulation
export function getOverallStats(): OverallStats {
  const dates = getAvailableDates();
  let compoundMultiplier = 1; // Start with 1 (100%)
  let totalPredictions = 0;
  let totalCorrect = 0;

  let bestDay: { date: string; return: number } | null = null;
  let worstDay: { date: string; return: number } | null = null;

  // Sort dates chronologically for proper compounding
  const sortedDates = [...dates].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  for (const date of sortedDates) {
    const stats = getDateStats(date);
    if (stats) {
      // Compound the daily return: multiply by (1 + daily_return/100)
      compoundMultiplier *= (1 + stats.avgReturn1d / 100);

      totalPredictions += stats.totalStocks;
      totalCorrect += stats.correctPredictions;

      if (!bestDay || stats.avgReturn1d > bestDay.return) {
        bestDay = { date, return: stats.avgReturn1d };
      }
      if (!worstDay || stats.avgReturn1d < worstDay.return) {
        worstDay = { date, return: stats.avgReturn1d };
      }
    }
  }

  // Convert multiplier back to percentage: (multiplier - 1) * 100
  const compoundReturn = (compoundMultiplier - 1) * 100;

  return {
    totalDays: dates.length,
    totalPredictions,
    avgDailyReturn: Math.round(compoundReturn * 10) / 10, // This is now the compound return
    avgMonthlyReturn: 0, // Not used
    overallAccuracy: totalPredictions > 0 ? Math.round((totalCorrect / totalPredictions) * 100) : 0,
    bestDay,
    worstDay,
  };
}

// Get detailed breakdown of overall compound return calculation
export function getOverallReturnBreakdown(): {
  dailyReturns: { date: string; return: number; multiplier: number; cumulative: number }[];
  finalMultiplier: number;
  finalReturn: number;
  formula: string;
} {
  const dates = getAvailableDates();
  const sortedDates = [...dates].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  const dailyReturns: { date: string; return: number; multiplier: number; cumulative: number }[] = [];
  let cumulativeMultiplier = 1;

  for (const date of sortedDates) {
    const stats = getDateStats(date);
    if (stats) {
      const dailyMultiplier = 1 + stats.avgReturn1d / 100;
      cumulativeMultiplier *= dailyMultiplier;
      dailyReturns.push({
        date,
        return: stats.avgReturn1d,
        multiplier: Math.round(dailyMultiplier * 10000) / 10000,
        cumulative: Math.round((cumulativeMultiplier - 1) * 1000) / 10, // As percentage
      });
    }
  }

  const finalReturn = (cumulativeMultiplier - 1) * 100;
  const multiplierParts = dailyReturns.map(d => `(1 + ${d.return}%)`).join(' × ');
  const formula = dailyReturns.length > 0
    ? `${multiplierParts} = ${cumulativeMultiplier.toFixed(4)} → ${finalReturn.toFixed(2)}%`
    : 'No data';

  return {
    dailyReturns,
    finalMultiplier: Math.round(cumulativeMultiplier * 10000) / 10000,
    finalReturn: Math.round(finalReturn * 10) / 10,
    formula,
  };
}

// ===============================================
// NEW FUNCTIONS FOR ENHANCED FEATURES
// ===============================================

// Get Nifty50 Index historical data
export function getNifty50IndexHistory(): Nifty50IndexPoint[] {
  const dates = getAvailableDates();
  const sortedDates = [...dates].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  const indexData: Nifty50IndexPoint[] = [];
  let indexValue = 21500; // Starting Nifty value

  for (let i = 0; i < sortedDates.length; i++) {
    const date = sortedDates[i];
    const seed = getSymbolSeed(date) + 9999;

    // Generate realistic daily return (-1.5% to +1.5% range)
    const dailyReturn = (seededRandom(seed) - 0.5) * 3;
    indexValue = indexValue * (1 + dailyReturn / 100);

    indexData.push({
      date,
      value: Math.round(indexValue * 100) / 100,
      return: Math.round(dailyReturn * 10) / 10,
    });
  }

  return indexData;
}

// Calculate risk metrics for the AI trading strategy
export function calculateRiskMetrics(): RiskMetrics {
  const dates = getAvailableDates();
  const dailyReturns: number[] = [];
  let wins = 0;
  let losses = 0;
  let totalWinReturn = 0;
  let totalLossReturn = 0;
  let totalCorrect = 0;
  let totalPredictions = 0;

  // Collect daily returns and win/loss stats
  for (const date of dates) {
    const stats = getDateStats(date);
    if (stats) {
      dailyReturns.push(stats.avgReturn1d);
      totalCorrect += stats.correctPredictions;
      totalPredictions += stats.totalStocks;

      if (stats.avgReturn1d > 0) {
        wins++;
        totalWinReturn += stats.avgReturn1d;
      } else if (stats.avgReturn1d < 0) {
        losses++;
        totalLossReturn += Math.abs(stats.avgReturn1d);
      }
    }
  }

  // Calculate standard deviation (volatility)
  const mean = dailyReturns.length > 0
    ? dailyReturns.reduce((a, b) => a + b, 0) / dailyReturns.length
    : 0;
  const variance = dailyReturns.length > 0
    ? dailyReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / dailyReturns.length
    : 0;
  const volatility = Math.sqrt(variance);

  // Calculate Sharpe ratio (assuming 0.02% risk-free daily rate, ~5% annual)
  const riskFreeRate = 0.02;
  const sharpeRatio = volatility > 0 ? (mean - riskFreeRate) / volatility : 0;

  // Calculate max drawdown
  let peak = 100;
  let maxDrawdown = 0;
  let currentValue = 100;
  for (const ret of dailyReturns) {
    currentValue = currentValue * (1 + ret / 100);
    if (currentValue > peak) {
      peak = currentValue;
    }
    const drawdown = ((peak - currentValue) / peak) * 100;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }

  // Calculate win/loss ratio
  const avgWin = wins > 0 ? totalWinReturn / wins : 0;
  const avgLoss = losses > 0 ? totalLossReturn / losses : 1;
  const winLossRatio = avgLoss > 0 ? avgWin / avgLoss : avgWin;

  // Win rate
  const winRate = totalPredictions > 0 ? (totalCorrect / totalPredictions) * 100 : 0;

  return {
    sharpeRatio: Math.round(sharpeRatio * 100) / 100,
    maxDrawdown: Math.round(maxDrawdown * 10) / 10,
    winLossRatio: Math.round(winLossRatio * 100) / 100,
    winRate: Math.round(winRate),
    volatility: Math.round(volatility * 100) / 100,
    totalTrades: totalPredictions,
  };
}

// Get return distribution histogram
export function getReturnDistribution(): ReturnBucket[] {
  const buckets: ReturnBucket[] = [
    { range: '< -3%', min: -Infinity, max: -3, count: 0, stocks: [] },
    { range: '-3% to -2%', min: -3, max: -2, count: 0, stocks: [] },
    { range: '-2% to -1%', min: -2, max: -1, count: 0, stocks: [] },
    { range: '-1% to 0%', min: -1, max: 0, count: 0, stocks: [] },
    { range: '0% to 1%', min: 0, max: 1, count: 0, stocks: [] },
    { range: '1% to 2%', min: 1, max: 2, count: 0, stocks: [] },
    { range: '2% to 3%', min: 2, max: 3, count: 0, stocks: [] },
    { range: '> 3%', min: 3, max: Infinity, count: 0, stocks: [] },
  ];

  // Get all stocks from latest recommendation and their returns
  const latestRec = sampleRecommendations[0];
  if (!latestRec) return buckets;

  for (const symbol of Object.keys(latestRec.analysis)) {
    const backtest = getBacktestResult(symbol);
    if (!backtest) continue;

    const returnVal = backtest.actual_return_1d;

    for (const bucket of buckets) {
      if (returnVal >= bucket.min && returnVal < bucket.max) {
        bucket.count++;
        bucket.stocks.push(symbol);
        break;
      }
    }
  }

  return buckets;
}

// Get accuracy trend over time
export function getAccuracyTrend(): AccuracyTrendPoint[] {
  const dates = getAvailableDates();
  const sortedDates = [...dates].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  return sortedDates.map(date => {
    const rec = getRecommendationByDate(date);
    if (!rec) {
      return { date, overall: 0, buy: 0, sell: 0, hold: 0 };
    }

    let totalBuy = 0, correctBuy = 0;
    let totalSell = 0, correctSell = 0;
    let totalHold = 0, correctHold = 0;

    for (const symbol of Object.keys(rec.analysis)) {
      const stockAnalysis = rec.analysis[symbol];
      const backtest = getBacktestResult(symbol);
      if (!backtest || !stockAnalysis?.decision) continue;

      if (stockAnalysis.decision === 'BUY') {
        totalBuy++;
        if (backtest.prediction_correct) correctBuy++;
      } else if (stockAnalysis.decision === 'SELL') {
        totalSell++;
        if (backtest.prediction_correct) correctSell++;
      } else {
        totalHold++;
        if (backtest.prediction_correct) correctHold++;
      }
    }

    const total = totalBuy + totalSell + totalHold;
    const correct = correctBuy + correctSell + correctHold;

    return {
      date,
      overall: total > 0 ? Math.round((correct / total) * 100) : 0,
      buy: totalBuy > 0 ? Math.round((correctBuy / totalBuy) * 100) : 0,
      sell: totalSell > 0 ? Math.round((correctSell / totalSell) * 100) : 0,
      hold: totalHold > 0 ? Math.round((correctHold / totalHold) * 100) : 0,
    };
  });
}

// Get cumulative portfolio data for charting
export function getCumulativeReturns(): { date: string; value: number; aiReturn: number; indexReturn: number }[] {
  const dates = getAvailableDates();
  const sortedDates = [...dates].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
  const indexData = getNifty50IndexHistory();

  const data: { date: string; value: number; aiReturn: number; indexReturn: number }[] = [];
  let aiMultiplier = 1;
  let indexMultiplier = 1;

  for (let i = 0; i < sortedDates.length; i++) {
    const date = sortedDates[i];
    const stats = getDateStats(date);
    const indexPoint = indexData.find(d => d.date === date);

    if (stats) {
      aiMultiplier *= (1 + stats.avgReturn1d / 100);
    }
    if (indexPoint) {
      indexMultiplier *= (1 + indexPoint.return / 100);
    }

    data.push({
      date,
      value: Math.round(aiMultiplier * 10000) / 100, // As percentage of starting value
      aiReturn: Math.round((aiMultiplier - 1) * 1000) / 10,
      indexReturn: Math.round((indexMultiplier - 1) * 1000) / 10,
    });
  }

  return data;
}

// Get all unique sectors from stocks
export function getAllSectors(): string[] {
  const sectors = new Set<string>();
  for (const stock of nifty50List) {
    if (stock.sector) {
      sectors.add(stock.sector);
    }
  }
  return Array.from(sectors).sort();
}
