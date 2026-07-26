import type { AdviceVersion, AnalysisJob, AssetMode, BackupPreview, ChinaFundCandidate, ChinaFundEvaluation, ChinaFundSnapshot, ConversationMessage, Instrument, TrustAssessment, UsageSummary } from './types'

async function json<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) {
    throw new Error(body.detail?.message ?? body.detail ?? 'Request failed')
  }
  return body as T
}

export function resolveInstrument(symbol: string, asset_type: AssetMode) {
  return fetch('/api/instruments/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, asset_type }),
  }).then(json<Instrument>)
}

export function createAnalysis(payload: Record<string, unknown>) {
  return fetch('/api/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(json<{ job_id: string; status: string }>)
}

export function cancelAnalysis(jobId: string) {
  return fetch(`/api/analyses/${jobId}/cancel`, { method: 'POST' }).then(json<{ status: string }>)
}
export function resumeAnalysis(jobId: string) { return fetch(`/api/analyses/${jobId}/resume`, { method: 'POST' }).then(json<{ job_id: string; status: string }>) }
export function retryAnalysis(jobId: string) { return fetch(`/api/analyses/${jobId}/retry`, { method: 'POST' }).then(json<{ job_id: string; status: string; retry_of_job_id: string }>) }

export function listAnalyses() { return fetch('/api/analyses').then(json<{ items: AnalysisJob[] }>).then(value => value.items) }
export function getAnalysis(jobId: string) { return fetch(`/api/analyses/${jobId}`).then(json<AnalysisJob>) }
export function getTrust(jobId: string) { return fetch(`/api/analyses/${jobId}/trust`).then(json<TrustAssessment>) }
export function getUsage(jobId: string) { return fetch(`/api/analyses/${jobId}/usage`).then(json<{ summary: UsageSummary }>) }
export function getOptions() { return fetch('/api/config/options').then(json<{ budget?: { limits: Record<string, number>; historical_estimate?: { requests: number; tokens: number; basis: number } | null; monetary_estimate: string; daily_usage: { requests: number; tokens: number } } }>) }
export function listVersions(reportId: string) { return fetch(`/api/reports/${reportId}/versions`).then(json<{ items: AdviceVersion[] }>).then(value => value.items) }
export function createConversation(reportId: string) { return fetch(`/api/reports/${reportId}/conversations`, { method: 'POST' }).then(json<{ id: string }>) }
export function getConversation(conversationId: string) { return fetch(`/api/conversations/${conversationId}`).then(json<{ id: string; messages: ConversationMessage[] }>) }
export function sendMessage(conversationId: string, content: string, refresh_data: boolean, candidate_adjustment: boolean) {
  return fetch(`/api/conversations/${conversationId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, refresh_data, candidate_adjustment }) }).then(json<{ user: ConversationMessage; assistant: ConversationMessage }>)
}
export function reevaluate(conversationId: string, trigger_message_ids: string[]) {
  return fetch(`/api/conversations/${conversationId}/re-evaluate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ trigger_message_ids }) }).then(json<AdviceVersion>)
}
export function listBackups() { return fetch('/api/admin/backups').then(json<{ items: BackupPreview[] }>).then(value => value.items) }
export function createBackup() { return fetch('/api/admin/backup', { method: 'POST' }).then(json<BackupPreview>) }
export function previewRestore(backup_id: string) { return fetch('/api/admin/restore/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ backup_id }) }).then(json<BackupPreview>) }
export function commitRestore(backup_id: string) { return fetch('/api/admin/restore/commit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ backup_id }) }).then(json<BackupPreview & { restored: boolean }>) }
export function searchChinaFunds(q: string) { return fetch(`/api/funds/search?q=${encodeURIComponent(q)}`).then(json<{ items: ChinaFundCandidate[] }>).then(value => value.items) }
export function getChinaFundSnapshot(code: string, analysisDate?: string) { return fetch(`/api/funds/${code}/snapshot${analysisDate ? `?analysis_date=${encodeURIComponent(analysisDate)}` : ''}`).then(json<ChinaFundSnapshot>) }
export function evaluateChinaFund(code: string, payload: Record<string, unknown>) { return fetch(`/api/funds/${code}/evaluate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(json<{ snapshot: ChinaFundSnapshot; evaluation: ChinaFundEvaluation; formal_advice: { version: number } | null }>) }
