// Thin JSON API client. Every state-changing call sends application/json
// (the server rejects anything else).

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw await apiError(response);
  return response.json();
}

async function apiError(response) {
  let detail = `${response.status} ${response.statusText}`;
  let body = null;
  try {
    body = await response.json();
    if (body.detail) {
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    /* non-JSON error body */
  }
  const error = new Error(detail);
  error.status = response.status;
  error.body = body;
  return error;
}

export const api = {
  health: () => getJSON('/api/health'),
  providers: () => getJSON('/api/providers'),
  config: () => getJSON('/api/config'),
  runs: () => getJSON('/api/runs'),
  run: (runId) => getJSON(`/api/runs/${encodeURIComponent(runId)}`),
  report: (ticker, date) =>
    getJSON(`/api/runs/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}/report`),

  async startRun(body) {
    const response = await fetch('/api/runs', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw await apiError(response);
    return response.json();
  },

  async cancelRun(runId) {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{}',
    });
    if (!response.ok) throw await apiError(response);
    return response.json();
  },
};
