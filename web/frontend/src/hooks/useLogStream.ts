import { useEffect, useRef, useState } from "react";
import { ResilientWs, buildLogsUrl } from "../lib/ws";
import { useLogStore } from "../store/logs";
import type { LogEntry } from "../store/logs";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export function useLogStream() {
  const append = useLogStore((s) => s.append);
  const [status, setStatus] = useState<WsStatus>("idle");
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    const client = new ResilientWs({
      url: buildLogsUrl,
      onMessage: (evt: unknown) => {
        const e = evt as { type?: string; id?: string; ts?: string; level?: string; logger?: string; message?: string; source?: string };
        if (e.type === "connected") return;
        const entry: LogEntry = {
          id: e.id ?? crypto.randomUUID(),
          ts: e.ts ?? new Date().toISOString(),
          level: (e.level as LogEntry["level"]) ?? "INFO",
          logger: e.logger ?? "unknown",
          message: e.message ?? "",
          source: (e.source as LogEntry["source"]) ?? "server",
        };
        append(entry);
      },
      onStatus: setStatus,
    });
    clientRef.current = client;
    client.start();
    return () => {
      client.stop();
      clientRef.current = null;
    };
  }, [append]);

  return { status };
}