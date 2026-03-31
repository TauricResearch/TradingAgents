import { useState, useEffect, useRef } from 'react';
import { buildWebSocketUrl } from '../config/api';

export interface AgentEvent {
  id: string;
  timestamp: string;
  agent: string;
  tier: 'quick' | 'mid' | 'deep';
  type: 'thought' | 'tool' | 'tool_result' | 'result' | 'log' | 'system';
  message: string;
  /** Full prompt text (available on thought & result events). */
  prompt?: string;
  /** Full response text (available on result & tool_result events). */
  response?: string;
  /** Ticker symbol (e.g. "AAPL"), "MARKET" for scans, or portfolio id. */
  identifier?: string;
  node_id?: string;
  parent_node_id?: string;
  /** Data service used by this tool (e.g. "yfinance", "finnhub", "finviz"). */
  service?: string;
  /** Tool execution status: "running", "success", "error", or "graceful_skip". */
  status?: 'running' | 'success' | 'error' | 'graceful_skip';
  /** Error message when status is "error". */
  error?: string | null;
  metrics?: {
    model: string;
    tokens_in?: number;
    tokens_out?: number;
    latency_ms?: number;
    raw_json_response?: string;
  };
  details?: {
    model_used: string;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    raw_json_response: string;
  };
}

export const useAgentStream = (runId: string | null, reloadKey = 0, enabled = true) => {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'streaming' | 'completed' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  // Track status in a ref to avoid stale closures and infinite reconnect loops
  const statusRef = useRef(status);
  statusRef.current = status;
  const terminalStatusRef = useRef<'completed' | 'error' | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const sessionTokenRef = useRef(0);

  const clearReconnectTimer = () => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  };

  useEffect(() => {
    const invalidateSession = () => {
      sessionTokenRef.current += 1;
    };

    const closeSocket = () => {
      clearReconnectTimer();
      const currentSocket = socketRef.current;
      socketRef.current = null;
      if (currentSocket && (currentSocket.readyState === WebSocket.CONNECTING || currentSocket.readyState === WebSocket.OPEN)) {
        currentSocket.close();
      }
    };

    invalidateSession();
    closeSocket();

    if (!enabled || !runId) {
      terminalStatusRef.current = null;
      if (statusRef.current !== 'completed' && statusRef.current !== 'error') {
        setStatus('idle');
        setError(null);
      }
      return () => {
        invalidateSession();
        closeSocket();
      };
    }

    const sessionToken = ++sessionTokenRef.current;
    terminalStatusRef.current = null;
    setStatus('connecting');
    setError(null);

    const openSocket = (attempt: number) => {
      if (sessionToken !== sessionTokenRef.current || !runId || !enabled) return;

      const socket = new WebSocket(buildWebSocketUrl(runId));
      socketRef.current = socket;

      socket.onopen = () => {
        if (sessionToken !== sessionTokenRef.current) {
          socket.close();
          return;
        }
        clearReconnectTimer();
        setStatus('streaming');
        setError(null);
        console.log(`Connected to run: ${runId}`);
      };

      socket.onmessage = (event) => {
        if (sessionToken !== sessionTokenRef.current) return;

        let data: any;
        try {
          data = JSON.parse(event.data);
        } catch (parseError) {
          console.error('Failed to parse WebSocket payload', parseError);
          return;
        }

        if (data.type === 'system' && data.message === '__heartbeat__') {
          return;
        }

        if (data.type === 'system' && data.message === 'Run completed.') {
          terminalStatusRef.current = 'completed';
          setStatus('completed');
          socket.close();
          return;
        }

        if (data.type === 'system' && data.message?.startsWith('Error:')) {
          terminalStatusRef.current = 'error';
          setStatus('error');
          setError(data.message);
          socket.close();
          return;
        }

        setEvents((prev) => [...prev, data as AgentEvent]);
      };

      socket.onclose = () => {
        if (socketRef.current === socket) {
          socketRef.current = null;
        }
        if (sessionToken !== sessionTokenRef.current) {
          return;
        }
        if (terminalStatusRef.current === 'completed') {
          setStatus('completed');
          console.log(`Disconnected from run: ${runId}`);
          return;
        }
        if (terminalStatusRef.current === 'error') {
          setStatus('error');
          console.log(`Disconnected from run: ${runId}`);
          return;
        }

        const reconnectDelayMs = Math.min(1000 * Math.max(attempt + 1, 1), 5000);
        setStatus('connecting');
        setError('Connection lost. Reconnecting…');
        clearReconnectTimer();
        reconnectTimerRef.current = window.setTimeout(() => {
          openSocket(attempt + 1);
        }, reconnectDelayMs);
        console.warn(`Disconnected from run: ${runId}. Reconnecting in ${reconnectDelayMs}ms.`);
      };

      socket.onerror = (err) => {
        if (sessionToken !== sessionTokenRef.current) return;
        console.error(err);
      };
    };

    openSocket(0);

    return () => {
      invalidateSession();
      closeSocket();
    };
  }, [runId, reloadKey, enabled]);

  const clearEvents = () => setEvents([]);
  const replaceEvents = (nextEvents: AgentEvent[]) => setEvents(nextEvents);
  const setTerminalStatus = (nextStatus: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error', nextError: string | null = null) => {
    setStatus(nextStatus);
    setError(nextError);
  };

  return { events, status, error, clearEvents, replaceEvents, setTerminalStatus };
};
