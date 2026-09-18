import { 
  Job, 
  JobCreatePayload, 
  JobReport, 
  JobEvent, 
  ConfigOptions, 
  MemoryEntry, 
  APIKeysStatusResponse,
  DeleteJobResponse,
  BatchDeleteResponse,
  ClearJobsResponse
} from '../types';

const API_BASE = '/api/v1';

async function handleResponse<T>(res: Response, fallbackMessage: string): Promise<T> {
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || `${fallbackMessage}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchJobs(status?: string): Promise<{ jobs: Job[]; total: number }> {
  const url = status ? `${API_BASE}/jobs?status=${encodeURIComponent(status)}` : `${API_BASE}/jobs`;
  const res = await fetch(url);
  return handleResponse(res, 'Failed to fetch jobs');
}

export async function fetchJob(jobId: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  return handleResponse(res, `Failed to fetch job ${jobId}`);
}

export async function createJob(payload: JobCreatePayload): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse(res, 'Failed to create job');
}

export async function cancelJob(jobId: string): Promise<{ message: string; status: string }> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/cancel`, { method: 'POST' });
  return handleResponse(res, `Failed to cancel job ${jobId}`);
}

export async function deleteJob(jobId: string, force: boolean = false): Promise<DeleteJobResponse> {
  const url = force ? `${API_BASE}/jobs/${jobId}?force=true` : `${API_BASE}/jobs/${jobId}`;
  const res = await fetch(url, { method: 'DELETE' });
  return handleResponse(res, `Failed to delete job ${jobId}`);
}

export async function batchDeleteJobs(jobIds: string[], force: boolean = false): Promise<BatchDeleteResponse> {
  const res = await fetch(`${API_BASE}/jobs/batch-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_ids: jobIds, force }),
  });
  return handleResponse(res, 'Failed to delete selected jobs');
}

export async function clearJobsHistory(status?: string, allFinished: boolean = false): Promise<ClearJobsResponse> {
  let url = `${API_BASE}/jobs?`;
  if (status) {
    url += `status=${encodeURIComponent(status)}`;
  } else if (allFinished) {
    url += 'all_finished=true';
  }
  const res = await fetch(url, { method: 'DELETE' });
  return handleResponse(res, 'Failed to clear jobs history');
}

export async function fetchReport(jobId: string): Promise<JobReport> {
  const res = await fetch(`${API_BASE}/reports/${jobId}`);
  return handleResponse(res, 'Failed to fetch report');
}

export async function fetchJobHistory(jobId: string): Promise<JobEvent[]> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/history`);
  return handleResponse(res, 'Failed to fetch job history');
}

export async function fetchConfigOptions(): Promise<ConfigOptions> {
  const res = await fetch(`${API_BASE}/config/options`);
  return handleResponse(res, 'Failed to fetch config options');
}

export async function fetchMemoryLog(ticker?: string): Promise<{ total_entries: number; entries: MemoryEntry[] }> {
  const url = ticker ? `${API_BASE}/memory?ticker=${encodeURIComponent(ticker)}` : `${API_BASE}/memory`;
  const res = await fetch(url);
  return handleResponse(res, 'Failed to fetch memory');
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
  return handleResponse(res, 'Failed to fetch API keys');
}

export async function updateApiKeys(keys: Record<string, string>): Promise<APIKeysStatusResponse> {
  const res = await fetch(`${API_BASE}/config/keys`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keys }),
  });
  return handleResponse(res, 'Failed to update API keys');
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


