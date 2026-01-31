/**
 * API service for fetching stock recommendations from the backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
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
}

export const api = new ApiService();

// Export a hook-friendly version for React Query or SWR
export default api;
