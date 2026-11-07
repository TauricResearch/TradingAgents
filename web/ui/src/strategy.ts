import { createContext, useContext } from 'react'

export type Vars = Record<string, string>

/** Placeholder values for the guide and help copy; empty until /api/strategy has loaded. */
export const StrategyContext = createContext<Vars>({})

export function useVars(): Vars {
  return useContext(StrategyContext)
}
