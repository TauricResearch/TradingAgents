import { useState, useEffect, useCallback, useRef } from 'react';

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

  const connect = useCallback(() => {
    if (!enabled || !runId) return;

    setStatus('connecting');
    setError(null);
    terminalStatusRef.current = null;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = '127.0.0.1:8088'; // Hardcoded for local dev to match backend
    const socket = new WebSocket(`${protocol}//${host}/ws/stream/${runId}`);

    socket.onopen = () => {
      setStatus('streaming');
      console.log(`Connected to run: ${runId}`);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'system' && data.message === 'Run completed.') {
        terminalStatusRef.current = 'completed';
        setStatus('completed');
        socket.close();
      } else if (data.type === 'system' && data.message?.startsWith('Error:')) {
        terminalStatusRef.current = 'error';
        setStatus('error');
        setError(data.message);
        socket.close();
      } else {
        setEvents((prev) => [...prev, data as AgentEvent]);
      }
    };

    socket.onclose = () => {
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
      // Only transition to idle if we weren't already in a terminal state
      if (statusRef.current !== 'completed' && statusRef.current !== 'error') {
        setStatus('idle');
      }
      console.log(`Disconnected from run: ${runId}`);
    };

    socket.onerror = (err) => {
      setStatus('error');
      setError('WebSocket error occurred');
      console.error(err);
    };

    return () => {
      socket.close();
    };
  }, [runId, reloadKey, enabled]); // reconnect when caller explicitly bumps reloadKey

  useEffect(() => {
    if (enabled && runId) {
      const cleanup = connect();
      return cleanup;
    }
  }, [runId, reloadKey, enabled, connect]);

  const clearEvents = () => setEvents([]);
  const replaceEvents = (nextEvents: AgentEvent[]) => setEvents(nextEvents);
  const setTerminalStatus = (nextStatus: 'idle' | 'connecting' | 'streaming' | 'completed' | 'error', nextError: string | null = null) => {
    setStatus(nextStatus);
    setError(nextError);
  };

  return { events, status, error, clearEvents, replaceEvents, setTerminalStatus };
};
