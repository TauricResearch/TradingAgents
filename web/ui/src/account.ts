import { createContext, useContext } from 'react'
import type { Account, Overview } from './api'
import type { FetchState } from './hooks'

export interface AccountScope {
  account: Account
  overview: FetchState<Overview>
}

export const AccountContext = createContext<AccountScope | null>(null)

/** The selected account and its 60-second overview feed, shared by the shell and pages. */
export function useAccount(): AccountScope {
  const scope = useContext(AccountContext)
  if (!scope) throw new Error('useAccount outside of AccountContext')
  return scope
}
