/**
 * API service for fetching stock recommendations from the backend.
 * Updated with cache-busting for refresh functionality.
 */

import type {
  FullPipelineData,
  AgentReportsMap,
  DebatesMap,
  DataSourceLog,
  PipelineSummary
} from '../types/pipeline';

// Import types from the centralized types file
import type {
  StockAnalysis,
  TopPick,
  StockToAvoid,
  DailyRecommendation,
} from '../types';

// Re-export types for consumers who import from api.ts
export type { StockAnalysis, TopPick, StockToAvoid, DailyRecommendation };

// Use same hostname as the page, just different port for API
const getApiBaseUrl = () => {
  // If env variable is set, use it
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  // Otherwise use the same host as the current page with port 8001
  const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  return `http://${hostname}:8001`;
};

const API_BASE_URL = getApiBaseUrl();

export interface Summary {
  total: number;
  buy: number;
  sell: number;
  hold: number;
}

export interface StockHistory {
  date: string;
  decision: string;
  confidence?: string;
  risk?: string;
  hold_days?: number | null;
}

/**
 * Analysis configuration options
 */
export interface AnalysisConfig {
  deep_think_model?: string;
  quick_think_model?: string;
  provider?: string;
  api_key?: string;
  max_debate_rounds?: number;
}

class ApiService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = API_BASE_URL;
  }

  private async fetch<T>(endpoint: string, options?: RequestInit & { noCache?: boolean }): Promise<T> {
    let url = `${this.baseUrl}${endpoint}`;

    // Add cache-busting query param if noCache is true
    const noCache = options?.noCache;
    if (noCache) {
      const separator = url.includes('?') ? '&' : '?';
      url = `${url}${separator}_t=${Date.now()}`;
    }

    // Remove noCache from options before passing to fetch
    const { noCache: _, ...fetchOptions } = options || {};

    const response = await fetch(url, {
      ...fetchOptions,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions?.headers,
      },
      cache: noCache ? 'no-store' : undefined,
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get all daily recommendations
   */
  async getAllRecommendations(): Promise<{ recommendations: DailyRecommendation[]; count: number }> {
    return this.fetch('/recommendations');
  }

  /**
   * Get the latest recommendation
   */
  async getLatestRecommendation(): Promise<DailyRecommendation> {
    return this.fetch('/recommendations/latest');
  }

  /**
   * Get recommendation for a specific date
   */
  async getRecommendationByDate(date: string): Promise<DailyRecommendation> {
    return this.fetch(`/recommendations/${date}`);
  }

  /**
   * Get historical recommendations for a stock
   */
  async getStockHistory(symbol: string): Promise<{ symbol: string; history: StockHistory[]; count: number }> {
    return this.fetch(`/stocks/${symbol}/history`);
  }

  /**
   * Get all available dates
   */
  async getAvailableDates(): Promise<{ dates: string[]; count: number }> {
    return this.fetch('/dates');
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string; database: string }> {
    return this.fetch('/health');
  }

  /**
   * Save a new recommendation (used by the analyzer)
   */
  async saveRecommendation(recommendation: {
    date: string;
    analysis: Record<string, StockAnalysis>;
    summary: Summary;
    top_picks: TopPick[];
    stocks_to_avoid: StockToAvoid[];
  }): Promise<{ message: string }> {
    return this.fetch('/recommendations', {
      method: 'POST',
      body: JSON.stringify(recommendation),
    });
  }

  // ============== Pipeline Data Methods ==============

  /**
   * Get full pipeline data for a stock on a specific date
   */
  async getPipelineData(date: string, symbol: string, refresh = false): Promise<FullPipelineData> {
    return this.fetch(`/recommendations/${date}/${symbol}/pipeline`, { noCache: refresh });
  }

  /**
   * Get agent reports for a stock on a specific date
   */
  async getAgentReports(date: string, symbol: string): Promise<{
    date: string;
    symbol: string;
    reports: AgentReportsMap;
    count: number;
  }> {
    return this.fetch(`/recommendations/${date}/${symbol}/agents`);
  }

  /**
   * Get debate history for a stock on a specific date
   */
  async getDebateHistory(date: string, symbol: string): Promise<{
    date: string;
    symbol: string;
    debates: DebatesMap;
  }> {
    return this.fetch(`/recommendations/${date}/${symbol}/debates`);
  }

  /**
   * Get data source logs for a stock on a specific date
   */
  async getDataSources(date: string, symbol: string): Promise<{
    date: string;
    symbol: string;
    data_sources: DataSourceLog[];
    count: number;
  }> {
    return this.fetch(`/recommendations/${date}/${symbol}/data-sources`);
  }

  /**
   * Get pipeline summary for all stocks on a specific date
   */
  async getPipelineSummary(date: string): Promise<{
    date: string;
    stocks: PipelineSummary[];
    count: number;
  }> {
    return this.fetch(`/recommendations/${date}/pipeline-summary`);
  }

  /**
   * Save pipeline data for a stock (used by the analyzer)
   */
  async savePipelineData(data: {
    date: string;
    symbol: string;
    agent_reports?: Record<string, unknown>;
    investment_debate?: Record<string, unknown>;
    risk_debate?: Record<string, unknown>;
    pipeline_steps?: unknown[];
    data_sources?: unknown[];
  }): Promise<{ message: string }> {
    return this.fetch('/pipeline', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ============== Analysis Trigger Methods ==============

  /**
   * Start analysis for a stock
   */
  async runAnalysis(symbol: string, date?: string, config?: AnalysisConfig): Promise<{
    message: string;
    symbol: string;
    date: string;
    status: string;
  }> {
    const url = date ? `/analyze/${symbol}?date=${date}` : `/analyze/${symbol}`;
    return this.fetch(url, {
      method: 'POST',
      body: JSON.stringify(config || {}),
      noCache: true,
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache'
      }
    });
  }

  /**
   * Get analysis status for a stock
   */
  async getAnalysisStatus(symbol: string): Promise<{
    symbol: string;
    status: string;
    progress?: string;
    error?: string;
    decision?: string;
    started_at?: string;
    completed_at?: string;
    steps_completed?: number;
    steps_total?: number;
    steps_running?: string[];
    pipeline_steps?: Record<string, { status: string; duration_ms?: number }>;
  }> {
    return this.fetch(`/analyze/${symbol}/status`, { noCache: true });
  }

  /**
   * Cancel a running analysis for a stock
   */
  async cancelAnalysis(symbol: string): Promise<{
    message: string;
    symbol: string;
    status: string;
  }> {
    return this.fetch(`/analyze/${symbol}/cancel`, { method: 'POST', noCache: true });
  }

  /**
   * Get all running analyses
   */
  async getRunningAnalyses(): Promise<{
    running: Record<string, unknown>;
    count: number;
  }> {
    return this.fetch('/analyze/running', { noCache: true });
  }

  /**
   * Start bulk analysis for all Nifty 50 stocks
   */
  async runBulkAnalysis(date?: string, config?: {
    deep_think_model?: string;
    quick_think_model?: string;
    provider?: string;
    api_key?: string;
    max_debate_rounds?: number;
    parallel_workers?: number;
  }): Promise<{
    message: string;
    date: string;
    total_stocks: number;
    skipped?: number;
    status: string;
  }> {
    const url = date ? `/analyze/all?date=${date}` : '/analyze/all';
    return this.fetch(url, {
      method: 'POST',
      body: JSON.stringify(config || {}),
      noCache: true
    });
  }

  /**
   * Get bulk analysis status
   */
  async getBulkAnalysisStatus(): Promise<{
    status: string;
    total: number;
    completed: number;
    failed: number;
    skipped?: number;
    current_symbol: string | null;
    current_symbols: string[];
    started_at: string | null;
    completed_at: string | null;
    results: Record<string, string>;
    parallel_workers?: number;
    stock_progress?: Record<string, { done: number; total: number; current: string | null }>;
    cancelled?: boolean;
  }> {
    return this.fetch('/analyze/all/status', { noCache: true });
  }

  /**
   * Cancel bulk analysis
   */
  async cancelBulkAnalysis(): Promise<{
    message: string;
    completed: number;
    total: number;
    status: string;
  }> {
    return this.fetch('/analyze/all/cancel', { method: 'POST', noCache: true });
  }

  // ============== Schedule Methods ==============

  /**
   * Set the auto-analyze schedule
   */
  async setSchedule(config: {
    enabled: boolean;
    time: string;
    config: Record<string, unknown>;
  }): Promise<{ status: string; message: string }> {
    return this.fetch('/settings/schedule', {
      method: 'POST',
      body: JSON.stringify(config),
      noCache: true,
    });
  }

  /**
   * Get the current auto-analyze schedule
   */
  async getSchedule(): Promise<{
    enabled: boolean;
    time: string;
    config: Record<string, unknown>;
    last_run_date: string | null;
  }> {
    return this.fetch('/settings/schedule', { noCache: true });
  }

  // ============== Stock Price History Methods ==============

  /**
   * Get real historical closing prices for a stock from yfinance
   */
  async getStockPriceHistory(symbol: string, days: number = 90): Promise<{
    symbol: string;
    prices: Array<{ date: string; price: number }>;
    error?: string;
  }> {
    return this.fetch(`/stocks/${symbol}/prices?days=${days}`);
  }

  // ============== Nifty50 Index Methods ==============

  /**
   * Get Nifty50 index closing prices for recommendation date range
   */
  async getNifty50History(): Promise<{
    dates: string[];
    prices: Record<string, number>;
    error?: string;
  }> {
    return this.fetch('/nifty50/history');
  }

  // ============== History Bundle ==============

  /**
   * Get all data the History page needs in a single call.
   * Returns recommendations + all backtest results + accuracy metrics + nifty50 prices.
   */
  async getHistoryBundle(): Promise<{
    recommendations: DailyRecommendation[];
    backtest_by_date: Record<string, Record<string, {
      return_1d?: number;
      return_1w?: number;
      return_1m?: number;
      return_at_hold?: number;
      hold_days?: number;
      prediction_correct?: boolean;
      decision: string;
    }>>;
    accuracy: {
      overall_accuracy: number;
      total_predictions: number;
      correct_predictions: number;
      by_decision: Record<string, { accuracy: number; total: number; correct: number }>;
      by_confidence: Record<string, { accuracy: number; total: number; correct: number }>;
    };
    nifty50_prices: Record<string, number>;
  }> {
    return this.fetch('/history/bundle');
  }

  // ============== Backtest Methods ==============

  /**
   * Get backtest result for a specific stock and date
   */
  async getBacktestResult(date: string, symbol: string): Promise<{
    available: boolean;
    reason?: string;
    prediction_correct?: boolean;
    actual_return_1d?: number;
    actual_return_1w?: number;
    actual_return_1m?: number;
    price_at_prediction?: number;
    current_price?: number;
    price_history?: Array<{ date: string; price: number }>;
    hold_days?: number | null;
    return_at_hold?: number | null;
  }> {
    return this.fetch(`/backtest/${date}/${symbol}`, { noCache: true });
  }

  /**
   * Get all backtest results for a specific date
   */
  async getBacktestResultsForDate(date: string): Promise<{
    date: string;
    results: Array<{
      symbol: string;
      decision: string;
      price_at_prediction: number;
      return_1d?: number;
      return_1w?: number;
      return_1m?: number;
      return_at_hold?: number;
      hold_days?: number;
      prediction_correct?: boolean;
    }>;
  }> {
    return this.fetch(`/backtest/${date}`);
  }

  /**
   * Get detailed backtest data with live prices, formulas, agent reports
   */
  async getDetailedBacktest(date: string): Promise<{
    date: string;
    total_stocks: number;
    stocks: Array<{
      symbol: string;
      company_name: string;
      rank?: number;
      decision: string;
      confidence: string;
      risk: string;
      hold_days: number;
      hold_days_elapsed: number;
      hold_period_active: boolean;
      price_at_prediction: number | null;
      price_current: number | null;
      price_at_hold_end: number | null;
      return_current: number | null;
      return_at_hold: number | null;
      prediction_correct: boolean | null;
      formula: string;
      raw_analysis: string;
      agent_summary: Record<string, string>;
      debate_summary: Record<string, string>;
    }>;
  }> {
    return this.fetch(`/backtest/${date}/detailed`, { noCache: true });
  }

  /**
   * Calculate backtest for all recommendations on a date
   */
  async calculateBacktest(date: string): Promise<{
    status: string;
    date: string;
    message: string;
  }> {
    return this.fetch(`/backtest/${date}/calculate`, { method: 'POST' });
  }

  /**
   * Get overall accuracy metrics from backtest results
   */
  async getAccuracyMetrics(): Promise<{
    overall_accuracy: number;
    total_predictions: number;
    correct_predictions: number;
    by_decision: Record<string, { accuracy: number; total: number; correct: number }>;
    by_confidence: Record<string, { accuracy: number; total: number; correct: number }>;
  }> {
    return this.fetch('/backtest/accuracy', { noCache: true });
  }
}

export const api = new ApiService();

// Export a hook-friendly version for React Query or SWR
export default api;
