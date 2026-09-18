import { Job, JobCreatePayload, JobReport, JobEvent, ConfigOptions, MemoryEntry, APIKeysStatusResponse } from '../types';

const API_BASE = '/api/v1';

export async function fetchJobs(status?: string): Promise<{ jobs: Job[]; total: number }> {
  const url = status ? `${API_BASE}/jobs?status=${encodeURIComponent(status)}` : `${API_BASE}/jobs`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.statusText}`);
  return res.json();
}

export async function fetchJob(jobId: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Failed to fetch job ${jobId}: ${res.statusText}`);
  return res.json();
}

export async function createJob(payload: JobCreatePayload): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to create job: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelJob(jobId: string): Promise<{ message: string; status: string }> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to cancel job ${jobId}: ${res.statusText}`);
  return res.json();
}

export async function fetchReport(jobId: string): Promise<JobReport> {
  const res = await fetch(`${API_BASE}/reports/${jobId}`);
  if (!res.ok) throw new Error(`Failed to fetch report: ${res.statusText}`);
  return res.json();
}

export async function fetchJobHistory(jobId: string): Promise<JobEvent[]> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/history`);
  if (!res.ok) throw new Error(`Failed to fetch job history: ${res.statusText}`);
  return res.json();
}

export async function fetchConfigOptions(): Promise<ConfigOptions> {
  const res = await fetch(`${API_BASE}/config/options`);
  if (!res.ok) throw new Error(`Failed to fetch config options: ${res.statusText}`);
  return res.json();
}

export async function fetchMemoryLog(ticker?: string): Promise<{ total_entries: number; entries: MemoryEntry[] }> {
  const url = ticker ? `${API_BASE}/memory?ticker=${encodeURIComponent(ticker)}` : `${API_BASE}/memory`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch memory: ${res.statusText}`);
  return res.json();
}

export function subscribeToJobEvents(
  jobId: string,
  onEvent: (event: JobEvent) => void,
  onError?: (err: any) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/jobs/${jobId}/events`);

  const handleMessage = (e: MessageEvent) => {
    try {
      const parsed = JSON.parse(e.data);
      const eventType = e.type || parsed.event_type || 'message';
      onEvent({
        id: parsed.id || Date.now(),
        job_id: jobId,
        timestamp: parsed.timestamp || new Date().toISOString(),
        event_type: eventType,
        data: parsed.data || parsed,
      });

      // Terminal event: close event source immediately to prevent infinite browser reconnection
      if (
        eventType === 'stream_closed' ||
        eventType === 'job_completed' ||
        eventType === 'job_failed' ||
        eventType === 'job_cancelled'
      ) {
        eventSource.close();
      }
    } catch (err) {
      console.error('Failed to parse SSE message:', err, e.data);
    }
  };

  // Specific event type listeners
  const eventTypes = [
    'stage_change',
    'agent_completed',
    'debate_speech',
    'research_plan',
    'trader_proposal',
    'risk_speech',
    'final_decision',
    'job_started',
    'job_completed',
    'job_failed',
    'job_cancelled',
    'stream_closed',
  ];

  eventTypes.forEach((type) => {
    eventSource.addEventListener(type, handleMessage);
  });

  eventSource.onmessage = handleMessage;
  eventSource.onerror = (err) => {
    if (eventSource.readyState === EventSource.CLOSED) {
      return;
    }
    if (onError) onError(err);
  };

  return () => {
    eventSource.close();
  };
}


export async function fetchApiKeys(): Promise<APIKeysStatusResponse> {
  const res = await fetch(`${API_BASE}/config/keys`);
  if (!res.ok) throw new Error(`Failed to fetch API keys: ${res.statusText}`);
  return res.json();
}

export async function updateApiKeys(keys: Record<string, string>): Promise<APIKeysStatusResponse> {
  const res = await fetch(`${API_BASE}/config/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keys }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to update API keys: ${res.statusText}`);
  }
  return res.json();
}

export function getReportDownloadUrl(jobId: string, tab: string = 'complete'): string {
  return `${API_BASE}/reports/${jobId}/download?tab=${encodeURIComponent(tab)}`;
}

export function downloadReportMarkdown(
  jobId: string,
  ticker: string,
  tradeDate: string,
  tab: string = 'complete',
  directContent?: string
): void {
  const cleanTicker = ticker.replace(/[^a-zA-Z0-9_-]/g, '').toUpperCase() || 'REPORT';
  const cleanDate = (tradeDate || 'DATE').replace(/[^a-zA-Z0-9_-]/g, '') || 'DATE';
  const cleanTab = tab !== 'complete' && tab !== 'overview' ? tab.charAt(0).toUpperCase() + tab.slice(1) : 'Complete';
  const filename = `TradingAgents_${cleanTicker}_${cleanDate}_${cleanTab}.md`;

  if (directContent && directContent.trim().length > 0) {
    const blob = new Blob([directContent], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    return;
  }

  // Fallback to backend direct download URL
  const downloadUrl = getReportDownloadUrl(jobId, tab);
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}


