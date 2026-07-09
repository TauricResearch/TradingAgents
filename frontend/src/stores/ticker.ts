/** High-frequency price state lives outside React Query: per-symbol
 * selectors mean a BTC tick re-renders one price cell, never the tree. */
import { create } from "zustand";

export interface Tick {
  last: number;
  bid: number | null;
  ask: number | null;
  at: number; // Date.now() of receipt
  source: string; // feed name from the venue (delta_exchange, binance, ...)
}

interface TickerState {
  ticks: Record<string, Tick>;
  setTick: (symbol: string, tick: Tick) => void;
}

export const useTickerStore = create<TickerState>((set) => ({
  ticks: {},
  setTick: (symbol, tick) =>
    set((state) => ({ ticks: { ...state.ticks, [symbol]: tick } })),
}));

export const useTick = (symbol: string): Tick | undefined =>
  useTickerStore((state) => state.ticks[symbol]);
