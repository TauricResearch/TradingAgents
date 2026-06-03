import { useQuery } from "@tanstack/react-query";
import { fetchPrices } from "../lib/api";

export function usePrices() {
  // REST polling is a slow fallback — the primary live-price channel is the
  // WebSocket global stream (useGlobalStream) which pushes updates into the
  // same React Query cache every ~2s.
  return useQuery({ queryKey: ["prices"], queryFn: fetchPrices, refetchInterval: 300_000 });
}
