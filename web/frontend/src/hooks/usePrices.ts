import { useQuery } from "@tanstack/react-query";
import { fetchPrices } from "../lib/api";

export function usePrices() {
  return useQuery({ queryKey: ["prices"], queryFn: fetchPrices, refetchInterval: 20_000 });
}
