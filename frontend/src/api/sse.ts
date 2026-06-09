// EventSource wrapper for the analysis stream. Returns a close() handle.

export type SseHandlers = {
  onEvent: (kind: string, data: any) => void
  onError?: (e: Event) => void
}

export function subscribeRun(runId: string, h: SseHandlers): () => void {
  const es = new EventSource(`/api/analysis/${encodeURIComponent(runId)}/stream`, {
    withCredentials: true,
  })
  for (const kind of ['started', 'chunk', 'stats', 'done', 'error']) {
    es.addEventListener(kind, (ev: MessageEvent) => {
      let data: any = {}
      try {
        data = JSON.parse(ev.data)
      } catch {
        /* heartbeat / malformed */
      }
      h.onEvent(kind, data)
      if (kind === 'done' || kind === 'error') es.close()
    })
  }
  es.onerror = (e) => h.onError?.(e)
  return () => es.close()
}
