/** Fetch wrapper: X-API-Key header + session cookie, 401 → auth dialog.
 *
 * On boot the AuthGate exchanges the stored key for an HttpOnly cookie
 * (POST /api/session) so EventSource and <a download> authenticate too.
 * The header is still attached to every fetch as belt-and-braces.
 */

const TOKEN_KEY = "proToken";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public url: string,
  ) {
    super(`HTTP ${status} for ${url}: ${detail}`);
  }
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

export function registerUnauthorizedHandler(handler: UnauthorizedHandler) {
  onUnauthorized = handler;
}

export function apiHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { "X-API-Key": token } : {};
}

export async function apiFetch<T = unknown>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { ...apiHeaders(), ...(init.headers ?? {}) },
  });
  if (response.status === 401) {
    onUnauthorized?.();
    throw new ApiError(401, "unauthorized", url);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail, url);
  }
  return (await response.json()) as T;
}

/** fetch with a hard timeout so a stalled boot request can never wedge the
 * AuthGate on "Connecting…" — an aborted request rejects and the gate falls
 * through to the login screen instead of hanging forever. */
async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  ms = 8_000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** Exchange the API key for the HttpOnly session cookie. Returns whether
 * the backend requires auth at all (open localhost dev = false). */
export async function establishSession(): Promise<{
  authenticated: boolean;
  auth_required: boolean;
}> {
  const response = await fetchWithTimeout("/api/session", {
    method: "POST",
    headers: apiHeaders(),
  });
  if (response.status === 401) throw new ApiError(401, "unauthorized", "/api/session");
  if (!response.ok)
    throw new ApiError(response.status, response.statusText, "/api/session");
  return (await response.json()) as { authenticated: boolean; auth_required: boolean };
}

/** Which login UI to render (open endpoint, no data). `firebase` is the
 * PUBLIC web-app config — present only when Google sign-in is enabled.
 * `stream_url` (when set) is the Cloud Run origin the EventSource should
 * connect to directly — Firebase Hosting's proxy can't carry SSE. */
export interface AuthConfig {
  auth_required: boolean;
  google: boolean;
  firebase: Record<string, string> | null;
  stream_url?: string | null;
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const response = await fetchWithTimeout("/api/auth/config");
  if (!response.ok)
    throw new ApiError(response.status, response.statusText, "/api/auth/config");
  return (await response.json()) as AuthConfig;
}

/** Exchange a Firebase ID token for the HttpOnly session cookie. The server
 * verifies the token and enforces its email allowlist (403 = signed in with
 * a Google account that isn't authorized). */
export async function establishGoogleSession(idToken: string): Promise<void> {
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail, "/api/session");
  }
}
