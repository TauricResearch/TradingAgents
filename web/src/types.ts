export type AssetMode = 'auto' | 'stock' | 'fund' | 'crypto'
export type JobStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelling' | 'cancelled' | 'interrupted' | 'budget_exhausted' | 'provider_rate_limited'

export interface ProviderRateLimitError {
  code: 'PROVIDER_RATE_LIMITED'
  message: string
  provider: string
  observed_at: string
  retry_after?: string
  cache_status: 'hit' | 'miss' | 'expired' | string
}

export interface Instrument {
  requested_symbol: string
  canonical_symbol: string
  asset_type: Exclude<AssetMode, 'auto'>
  fund_type?: string | null
  quote_type?: string | null
  name?: string | null
  exchange?: string | null
  currency?: string | null
  warnings: string[]
}

export interface AnalysisEvent {
  id: number
  job_id: string
  type: string
  timestamp: string
  data: Record<string, unknown>
}

export interface Metric {
  name: string
  value: number | null
  unit: string
  window?: string
  reason_if_unavailable?: string
}

export interface Snapshot {
  instrument: Record<string, unknown>
  profile: Record<string, number | string | null>
  metrics: Metric[]
  price_series: Array<{ date: string; adjusted_close: number; benchmark?: number }>
  top_holdings: Array<{ symbol?: string; name?: string; weight?: number }>
  sectors: Record<string, number>
  warnings: string[]
}

export interface AnalysisResult {
  asset_type: string
  company_of_interest: string
  trade_date: string
  benchmark_symbol: string
  fund_snapshot?: Snapshot | null
  [key: string]: unknown
}

export interface AnalysisState {
  status: JobStatus
  jobId?: string
  lastEventId: number
  connected: boolean
  agents: Record<string, string>
  reports: Record<string, string>
  result?: AnalysisResult
  error?: string
  providerRateLimit?: ProviderRateLimitError
  reportId?: string
  adviceId?: string
}

export interface AnalysisJob {
  job_id: string
  status: JobStatus
  result?: AnalysisResult
  error?: { code: string; message: string } & Partial<ProviderRateLimitError>
  report_id?: string
  advice_id?: string
  created_at: string
  updated_at: string
  resumable: boolean
  retry_of_job_id?: string | null
  retry_attempt?: number
  request: Record<string, unknown>
}

export interface EvidenceField {
  name: string
  value: unknown
  unit?: string | null
  source_reference: string
  retrieved_at: string
  effective_at?: string | null
  freshness_status: string
  normalization_warnings: string[]
}

export interface TrustAssessment {
  id: string
  level: 'trusted' | 'usable_with_warning' | 'insufficient'
  executable: boolean
  reason_codes: string[]
  warnings: string[]
  assessed_at: string
  evidence: EvidenceField[]
}

export interface UsageSummary {
  requests: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  retries: number
  token_usage_complete: boolean
  warnings: string[]
  limits?: Record<string, number>
}

export interface AdviceVersion {
  id: string
  report_id: string
  parent_id?: string | null
  version: number
  created_at: string
  action: string
  confidence: string
  reason: string
  eligibility: string
  trigger_message_ids: string[]
}

export interface ConversationMessage {
  id: string
  role: string
  content: string
  created_at: string
  source_references: string[]
  refreshed_data: boolean
  candidate_adjustment: boolean
}

export interface BackupPreview {
  backup_id: string
  valid: boolean
  compatible: boolean
  schema_version?: number | null
  created_at?: string | null
  size_bytes?: number | null
  reason?: string | null
}
