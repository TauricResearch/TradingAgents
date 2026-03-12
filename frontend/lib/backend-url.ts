/**
 * Unified backend URL resolution for server-side proxying.
 *
 * Priority:
 *  1. BACKEND_URL          – explicit override (Railway / custom deployment)
 *  2. Development mode     – http://localhost:8000
 *  3. NEXT_PUBLIC_API_URL  – fallback (often set in Railway for client-side too)
 *  4. Docker Compose default – http://backend:8000
 *
 * Used by next.config.ts rewrites and Next.js API route handlers.
 */
export function getBackendUrl(): string {
  if (process.env.BACKEND_URL) {
    return process.env.BACKEND_URL;
  }

  if (process.env.NODE_ENV === "development") {
    return "http://localhost:8000";
  }

  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // Docker Compose internal hostname (only works when both services share a Docker network)
  return "http://backend:8000";
}
