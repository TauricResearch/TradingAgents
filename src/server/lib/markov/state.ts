/**
 * Markov Regime Detection — State Classification
 *
 * Classifies market state from rolling 20-bar returns.
 * Bull: cumulative return >= +5%
 * Bear: cumulative return <= -5%
 * Sideways: between -5% and +5%
 */

export type MarketState = 'bull' | 'bear' | 'sideways';

export interface DailyState {
  ticker: string;
  date: string;
  state: MarketState;
  cumulativeReturn: number;
}

export interface StateConfig {
  bullThreshold: number;
  bearThreshold: number;
  lookback: number;
}

const DEFAULT_CONFIG: StateConfig = {
  bullThreshold: 0.05,
  bearThreshold: -0.05,
  lookback: 20,
};

/**
 * Classify a market state from an array of period returns.
 */
export function classifyState(returns: number[], config: Partial<StateConfig> = {}): MarketState {
  const { bullThreshold, bearThreshold } = { ...DEFAULT_CONFIG, ...config };

  if (returns.length === 0) {
    throw new Error('Cannot classify state with empty returns array');
  }

  const cumulative = returns.reduce((sum, r) => sum + r, 0);

  if (cumulative >= bullThreshold) return 'bull';
  if (cumulative <= bearThreshold) return 'bear';
  return 'sideways';
}

/**
 * Get cumulative return from a price series.
 */
export function computeCumulativeReturns(prices: number[], lookback: number = 20): number[] {
  if (prices.length < lookback) {
    throw new Error(`Insufficient history: need ${lookback} bars, got ${prices.length}`);
  }

  const returns: number[] = [];
  for (let i = lookback; i < prices.length; i++) {
    const startPrice = prices[i - lookback]!;
    const endPrice = prices[i]!;
    const cumulativeReturn = (endPrice - startPrice) / startPrice;
    returns.push(cumulativeReturn);
  }
  return returns;
}

/**
 * Convert prices to daily states.
 */
export function generateStateStream(
  ticker: string,
  prices: number[],
  dates: string[],
  config: Partial<StateConfig> = {},
): DailyState[] {
  const { lookback } = { ...DEFAULT_CONFIG, ...config };

  if (prices.length !== dates.length) {
    throw new Error(`Price/date length mismatch: ${prices.length} prices, ${dates.length} dates`);
  }

  if (prices.length < lookback) {
    throw new Error(`Insufficient history: need ${lookback} bars, got ${prices.length}`);
  }

  const states: DailyState[] = [];

  for (let i = lookback; i < prices.length; i++) {
    // Calculate cumulative return for the lookback window
    const startPrice = prices[i - lookback]!;
    const endPrice = prices[i]!;
    const cumulativeReturn = (endPrice - startPrice) / startPrice;

    // Classify based on threshold
    const state = classifyStateFromReturn(cumulativeReturn, config);

    states.push({
      ticker,
      date: dates[i]!,
      state,
      cumulativeReturn,
    });
  }

  return states;
}

/**
 * Classify state directly from a cumulative return value.
 */
function classifyStateFromReturn(cumulativeReturn: number, config: Partial<StateConfig> = {}): MarketState {
  const { bullThreshold, bearThreshold } = { ...DEFAULT_CONFIG, ...config };

  if (cumulativeReturn >= bullThreshold) return 'bull';
  if (cumulativeReturn <= bearThreshold) return 'bear';
  return 'sideways';
}

/**
 * Get today's state from the most recent prices and dates.
 */
export function getCurrentState(
  ticker: string,
  prices: number[],
  dates: string[],
  config: Partial<StateConfig> = {},
): DailyState {
  const states = generateStateStream(ticker, prices, dates, config);
  if (states.length === 0) {
    throw new Error(`Cannot compute current state for ${ticker}: insufficient data`);
  }
  return states[states.length - 1]!;
}