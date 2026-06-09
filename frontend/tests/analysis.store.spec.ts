import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAnalysisStore } from '../src/stores/analysis'

describe('analysis store SSE handling', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('maps chunk events to report fields', () => {
    const s = useAnalysisStore()
    ;(s as any).reset()
    ;(s as any) // access internal handle via subscribe path not available; replicate:
    // Drive the public reset + simulate by calling start path is network-bound,
    // so we exercise the chunk mapping through loadFullState which uses applyChunk.
    s.loadFullState({ market_report: 'hello market', final_trade_decision: 'BUY now' })
    expect(s.reports.market_report).toBe('hello market')
    expect(s.decisionLabel).toBe('BUY')
  })

  it('derives SELL/HOLD/— from decision text', () => {
    const s = useAnalysisStore()
    s.loadFullState({ final_trade_decision: 'We should SELL' })
    expect(s.decisionLabel).toBe('SELL')
    s.loadFullState({ final_trade_decision: 'maybe later' })
    expect(s.decisionLabel).toBe('—')
  })
})
