/**
 * TypeScript types for the analysis pipeline visualization
 */

// Agent types that perform analysis
export type AgentType = 'market' | 'news' | 'social_media' | 'fundamentals';

// Debate types in the system
export type DebateType = 'investment' | 'risk';

// Pipeline step status
export type PipelineStepStatus = 'pending' | 'running' | 'completed' | 'error';

/**
 * Individual agent's analysis report
 */
export interface AgentReport {
  agent_type: AgentType;
  report_content: string;
  data_sources_used: string[];
  created_at?: string;
}

/**
 * Map of agent reports by type
 */
export interface AgentReportsMap {
  market?: AgentReport;
  news?: AgentReport;
  social_media?: AgentReport;
  fundamentals?: AgentReport;
}

/**
 * Debate history for investment or risk debates
 */
export interface DebateHistory {
  debate_type: DebateType;
  // Investment debate fields
  bull_arguments?: string;
  bear_arguments?: string;
  // Risk debate fields
  risky_arguments?: string;
  safe_arguments?: string;
  neutral_arguments?: string;
  // Common fields
  judge_decision?: string;
  full_history?: string;
  created_at?: string;
}

/**
 * Map of debates by type
 */
export interface DebatesMap {
  investment?: DebateHistory;
  risk?: DebateHistory;
}

/**
 * Single step in the analysis pipeline
 */
export interface PipelineStep {
  step_number: number;
  step_name: string;
  status: PipelineStepStatus;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  output_summary?: string;
}

/**
 * Log entry for a data source fetch
 */
export interface DataSourceLog {
  source_type: string;
  source_name: string;
  data_fetched?: Record<string, unknown>;
  fetch_timestamp?: string;
  success: boolean;
  error_message?: string;
}

/**
 * Complete pipeline data for a single stock analysis
 */
export interface FullPipelineData {
  date: string;
  symbol: string;
  agent_reports: AgentReportsMap;
  debates: DebatesMap;
  pipeline_steps: PipelineStep[];
  data_sources: DataSourceLog[];
  status?: 'complete' | 'in_progress' | 'no_data';
}

/**
 * Summary of pipeline for a single stock (used in list views)
 */
export interface PipelineSummary {
  symbol: string;
  pipeline_steps: { step_name: string; status: PipelineStepStatus }[];
  agent_reports_count: number;
  has_debates: boolean;
}

/**
 * API response types
 */
export interface PipelineDataResponse extends FullPipelineData {}

export interface AgentReportsResponse {
  date: string;
  symbol: string;
  reports: AgentReportsMap;
  count: number;
}

export interface DebateHistoryResponse {
  date: string;
  symbol: string;
  debates: DebatesMap;
}

export interface DataSourcesResponse {
  date: string;
  symbol: string;
  data_sources: DataSourceLog[];
  count: number;
}

export interface PipelineSummaryResponse {
  date: string;
  stocks: PipelineSummary[];
  count: number;
}

/**
 * Pipeline step definitions (for UI rendering)
 */
export const PIPELINE_STEPS = [
  { number: 1, name: 'data_collection', label: 'Data Collection', icon: 'Database' },
  { number: 2, name: 'market_analysis', label: 'Market Analysis', icon: 'TrendingUp' },
  { number: 3, name: 'news_analysis', label: 'News Analysis', icon: 'Newspaper' },
  { number: 4, name: 'social_analysis', label: 'Social Analysis', icon: 'Users' },
  { number: 5, name: 'fundamentals_analysis', label: 'Fundamentals', icon: 'FileText' },
  { number: 6, name: 'investment_debate', label: 'Investment Debate', icon: 'MessageSquare' },
  { number: 7, name: 'trader_decision', label: 'Trader Decision', icon: 'Target' },
  { number: 8, name: 'risk_debate', label: 'Risk Assessment', icon: 'Shield' },
  { number: 9, name: 'final_decision', label: 'Final Decision', icon: 'CheckCircle' },
] as const;

/**
 * Agent metadata for UI rendering
 */
export const AGENT_METADATA: Record<AgentType, { label: string; icon: string; color: string; description: string }> = {
  market: {
    label: 'Market Analyst',
    icon: 'TrendingUp',
    color: 'blue',
    description: 'Analyzes technical indicators, price trends, and market patterns'
  },
  news: {
    label: 'News Analyst',
    icon: 'Newspaper',
    color: 'purple',
    description: 'Analyzes company news, macroeconomic trends, and market events'
  },
  social_media: {
    label: 'Social Media Analyst',
    icon: 'Users',
    color: 'pink',
    description: 'Analyzes social sentiment, Reddit discussions, and public perception'
  },
  fundamentals: {
    label: 'Fundamentals Analyst',
    icon: 'FileText',
    color: 'green',
    description: 'Analyzes financial statements, ratios, and company health'
  }
};

/**
 * Debate role metadata for UI rendering
 */
export const DEBATE_ROLES = {
  investment: {
    bull: { label: 'Bull Analyst', color: 'green', icon: 'TrendingUp' },
    bear: { label: 'Bear Analyst', color: 'red', icon: 'TrendingDown' },
    judge: { label: 'Research Manager', color: 'blue', icon: 'Scale' }
  },
  risk: {
    risky: { label: 'Aggressive Analyst', color: 'red', icon: 'Zap' },
    safe: { label: 'Conservative Analyst', color: 'green', icon: 'Shield' },
    neutral: { label: 'Neutral Analyst', color: 'gray', icon: 'Scale' },
    judge: { label: 'Risk Manager', color: 'blue', icon: 'ShieldCheck' }
  }
} as const;
