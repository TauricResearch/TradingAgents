export type Decision = 'BUY' | 'SELL' | 'HOLD';
export type Confidence = 'HIGH' | 'MEDIUM' | 'LOW';
export type Risk = 'HIGH' | 'MEDIUM' | 'LOW';

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

// Backtest Types
export interface PricePoint {
  date: string;
  price: number;
}

export interface BacktestResult {
  prediction_correct: boolean;
  actual_return_1d: number;   // next trading day percentage return
  actual_return_1w: number;   // percentage
  actual_return_1m: number;   // percentage
  price_at_prediction: number;
  current_price: number;
  price_history: PricePoint[];
}

export interface AccuracyMetrics {
  total_predictions: number;
  correct_predictions: number;
  success_rate: number;
  buy_accuracy: number;
  sell_accuracy: number;
  hold_accuracy: number;
}

// Date-level statistics for history page
export interface DateStats {
  date: string;
  avgReturn1d: number;        // Average next-day return for all stocks
  avgReturn1m: number;        // Average 1-month return
  totalStocks: number;
  correctPredictions: number;
  accuracy: number;
  buyCount: number;
  sellCount: number;
  holdCount: number;
}

export interface OverallStats {
  totalDays: number;
  totalPredictions: number;
  avgDailyReturn: number;
  avgMonthlyReturn: number;
  overallAccuracy: number;
  bestDay: { date: string; return: number } | null;
  worstDay: { date: string; return: number } | null;
}

export interface StockAnalysis {
  symbol: string;
  company_name: string;
  decision: Decision | null;
  confidence?: Confidence;
  risk?: Risk;
  raw_analysis?: string;
  hold_days?: number | null;
  rank?: number | null;
  error?: string | null;
}

export interface RankingResult {
  ranking: string;
  stocks_analyzed: number;
  timestamp: string;
  error?: string;
}

export interface TopPick {
  rank: number;
  symbol: string;
  company_name: string;
  decision: string;
  reason: string;
  risk_level: Risk;
}

export interface StockToAvoid {
  symbol: string;
  company_name: string;
  reason: string;
}

export interface DailyRecommendation {
  date: string;
  analysis: Record<string, StockAnalysis>;
  ranking?: RankingResult;  // Optional since API may not return it
  summary: {
    total: number;
    buy: number;
    sell: number;
    hold: number;
  };
  top_picks: TopPick[];
  stocks_to_avoid: StockToAvoid[];
}

export interface HistoricalEntry {
  date: string;
  symbol: string;
  company_name: string;
  decision: Decision;
  confidence?: Confidence;
  risk?: Risk;
  hold_days?: number | null;
  rank?: number | null;
}

export interface StockHistory {
  symbol: string;
  company_name: string;
  history: HistoricalEntry[];
  stats: {
    total_recommendations: number;
    buy_count: number;
    sell_count: number;
    hold_count: number;
    accuracy?: number;
  };
}

export interface NiftyStock {
  symbol: string;
  company_name: string;
  sector?: string;
}

// Nifty50 Index data point
export interface Nifty50IndexPoint {
  date: string;
  value: number;
  return: number; // daily return %
}

// Risk metrics for portfolio analysis
export interface RiskMetrics {
  sharpeRatio: number;      // (mean return - risk-free) / std dev
  maxDrawdown: number;      // peak-to-trough decline %
  winLossRatio: number;     // avg win / avg loss
  winRate: number;          // % of winning predictions
  volatility: number;       // std dev of returns
  totalTrades: number;
  // Additional calculation details for showing formulas
  meanReturn?: number;
  riskFreeRate?: number;
  winningTrades?: number;
  losingTrades?: number;
  avgWinReturn?: number;
  avgLossReturn?: number;
  peakValue?: number;
  troughValue?: number;
}

// Return distribution bucket
export interface ReturnBucket {
  range: string;       // e.g., "0% to 1%"
  min: number;
  max: number;
  count: number;
  stocks: string[];    // symbols in this bucket
}

// Filter state for History page
export interface FilterState {
  decision: 'ALL' | 'BUY' | 'SELL' | 'HOLD';
  confidence: 'ALL' | 'HIGH' | 'MEDIUM' | 'LOW';
  sector: string;
  sortBy: 'symbol' | 'return' | 'accuracy';
  sortOrder: 'asc' | 'desc';
}

// Accuracy trend data point
export interface AccuracyTrendPoint {
  date: string;
  overall: number;
  buy: number;
  sell: number;
  hold: number;
}

// Cumulative return data point for index comparison chart
export interface CumulativeReturnPoint {
  date: string;
  value: number;
  aiReturn: number;
  indexReturn: number;
}

export const NIFTY_50_STOCKS: NiftyStock[] = [
  { symbol: 'RELIANCE', company_name: 'Reliance Industries Ltd', sector: 'Energy' },
  { symbol: 'TCS', company_name: 'Tata Consultancy Services Ltd', sector: 'IT' },
  { symbol: 'HDFCBANK', company_name: 'HDFC Bank Ltd', sector: 'Banking' },
  { symbol: 'INFY', company_name: 'Infosys Ltd', sector: 'IT' },
  { symbol: 'ICICIBANK', company_name: 'ICICI Bank Ltd', sector: 'Banking' },
  { symbol: 'HINDUNILVR', company_name: 'Hindustan Unilever Ltd', sector: 'FMCG' },
  { symbol: 'ITC', company_name: 'ITC Ltd', sector: 'FMCG' },
  { symbol: 'SBIN', company_name: 'State Bank of India', sector: 'Banking' },
  { symbol: 'BHARTIARTL', company_name: 'Bharti Airtel Ltd', sector: 'Telecom' },
  { symbol: 'KOTAKBANK', company_name: 'Kotak Mahindra Bank Ltd', sector: 'Banking' },
  { symbol: 'LT', company_name: 'Larsen & Toubro Ltd', sector: 'Infrastructure' },
  { symbol: 'AXISBANK', company_name: 'Axis Bank Ltd', sector: 'Banking' },
  { symbol: 'ASIANPAINT', company_name: 'Asian Paints Ltd', sector: 'Consumer' },
  { symbol: 'MARUTI', company_name: 'Maruti Suzuki India Ltd', sector: 'Auto' },
  { symbol: 'HCLTECH', company_name: 'HCL Technologies Ltd', sector: 'IT' },
  { symbol: 'SUNPHARMA', company_name: 'Sun Pharmaceutical Industries Ltd', sector: 'Pharma' },
  { symbol: 'TITAN', company_name: 'Titan Company Ltd', sector: 'Consumer' },
  { symbol: 'BAJFINANCE', company_name: 'Bajaj Finance Ltd', sector: 'Finance' },
  { symbol: 'WIPRO', company_name: 'Wipro Ltd', sector: 'IT' },
  { symbol: 'ULTRACEMCO', company_name: 'UltraTech Cement Ltd', sector: 'Cement' },
  { symbol: 'NESTLEIND', company_name: 'Nestle India Ltd', sector: 'FMCG' },
  { symbol: 'NTPC', company_name: 'NTPC Ltd', sector: 'Power' },
  { symbol: 'POWERGRID', company_name: 'Power Grid Corporation of India Ltd', sector: 'Power' },
  { symbol: 'M&M', company_name: 'Mahindra & Mahindra Ltd', sector: 'Auto' },
  { symbol: 'TATAMOTORS', company_name: 'Tata Motors Ltd', sector: 'Auto' },
  { symbol: 'ONGC', company_name: 'Oil & Natural Gas Corporation Ltd', sector: 'Energy' },
  { symbol: 'JSWSTEEL', company_name: 'JSW Steel Ltd', sector: 'Metals' },
  { symbol: 'TATASTEEL', company_name: 'Tata Steel Ltd', sector: 'Metals' },
  { symbol: 'ADANIENT', company_name: 'Adani Enterprises Ltd', sector: 'Conglomerate' },
  { symbol: 'ADANIPORTS', company_name: 'Adani Ports and SEZ Ltd', sector: 'Infrastructure' },
  { symbol: 'COALINDIA', company_name: 'Coal India Ltd', sector: 'Mining' },
  { symbol: 'BAJAJFINSV', company_name: 'Bajaj Finserv Ltd', sector: 'Finance' },
  { symbol: 'TECHM', company_name: 'Tech Mahindra Ltd', sector: 'IT' },
  { symbol: 'HDFCLIFE', company_name: 'HDFC Life Insurance Company Ltd', sector: 'Insurance' },
  { symbol: 'SBILIFE', company_name: 'SBI Life Insurance Company Ltd', sector: 'Insurance' },
  { symbol: 'GRASIM', company_name: 'Grasim Industries Ltd', sector: 'Cement' },
  { symbol: 'DIVISLAB', company_name: "Divi's Laboratories Ltd", sector: 'Pharma' },
  { symbol: 'DRREDDY', company_name: "Dr. Reddy's Laboratories Ltd", sector: 'Pharma' },
  { symbol: 'CIPLA', company_name: 'Cipla Ltd', sector: 'Pharma' },
  { symbol: 'BRITANNIA', company_name: 'Britannia Industries Ltd', sector: 'FMCG' },
  { symbol: 'EICHERMOT', company_name: 'Eicher Motors Ltd', sector: 'Auto' },
  { symbol: 'APOLLOHOSP', company_name: 'Apollo Hospitals Enterprise Ltd', sector: 'Healthcare' },
  { symbol: 'INDUSINDBK', company_name: 'IndusInd Bank Ltd', sector: 'Banking' },
  { symbol: 'HEROMOTOCO', company_name: 'Hero MotoCorp Ltd', sector: 'Auto' },
  { symbol: 'TATACONSUM', company_name: 'Tata Consumer Products Ltd', sector: 'FMCG' },
  { symbol: 'BPCL', company_name: 'Bharat Petroleum Corporation Ltd', sector: 'Energy' },
  { symbol: 'UPL', company_name: 'UPL Ltd', sector: 'Chemicals' },
  { symbol: 'HINDALCO', company_name: 'Hindalco Industries Ltd', sector: 'Metals' },
  { symbol: 'BAJAJ-AUTO', company_name: 'Bajaj Auto Ltd', sector: 'Auto' },
  { symbol: 'LTIM', company_name: 'LTIMindtree Ltd', sector: 'IT' },
];
