import type { RunConfig, RunSummary } from './types/run'
import type { Settings } from './types/settings'

const API = process.env.NEXT_PUBLIC_API_URL ?? ''

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = init
    ? await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...init,
      })
    : await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json() as Promise<T>
}

export const createRun = (config: RunConfig): Promise<RunSummary> =>
  apiFetch('/api/runs', { method: 'POST', body: JSON.stringify(config) })

export const listRuns = (): Promise<RunSummary[]> =>
  apiFetch('/api/runs')

export const getRun = (id: string): Promise<RunSummary> =>
  apiFetch(`/api/runs/${id}`)

export const getSettings = (): Promise<Settings> =>
  apiFetch('/api/settings')

export const updateSettings = (settings: Settings): Promise<Settings> =>
  apiFetch('/api/settings', { method: 'PUT', body: JSON.stringify(settings) })

export const getRunStreamUrl = (id: string): string =>
  `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/runs/${id}/stream`
