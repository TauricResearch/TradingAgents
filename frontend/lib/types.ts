/**
 * TypeScript type definitions for TradingAgentsX API
 */

export interface AnalysisRequest {
  ticker: string;
  analysis_date: string;
  analysts?: string[];
  research_depth?: number;
  market_type?: "us" | "twse" | "tpex";  // 市場類型：美股、上市、上櫃/興櫃
  quick_think_llm?: string;
  deep_think_llm?: string;

  // API Configuration
  openai_api_key?: string;
  openai_base_url?: string;
  quick_think_base_url?: string;
  deep_think_base_url?: string;
  quick_think_api_key?: string;
  deep_think_api_key?: string;
  embedding_base_url?: string;
  embedding_api_key?: string;
  alpha_vantage_api_key?: string;
  finmind_api_key?: string;  // 台灣股市資料 API
}

export interface PriceData {
  Date: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  "Adj Close"?: number; // Optional adjusted close price
  Volume: number;
}

export interface PriceStats {
  growth_rate: number;
  duration_days: number;
  start_date: string;
  end_date: string;
  start_price: number;
  end_price: number;
}

export interface AnalysisResponse {
  status: string;
  ticker: string;
  analysis_date: string;
  decision?: any;
  reports?: any;
  error?: string;
  error_type?: string;
  retry_after?: number;
  quota_limit?: number;
  price_data?: PriceData[];
  price_stats?: PriceStats;
}

export interface Decision {
  action: string;
  quantity?: number;
  reasoning?: string;
  confidence?: number;
}

export interface Reports {
  market_report?: string;
  sentiment_report?: string;
  news_report?: string;
  fundamentals_report?: string;
  investment_plan?: string;
  trader_investment_plan?: string;
  final_trade_decision?: string;
  investment_debate_state?: DebateState;
  risk_debate_state?: DebateState;
}

export interface DebateState {
  bull_history?: string;
  bear_history?: string;
  risky_history?: string;
  safe_history?: string;
  neutral_history?: string;
  judge_decision?: string;
}

export interface ConfigResponse {
  available_analysts: string[];
  available_llms: {
    [provider: string]: string[];
  };
  default_config: {
    [key: string]: any;
  };
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}

export interface Ticker {
  symbol: string;
  name: string;
}

// Task Management Types

export interface TaskCreatedResponse {
  task_id: string;
  status: "pending";
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  progress?: string;
  result?: AnalysisResponse;
  error?: string;
  completed_at?: string;
}
