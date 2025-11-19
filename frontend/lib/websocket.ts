import ReconnectingWebSocket from "reconnecting-websocket";
import { StreamUpdate } from "./types";

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function createWebSocket(
  analysisId: string,
  onMessage: (update: StreamUpdate) => void,
  onError?: (error: Event) => void,
  onOpen?: () => void,
  onClose?: () => void
): ReconnectingWebSocket {
  const ws = new ReconnectingWebSocket(
    `${WS_BASE_URL}/api/analysis/${analysisId}/stream`,
    [],
    {
      connectionTimeout: 4000,
      maxRetries: 10,
      maxReconnectionDelay: 10000,
      minReconnectionDelay: 1000,
    }
  );

  ws.addEventListener("message", (event) => {
    try {
      const update: StreamUpdate = JSON.parse(event.data);
      onMessage(update);
    } catch (error) {
      console.error("Failed to parse WebSocket message:", error);
    }
  });

  if (onError) {
    ws.addEventListener("error", onError);
  }

  if (onOpen) {
    ws.addEventListener("open", onOpen);
  }

  if (onClose) {
    ws.addEventListener("close", onClose);
  }

  return ws;
}

