/** Browser → Binance WS for BTC ticks (free, keyless). One shared socket,
 * exponential backoff with jitter, rAF-throttled store writes so a busy
 * tape can't melt React. Falls back silently — the backend bars endpoint
 * keeps charts alive when WS is blocked (corporate proxies, geo blocks).
 * Host is configurable in Settings for binance.us regions. */
import { useEffect } from "react";

import { useTickerStore } from "@/stores/ticker";

const DEFAULT_HOST = "wss://stream.binance.com:9443";
const HOST_KEY = "binanceWsHost";

export function binanceHost(): string {
  return localStorage.getItem(HOST_KEY) ?? DEFAULT_HOST;
}

export function setBinanceHost(host: string) {
  localStorage.setItem(HOST_KEY, host);
}

interface MiniTicker {
  s: string; // symbol e.g. BTCUSDT
  c: string; // close (last)
}

let socket: WebSocket | null = null;
let refCount = 0;
let attempt = 0;
let closedByUs = false;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pending: MiniTicker | null = null;
let rafHandle = 0;

const DISPLAY: Record<string, string> = { BTCUSDT: "BTC-USD" };

function flush() {
  rafHandle = 0;
  if (!pending) return;
  const symbol = DISPLAY[pending.s] ?? pending.s;
  useTickerStore.getState().setTick(symbol, {
    last: parseFloat(pending.c),
    bid: null,
    ask: null,
    at: Date.now(),
    source: "binance",
  });
  pending = null;
}

function connect() {
  closedByUs = false;
  socket = new WebSocket(`${binanceHost()}/ws/btcusdt@miniTicker`);
  socket.onopen = () => {
    attempt = 0;
  };
  socket.onmessage = (event) => {
    try {
      pending = JSON.parse(event.data as string) as MiniTicker;
      if (!rafHandle) rafHandle = requestAnimationFrame(flush);
    } catch {
      /* ignore malformed frame */
    }
  };
  socket.onclose = () => {
    socket = null;
    if (closedByUs || refCount === 0) return;
    const backoff = Math.min(30_000, 1_000 * 2 ** attempt);
    const jitter = backoff * (0.5 + Math.random() * 0.5);
    attempt += 1;
    reconnectTimer = setTimeout(connect, jitter);
  };
  socket.onerror = () => socket?.close();
}

function acquire() {
  refCount += 1;
  if (!socket && !reconnectTimer) connect();
}

function release() {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0) {
    closedByUs = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
    socket?.close();
    socket = null;
  }
}

/** Mount once per view that needs live BTC. Ref-counted. */
export function useBinanceTicker(enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    acquire();
    const onVisibility = () => {
      // paused tab for >60s: drop the socket, reacquire on return
      if (document.hidden) release();
      else acquire();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      release();
    };
  }, [enabled]);
}
