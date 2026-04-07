const BASE = '/api/portfolio';
const FETCH_TIMEOUT_MS = 15000; // 15s timeout per request

async function req(method, path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    signal: controller.signal,
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(`${BASE}${path}`, opts);
    clearTimeout(timeout);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `请求失败: ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json();
  } catch (e) {
    clearTimeout(timeout);
    if (e.name === 'AbortError') throw new Error('请求超时，请检查网络连接');
    throw e;
  }
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
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    const url = `${BASE}/positions/export${account ? `?account=${encodeURIComponent(account)}` : ''}`;
    return fetch(url, { signal: controller.signal })
      .then(r => { clearTimeout(timeout); return r; })
      .then(r => { if (!r.ok) throw new Error(`导出失败: ${r.status}`); return r.blob(); })
      .catch(e => { clearTimeout(timeout); if (e.name === 'AbortError') throw new Error('请求超时'); throw e; });
  },

  // Recommendations
  getRecommendations: (date) =>
    req('GET', `/recommendations${date ? `?date=${date}` : ''}`),
  getRecommendation: (date, ticker) => req('GET', `/recommendations/${date}/${ticker}`),

  // Batch analysis
  startAnalysis: () => req('POST', '/analyze'),
};
