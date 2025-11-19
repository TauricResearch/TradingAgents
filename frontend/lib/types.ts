// TypeScript types matching backend Pydantic schemas

export enum AnalystType {
  MARKET = "market",
  SOCIAL = "social",
  NEWS = "news",
  FUNDAMENTALS = "fundamentals",
}

export enum LLMProvider {
  OPENAI = "openai",
  ANTHROPIC = "anthropic",
  GOOGLE = "google",
  OPENROUTER = "openrouter",
  OLLAMA = "ollama",
}

export interface AnalysisRequest {
  ticker: string;
  analysis_date: string;
  analysts: AnalystType[];
  research_depth: number;
  llm_provider: LLMProvider;
  backend_url: string;
  quick_think_llm: string;
  deep_think_llm: string;
  data_vendors?: Record<string, string>;
}

export type AgentStatusType = "pending" | "in_progress" | "completed" | "error";

export interface AgentStatus {
  agent: string;
  status: AgentStatusType;
  team?: string;
}

export interface MessageUpdate {
  timestamp: string;
  type: string;
  content: string;
}

export interface ToolCallUpdate {
  timestamp: string;
  tool_name: string;
  args: Record<string, any>;
}

export interface ReportSection {
  section_name: string;
  content: string;
  updated_at: string;
}

export type AnalysisStatusType = "pending" | "running" | "completed" | "error";

export interface AnalysisStatus {
  analysis_id: string;
  status: AnalysisStatusType;
  ticker: string;
  analysis_date: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export type StreamUpdateType =
  | "status"
  | "message"
  | "tool_call"
  | "report"
  | "agent_status"
  | "debate_update"
  | "risk_debate_update"
  | "final_decision";

export interface StreamUpdate {
  type: StreamUpdateType;
  data: Record<string, any>;
  timestamp: string;
}

export interface InvestmentDebateState {
  bull_history?: string;
  bear_history?: string;
  judge_decision?: string;
  count: number;
}

export interface RiskDebateState {
  risky_history?: string;
  safe_history?: string;
  neutral_history?: string;
  current_risky_response?: string;
  current_safe_response?: string;
  current_neutral_response?: string;
  judge_decision?: string;
  count: number;
}

export interface AnalysisResults {
  analysis_id: string;
  ticker: string;
  analysis_date: string;
  market_report?: string;
  sentiment_report?: string;
  news_report?: string;
  fundamentals_report?: string;
  investment_debate_state?: InvestmentDebateState;
  trader_investment_plan?: string;
  risk_debate_state?: RiskDebateState;
  final_trade_decision?: string;
  processed_signal?: string;
  completed_at: string;
}

export interface HistoricalAnalysisSummary {
  ticker: string;
  analysis_date: string;
  completed_at?: string;
  has_results: boolean;
}

export interface ConfigPreset {
  name: string;
  description?: string;
  config: Record<string, any>;
  created_at: string;
}

