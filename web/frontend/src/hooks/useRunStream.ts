import { useEffect, useRef, useState } from "react";
import { ResilientWs, buildRunUrl } from "../lib/ws";
import { useUi } from "../store/ui";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export function useRunStream(runId: number | null) {
  const appendEvent = useUi((s) => s.appendEvent);
  const [status, setStatus] = useState<WsStatus>("idle");
  const lastIdRef = useRef<number>(0);
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    if (runId == null) {
      setStatus("idle");
      return;
    }
    const client = new ResilientWs({
      url: () => buildRunUrl(runId, lastIdRef.current || undefined),
      onMessage: (evt) => {
        if (typeof evt.id === "number") lastIdRef.current = Math.max(lastIdRef.current, evt.id);
        appendEvent(evt);
      },
      onStatus: setStatus,
    });
    clientRef.current = client;
    client.start();
    return () => {
      client.stop();
      clientRef.current = null;
    };
  }, [runId, appendEvent]);

  return { status };
}
