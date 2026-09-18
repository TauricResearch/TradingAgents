export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  ticker: string;
  trade_date: string;
  asset_type: 'stock' | 'crypto';
  analysts: string[];
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  max_debate_rounds: number;
  max_risk_discuss_rounds: number;
  output_language: string;
  status: JobStatus;
  progress: number;
  current_stage: string;
  decision_signal?: string | null;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
}

export interface JobCreatePayload {
  ticker: string;
  trade_date?: string;
  asset_type?: 'stock' | 'crypto';
  analysts?: string[];
  llm_provider?: string;
  deep_think_llm?: string;
  quick_think_llm?: string;
  max_debate_rounds?: number;
  max_risk_discuss_rounds?: number;
  output_language?: string;
}

export interface JobEvent {
  id: number;
  job_id: string;
  timestamp: string;
  event_type: string;
  data: Record<string, any>;
}

export interface JobReport {
  job_id: string;
  ticker: string;
  trade_date: string;
  recommendation?: string | null;
  executive_summary?: string | null;
  entry_price?: number | null;
  stop_loss?: number | null;
  target_price?: number | null;
  complete_report_md?: string | null;
  market_report_md?: string | null;
  sentiment_report_md?: string | null;
  news_report_md?: string | null;
  fundamentals_report_md?: string | null;
  investment_debate?: Record<string, any> | null;
  risk_debate?: Record<string, any> | null;
  trader_investment_plan?: string | null;
}

export interface ConfigOptions {
  providers: Array<{
    id: string;
    name: string;
    default_deep: string;
    default_quick: string;
  }>;
  models: Record<string, {
    quick: Array<{ label: string; value: string }>;
    deep: Array<{ label: string; value: string }>;
  }>;
  analysts: Array<{
    key: string;
    name: string;
    description: string;
  }>;
  languages: string[];
  default_config: Record<string, any>;
}

export interface MemoryEntry {
  trade_date?: string;
  ticker?: string;
  rating?: string;
  pending?: boolean;
  decision?: string;
  reflection?: string;
  raw_return?: number;
  alpha_return?: number;
}

export interface APIKeyInfo {
  provider: string;
  env_var: string;
  category: 'llm' | 'data';
  configured: boolean;
  preview: string;
}

export interface APIKeysStatusResponse {
  keys: APIKeyInfo[];
}

export interface APIKeysUpdateRequest {
  keys: Record<string, string>;
}

export interface BatchDeletePayload {
  job_ids: string[];
  force?: boolean;
}

export interface BatchDeleteResponse {
  message: string;
  deleted_count: number;
  job_ids: string[];
}

export interface DeleteJobResponse {
  message: string;
  job_id: string;
}

export interface ClearJobsResponse {
  message: string;
  deleted_count: number;
}

