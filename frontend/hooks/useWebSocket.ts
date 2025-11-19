import { useEffect, useRef, useState, useCallback } from "react";
import { createWebSocket } from "@/lib/websocket";
import { StreamUpdate } from "@/lib/types";

export function useWebSocket(
  analysisId: string | null,
  onMessage?: (update: StreamUpdate) => void
) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Event | null>(null);
  const wsRef = useRef<ReturnType<typeof createWebSocket> | null>(null);
  const onMessageRef = useRef(onMessage);

  // Keep the ref updated with the latest callback
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!analysisId) {
      return;
    }

    const ws = createWebSocket(
      analysisId,
      (update) => {
        // Use ref to avoid dependency issues
        onMessageRef.current?.(update);
      },
      (err) => {
        setError(err);
        setIsConnected(false);
      },
      () => {
        setIsConnected(true);
        setError(null);
      },
      () => {
        setIsConnected(false);
      }
    );

    wsRef.current = ws;

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
    };
  }, [analysisId]); // Only depend on analysisId, not onMessage

  const send = useCallback((message: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
    }
  }, []);

  return { isConnected, error, send };
}

