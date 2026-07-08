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

/** Exchange the API key for the HttpOnly session cookie. Returns whether
 * the backend requires auth at all (open localhost dev = false). */
export async function establishSession(): Promise<{
  authenticated: boolean;
  auth_required: boolean;
}> {
  const response = await fetch("/api/session", {
    method: "POST",
    headers: apiHeaders(),
  });
  if (response.status === 401) throw new ApiError(401, "unauthorized", "/api/session");
  if (!response.ok)
    throw new ApiError(response.status, response.statusText, "/api/session");
  return (await response.json()) as { authenticated: boolean; auth_required: boolean };
}
