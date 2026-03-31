const DEV_FRONTEND_PORTS = new Set(["5173", "5174"]);
const DEFAULT_BACKEND_PORT = "8088";

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, "");

const configuredApiBase = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL?.trim() || "");

const getBackendOrigin = (): string => {
  if (configuredApiBase) {
    return new URL(configuredApiBase, window.location.origin).origin;
  }

  const { protocol, hostname, port, host } = window.location;
  if (DEV_FRONTEND_PORTS.has(port)) {
    return `${protocol}//${hostname}:${DEFAULT_BACKEND_PORT}`;
  }

  return `${protocol}//${host}`;
};

export const API_BASE = configuredApiBase || `${getBackendOrigin()}/api`;

export const buildWebSocketUrl = (runId: string): string => {
  const backendOrigin = getBackendOrigin();
  const backendUrl = new URL(backendOrigin);
  const protocol = backendUrl.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${backendUrl.host}/ws/stream/${encodeURIComponent(runId)}`;
};
