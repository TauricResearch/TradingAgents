import { createContext, useContext } from 'react'
import type { Account, Overview } from './api'
import type { FetchState } from './hooks'

export interface AccountScope {
  account: Account
  /** Every account the backend lists, for the top bar's switch. */
  accounts: Account[]
  /** Switch to the account with this id; the choice is remembered by this browser. */
  select: (id: string) => void
  overview: FetchState<Overview>
}

export const AccountContext = createContext<AccountScope | null>(null)

/** The selected account and its 60-second overview feed, shared by the shell and pages. */
export function useAccount(): AccountScope {
  const scope = useContext(AccountContext)
  if (!scope) throw new Error('useAccount outside of AccountContext')
  return scope
}
