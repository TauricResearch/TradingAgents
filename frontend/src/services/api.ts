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

export interface StockAnalysis {
  symbol: string;
  company_name: string;
  decision: 'BUY' | 'SELL' | 'HOLD' | null;
  confidence?: 'HIGH' | 'MEDIUM' | 'LOW';
  risk?: 'HIGH' | 'MEDIUM' | 'LOW';
  raw_analysis?: string;
}

export interface TopPick {
  rank: number;
  symbol: string;
  company_name: string;
  decision: string;
  reason: string;
  risk_level: string;
}

export interface StockToAvoid {
  symbol: string;
  company_name: string;
  reason: string;
}

export interface Summary {
  total: number;
  buy: number;
  sell: number;
  hold: number;
}

export interface DailyRecommendation {
  date: string;
  analysis: Record<string, StockAnalysis>;
  summary: Summary;
  top_picks: TopPick[];
  stocks_to_avoid: StockToAvoid[];
}

export interface StockHistory {
  date: string;
  decision: string;
  confidence?: string;
  risk?: string;
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
  async runAnalysis(symbol: string, date?: string): Promise<{
    message: string;
    symbol: string;
    date: string;
    status: string;
  }> {
    const url = date ? `/analyze/${symbol}?date=${date}` : `/analyze/${symbol}`;
    return this.fetch(url, {
      method: 'POST',
      body: JSON.stringify({}),
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
  }> {
    return this.fetch(`/analyze/${symbol}/status`, { noCache: true });
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
}

export const api = new ApiService();

// Export a hook-friendly version for React Query or SWR
export default api;
