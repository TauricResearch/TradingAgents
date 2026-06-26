import type { WsEvent } from "./events";

export interface SubscribeOpts {
  url: string | (() => string);
  onMessage: (evt: WsEvent) => void;
  onStatus?: (status: "connecting" | "open" | "reconnecting" | "closed") => void;
  backoffMs?: (attempt: number) => number;
  onReconnect?: (attempt: number, delayMs: number) => void;
}

export class ResilientWs {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private closedByUser = false;
  private opts: SubscribeOpts;

  constructor(opts: SubscribeOpts) {
    this.opts = opts;
  }

  start() {
    this.closedByUser = false;
    this.connect();
  }

  stop() {
    this.closedByUser = true;
    if (this.ws && this.ws.readyState !== WebSocket.CONNECTING) {
      this.ws.close();
    }
    this.ws = null;
    this.opts.onStatus?.("closed");
  }

  private connect() {
    if (this.closedByUser) return;
    this.opts.onStatus?.(this.attempt === 0 ? "connecting" : "reconnecting");
    const url = typeof this.opts.url === "function" ? this.opts.url() : this.opts.url;
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.onopen = () => {
      if (this.closedByUser || this.ws !== ws) {
        ws.close();
        return;
      }
      this.attempt = 0;
      this.opts.onStatus?.("open");
    };
    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse((e as MessageEvent).data as string) as WsEvent;
        this.opts.onMessage(evt);
      } catch {
        // ignore malformed
      }
    };
    ws.onclose = () => {
      if (this.closedByUser) return;
      const attempt = this.attempt++;
      const delay = (this.opts.backoffMs ?? defaultBackoff)(attempt);
      this.opts.onReconnect?.(attempt, delay);
      setTimeout(() => this.connect(), delay);
    };
    ws.onerror = () => {
      // close will follow
    };
  }
}

function defaultBackoff(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 30_000);
}

export function buildRunUrl(runId: string, since?: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const base = `${proto}//${location.host}/ws/runs/${runId}`;
  return since ? `${base}?since=${encodeURIComponent(since)}` : base;
}

export function buildGlobalUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/global`;
}

export function buildLogsUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/ws/logs`;
}
