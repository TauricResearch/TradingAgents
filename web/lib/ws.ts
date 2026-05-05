// WebSocket helpers. The Next.js dev server proxies HTTP `/api/*` to the
// FastAPI service, but WS isn't proxied through `rewrites()`, so we
// connect directly. NEXT_PUBLIC_WS_BASE controls the destination
// (defaults to localhost:8000 for dev; reverse-proxy URL in prod).

export function wsBase(): string {
  if (typeof window === "undefined") return "ws://localhost:8000";
  const fromEnv = process.env.NEXT_PUBLIC_WS_BASE;
  if (fromEnv) return fromEnv;
  // Fall back to same host on a fixed port. Override for production.
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.hostname}:8000`;
}

export function runStreamUrl(runId: string): string {
  return `${wsBase()}/runs/${runId}/stream`;
}

export function chatStreamUrl(runId: string): string {
  return `${wsBase()}/runs/${runId}/chat/stream`;
}
