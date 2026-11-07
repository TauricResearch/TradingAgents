import { useCallback, useEffect, useState } from 'react'
import { getJson } from './api'

export interface FetchState<T> {
  /** Last successful payload for the current path; null until the first success. */
  data: T | null
  /** Error of the latest request; kept alongside stale data on refresh failures. */
  error: Error | null
  /** True while the first request for the current path is in flight. */
  loading: boolean
  updatedAt: number | null
  refresh: () => void
}

interface Snapshot<T> {
  path: string | null
  data: T | null
  error: Error | null
  updatedAt: number | null
}

const toError = (e: unknown): Error => (e instanceof Error ? e : new Error(String(e)))

/**
 * Fetch JSON from `path`, re-fetching every `refreshMs` when > 0.
 * Pass `null` as the path to wait (e.g. until the account id is known).
 */
export function useFetch<T>(path: string | null, refreshMs = 0): FetchState<T> {
  const [snap, setSnap] = useState<Snapshot<T>>({
    path: null,
    data: null,
    error: null,
    updatedAt: null,
  })
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (path === null) return
    const controller = new AbortController()
    getJson<T>(path, controller.signal).then(
      (data) => setSnap({ path, data, error: null, updatedAt: Date.now() }),
      (e: unknown) => {
        if (controller.signal.aborted) return
        setSnap((prev) => {
          const same = prev.path === path
          return {
            path,
            data: same ? prev.data : null,
            error: toError(e),
            updatedAt: same ? prev.updatedAt : null,
          }
        })
      },
    )
    return () => controller.abort()
  }, [path, tick])

  useEffect(() => {
    if (refreshMs <= 0 || path === null) return
    const id = window.setInterval(() => setTick((t) => t + 1), refreshMs)
    return () => window.clearInterval(id)
  }, [refreshMs, path])

  const refresh = useCallback(() => setTick((t) => t + 1), [])

  const current = snap.path === path
  return {
    data: current ? snap.data : null,
    error: current ? snap.error : null,
    loading: path !== null && (!current || (snap.data === null && snap.error === null)),
    updatedAt: current ? snap.updatedAt : null,
    refresh,
  }
}
