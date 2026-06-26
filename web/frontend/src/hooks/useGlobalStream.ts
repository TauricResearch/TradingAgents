import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ResilientWs, buildGlobalUrl } from "../lib/ws";
import { EventType, type WsEvent } from "../lib/events";

interface PriceData {
  price: number;
  change_pct: number | null;
  sparkline: number[];
  stale: boolean;
}

/**
 * Connects to the global event stream and dispatches price updates
 * into the React Query cache so all price-dependent components
 * (TickerHeader, TickerRow, etc.) re-render in real-time.
 */
export function useGlobalStream() {
  const qc = useQueryClient();
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    if (clientRef.current) return;
    const client = new ResilientWs({
      url: buildGlobalUrl,
      onMessage: (evt: WsEvent) => {
        if (evt.type === EventType.PRICE_UPDATE) {
          const { ticker, price, change_pct, sparkline, stale } = evt.data as Record<
            string,
            unknown
          >;
          if (typeof ticker !== "string") return;

          const priceData: PriceData = {
            price: Number(price) || 0,
            change_pct: change_pct != null ? Number(change_pct) : null,
            sparkline: Array.isArray(sparkline)
              ? sparkline.map(Number)
              : [],
            stale: Boolean(stale),
          };

          // Merge into the existing ["prices"] cache so REST polling
          // and WS updates coexist — WS just fills the gap between polls.
          qc.setQueryData(["prices"], (old: Record<string, PriceData> | undefined) => ({
            ...(old || {}),
            [ticker]: priceData,
          }));
        } else if (evt.type === EventType.RUN_FINISHED || evt.type === EventType.RUN_FAILED) {
          const { ticker } = evt.data as Record<string, unknown>;
          if (typeof ticker === "string" && ticker) {
            qc.invalidateQueries({ queryKey: ["ticker-runs", ticker] });
            qc.invalidateQueries({ queryKey: ["runs", "list"] });
          }
        }
      },
    });

    clientRef.current = client;
    client.start();

    return () => {
      client.stop();
      clientRef.current = null;
    };
  }, [qc]);
}
