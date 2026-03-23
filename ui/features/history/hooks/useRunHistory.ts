'use client'
import { useEffect, useState } from 'react'
import { listRuns } from '@/lib/api-client'
import type { RunSummary } from '@/lib/types/run'

export function useRunHistory() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRuns()
      .then(setRuns)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return { runs, loading, error }
}
