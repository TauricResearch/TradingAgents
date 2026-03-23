export type SSEHandlers = {
  onAgentStart?: (data: { step: string; turn: number }) => void
  onAgentComplete?: (data: { step: string; turn: number; report: string }) => void
  onRunComplete?: (data: { decision: string; run_id: string }) => void
  onRunError?: (data: { message: string }) => void
  onOpen?: () => void
}

export function createSSEConnection(url: string, handlers: SSEHandlers): () => void {
  const source = new EventSource(url)

  source.onopen = () => handlers.onOpen?.()

  source.onerror = () => {
    handlers.onRunError?.({ message: 'SSE connection error' })
    source.close()
  }

  source.addEventListener('agent:start', (e: MessageEvent) => {
    try { handlers.onAgentStart?.(JSON.parse(e.data)) }
    catch { handlers.onRunError?.({ message: 'Failed to parse event data' }) }
  })

  source.addEventListener('agent:complete', (e: MessageEvent) => {
    try { handlers.onAgentComplete?.(JSON.parse(e.data)) }
    catch { handlers.onRunError?.({ message: 'Failed to parse event data' }) }
  })

  source.addEventListener('run:complete', (e: MessageEvent) => {
    try { handlers.onRunComplete?.(JSON.parse(e.data)) }
    catch { handlers.onRunError?.({ message: 'Failed to parse event data' }) }
    source.close()
  })

  source.addEventListener('run:error', (e: MessageEvent) => {
    try { handlers.onRunError?.(JSON.parse(e.data)) }
    catch { handlers.onRunError?.({ message: 'Failed to parse event data' }) }
    source.close()
  })

  return () => source.close()
}
