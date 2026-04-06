const BASE = '/api/portfolio';

async function req(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const portfolioApi = {
  // Watchlist
  getWatchlist: () => req('GET', '/watchlist'),
  addToWatchlist: (ticker, name) => req('POST', '/watchlist', { ticker, name }),
  removeFromWatchlist: (ticker) => req('DELETE', `/watchlist/${ticker}`),

  // Accounts
  getAccounts: () => req('GET', '/accounts'),
  createAccount: (name) => req('POST', '/accounts', { account_name: name }),
  deleteAccount: (name) => req('DELETE', `/accounts/${name}`),

  // Positions
  getPositions: (account) => req('GET', `/positions${account ? `?account=${encodeURIComponent(account)}` : ''}`),
  addPosition: (data) => req('POST', '/positions', data),
  removePosition: (ticker, positionId, account) => {
    const params = new URLSearchParams({ ticker });
    if (positionId) params.set('position_id', positionId);
    if (account) params.set('account', account);
    return req('DELETE', `/positions/${ticker}?${params}`);
  },
  exportPositions: (account) => {
    const url = `${BASE}/positions/export${account ? `?account=${encodeURIComponent(account)}` : ''}`;
    return fetch(url).then(r => r.blob());
  },

  // Recommendations
  getRecommendations: (date) =>
    req('GET', `/recommendations${date ? `?date=${date}` : ''}`),
  getRecommendation: (date, ticker) => req('GET', `/recommendations/${date}/${ticker}`),

  // Batch analysis
  startAnalysis: () => req('POST', '/analyze'),
};
