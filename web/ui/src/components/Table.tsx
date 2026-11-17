import type { FetchState } from '../hooks'
import { DataTable, type Column } from './DataTable'
import { ErrorBox, Loading } from './Status'

/** A DataTable over a fetched list: loading first, the error with a retry if the first request failed. */
export function Table<T>({ state, columns, rowKey, rowClassName }: {
  state: FetchState<T[]>
  columns: Column<T>[]
  rowKey: (row: T, i: number) => string
  rowClassName?: (row: T) => string
}) {
  if (state.error && !state.data) return <ErrorBox error={state.error} onRetry={state.refresh} />
  if (!state.data) return <Loading />
  return <DataTable columns={columns} rows={state.data} rowKey={rowKey} rowClassName={rowClassName} />
}
