import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { subscribeRun } from '../api/sse'

// Maps worker chunk fields → the report tabs the UI shows.
export type Reports = {
  market_report: string
  sentiment_report: string
  news_report: string
  fundamentals_report: string
  investment_plan: string
  trader_investment_plan: string
  final_trade_decision: string
}

const EMPTY: Reports = {
  market_report: '', sentiment_report: '', news_report: '', fundamentals_report: '',
  investment_plan: '', trader_investment_plan: '', final_trade_decision: '',
}

export type StartReq = {
  ticker: string; trade_date: string; provider: string; deep_model: string
  quick_model: string; selected_analysts: string[]; max_debate_rounds: number
  max_risk_discuss_rounds: number; output_language: string; checkpoint_enabled: boolean
  user_research?: string
}

export const useAnalysisStore = defineStore('analysis', () => {
  const runId = ref<string | null>(null)
  const status = ref<'idle' | 'pending' | 'running' | 'done' | 'error'>('idle')
  const reports = ref<Reports>({ ...EMPTY })
  const decision = ref<string | null>(null)
  const stats = ref<Record<string, any> | null>(null)
  const log = ref<string[]>([])
  const errorMsg = ref<string | null>(null)
  let unsub: (() => void) | null = null

  const decisionLabel = computed(() => {
    const t = (decision.value || reports.value.final_trade_decision || '').toUpperCase()
    for (const w of ['BUY', 'SELL', 'HOLD']) if (new RegExp(`\\b${w}\\b`).test(t)) return w
    return '—'
  })

  function applyChunk(data: Partial<Reports> & Record<string, any>) {
    for (const k of Object.keys(EMPTY) as (keyof Reports)[]) {
      if (data[k]) reports.value[k] = data[k] as string
    }
  }

  function handle(kind: string, data: any) {
    if (kind === 'started') {
      status.value = 'running'
      log.value.push('Pipeline started')
    } else if (kind === 'chunk') {
      applyChunk(data.data ?? data)
      log.value.push('update received')
    } else if (kind === 'stats') {
      stats.value = data.data ?? data
    } else if (kind === 'done') {
      decision.value = data.decision ?? null
      status.value = 'done'
      log.value.push('Pipeline complete')
    } else if (kind === 'error') {
      errorMsg.value = data.msg || 'error'
      status.value = 'error'
      log.value.push('Error: ' + errorMsg.value)
    }
  }

  function reset() {
    if (unsub) unsub()
    unsub = null
    reports.value = { ...EMPTY }
    decision.value = null
    stats.value = null
    log.value = []
    errorMsg.value = null
    status.value = 'idle'
  }

  function subscribe(id: string) {
    runId.value = id
    if (unsub) unsub()
    unsub = subscribeRun(id, { onEvent: handle })
  }

  async function start(req: StartReq) {
    reset()
    status.value = 'pending'
    const r = await api.post<{ run_id: string; resumed: boolean }>('/api/analysis/start', req)
    subscribe(r.run_id)
    return r.run_id
  }

  async function cancel() {
    if (runId.value) await api.post(`/api/analysis/${runId.value}/cancel`)
  }

  // Load a finished past run's full state into the same report shape.
  function loadFullState(fs: Record<string, any>) {
    reset()
    applyChunk(fs)
    if (fs.investment_debate_state || fs.risk_debate_state) {
      // keep raw for the debate views if present
    }
    decision.value = fs.final_trade_decision ?? null
    status.value = 'done'
  }

  return {
    runId, status, reports, decision, stats, log, errorMsg, decisionLabel,
    start, subscribe, cancel, reset, loadFullState,
  }
})
