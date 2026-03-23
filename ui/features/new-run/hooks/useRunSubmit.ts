'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createRun } from '@/lib/api-client'
import type { NewRunFormState } from '../types'

export function useRunSubmit() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (form: NewRunFormState) => {
    setLoading(true)
    setError(null)
    try {
      const run = await createRun(form)
      router.push(`/runs/${run.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start run')
    } finally {
      setLoading(false)
    }
  }

  return { submit, loading, error }
}
