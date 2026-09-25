import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "tradingagents.apiKey";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, { method = "GET", apiKey, body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (apiKey) headers["X-API-Key"] = apiKey;

  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection.", 0);
  }

  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : null;

  if (!res.ok) {
    throw new ApiError(data?.detail || `Request failed (${res.status})`, res.status);
  }
  return data;
}

/**
 * Single point of contact with the TradingAgents API: owns the API key
 * (with an opt-in "remember on this device" persisted to localStorage) and
 * exposes one async function per endpoint. Components keep their own
 * loading/error state around these calls — this hook only isolates *how*
 * requests are made and authenticated, not each call site's UI state.
 */
export function useTradingApi() {
  const [apiKey, setApiKeyState] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || "";
    } catch {
      return "";
    }
  });
  const [remember, setRemember] = useState(() => {
    try {
      return Boolean(localStorage.getItem(STORAGE_KEY));
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      if (remember && apiKey) {
        localStorage.setItem(STORAGE_KEY, apiKey);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Storage unavailable (private mode, quota, etc.) — the key still
      // works for this session via React state, it just won't persist.
    }
  }, [apiKey, remember]);

  const setApiKey = useCallback((key) => setApiKeyState(key), []);

  const signup = useCallback(
    (email) => request("/api/signup", { method: "POST", body: { email } }),
    []
  );

  const fetchMe = useCallback(() => request("/api/me", { apiKey }), [apiKey]);

  const analyze = useCallback(
    (ticker, tradeDate) =>
      request("/api/analyze", {
        method: "POST",
        apiKey,
        body: { ticker, trade_date: tradeDate || null },
      }),
    [apiKey]
  );

  const fetchJob = useCallback((jobId) => request(`/api/jobs/${jobId}`, { apiKey }), [apiKey]);

  const fetchJobs = useCallback(() => request("/api/jobs", { apiKey }), [apiKey]);

  const checkout = useCallback(
    () => request("/api/billing/checkout", { method: "POST", apiKey }),
    [apiKey]
  );

  // Memoized so consumers that depend on the whole `api` object (e.g. a
  // useCallback/useEffect dependency array) only see a new reference when
  // something in it actually changed — not on every unrelated re-render of
  // whichever component called this hook.
  return useMemo(
    () => ({
      apiKey,
      setApiKey,
      remember,
      setRemember,
      signup,
      fetchMe,
      analyze,
      fetchJob,
      fetchJobs,
      checkout,
    }),
    [apiKey, setApiKey, remember, setRemember, signup, fetchMe, analyze, fetchJob, fetchJobs, checkout]
  );
}
