import { useState, useEffect, useCallback } from 'react';

export interface AgentEvent {
  id: string;
  timestamp: string;
  agent: string;
  tier: 'quick' | 'mid' | 'deep';
  type: 'thought' | 'tool' | 'result' | 'system';
  message: string;
  details?: {
    model_used: string;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    raw_json_response: string;
  };
}

export const useAgentStream = (runId: string | null) => {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [status, setStatus] = useState<'idle' | 'connecting' | 'streaming' | 'completed' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(() => {
    if (!runId) return;

    setStatus('connecting');
    setError(null);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host; // Change this to your backend host if different
    const socket = new WebSocket(`${protocol}//${host}/ws/stream/${runId}`);

    socket.onopen = () => {
      setStatus('streaming');
      console.log(`Connected to run: ${runId}`);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'system' && data.message === 'Run completed.') {
        setStatus('completed');
      } else if (data.type === 'system' && data.message.startsWith('Error:')) {
        setStatus('error');
        setError(data.message);
      } else {
        setEvents((prev) => [...prev, data as AgentEvent]);
      }
    };

    socket.onclose = () => {
      if (status !== 'completed' && status !== 'error') {
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
  }, [runId, status]);

  useEffect(() => {
    if (runId) {
      const cleanup = connect();
      return cleanup;
    }
  }, [runId, connect]);

  const clearEvents = () => setEvents([]);

  return { events, status, error, clearEvents };
};
