import { createContext, useContext } from 'react'
import type { Account, Execution, Overview } from './api'
import type { FetchState } from './hooks'

export interface AccountScope {
  account: Account
  /** Every account the backend lists, for the top bar's switch. */
  accounts: Account[]
  /** Switch to the account with this id; the choice is remembered by this browser. */
  select: (id: string) => void
  overview: FetchState<Overview>
  /** An exchange account's last reconciliation, polled with the overview; never fetched for the other accounts. */
  execution: FetchState<Execution>
}

export const AccountContext = createContext<AccountScope | null>(null)

/** The selected account and its 60-second overview and execution feeds, shared by the shell and pages. */
export function useAccount(): AccountScope {
  const scope = useContext(AccountContext)
  if (!scope) throw new Error('useAccount outside of AccountContext')
  return scope
}
