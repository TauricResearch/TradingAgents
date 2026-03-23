'use client'
import { useState } from 'react'
import AnalystSelector from './AnalystSelector'
import { useRunSubmit } from '../hooks/useRunSubmit'
import { DEFAULT_FORM } from '../types'
import type { NewRunFormState } from '../types'

function SectionCard({
  step,
  title,
  subtitle,
  children,
}: {
  step: number
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section
      className="overflow-hidden"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '14px',
      }}
    >
      {/* Section header */}
      <div
        className="px-5 py-3.5 flex items-center gap-3"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-elevated)' }}
      >
        <div
          className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
          style={{
            background: 'var(--accent-dim)',
            color: 'var(--accent-light)',
            border: '1px solid rgba(0,196,232,0.30)',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '-0.01em',
          }}
        >
          {String(step).padStart(2, '0')}
        </div>
        <div className="flex-1 min-w-0">
          <div
            className="text-sm font-semibold"
            style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
          >
            {title}
          </div>
          {subtitle && (
            <div
              className="text-[10px] mt-0.5"
              style={{ color: 'var(--text-low)', fontFamily: 'var(--font-mono)', letterSpacing: '0.03em' }}
            >
              {subtitle}
            </div>
          )}
        </div>
      </div>

      {/* Section body */}
      <div className="p-5">{children}</div>
    </section>
  )
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label
      className="block mb-1.5 text-[10px] font-bold uppercase tracking-widest"
      style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em' }}
    >
      {children}
    </label>
  )
}

export default function RunConfigForm() {
  const [form, setForm] = useState<NewRunFormState>(DEFAULT_FORM)
  const { submit, loading, error } = useRunSubmit()
  const set = (k: keyof NewRunFormState, v: unknown) =>
    setForm((f) => ({ ...f, [k]: v }))

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); submit(form) }}
      className="space-y-3"
    >
      {/* Error */}
      {error && (
        <div
          className="px-4 py-3 rounded-xl text-sm flex items-center gap-2.5"
          style={{
            background: 'var(--error-bg)',
            color: 'var(--error)',
            border: '1px solid rgba(255,43,62,0.25)',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.4"/>
            <path d="M7 4v4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
            <circle cx="7" cy="10" r="0.8" fill="currentColor"/>
          </svg>
          {error}
        </div>
      )}

      {/* ── Section 1: Target ─────────────────────────────────────── */}
      <SectionCard
        step={1}
        title="Analysis Target"
        subtitle="Select the security and trade date"
      >
        <div className="grid grid-cols-2 gap-4">
          <div>
            <FieldLabel>Ticker Symbol</FieldLabel>
            <input
              className="vault-input terminal-text font-bold text-sm tracking-widest"
              placeholder="e.g. NVDA"
              value={form.ticker}
              onChange={(e) => set('ticker', e.target.value.toUpperCase())}
              required
              style={{ letterSpacing: '0.12em' }}
            />
          </div>
          <div>
            <FieldLabel>Trade Date</FieldLabel>
            <input
              id="trade-date"
              type="date"
              className="vault-input terminal-text text-sm"
              value={form.date}
              onChange={(e) => set('date', e.target.value)}
              required
            />
          </div>
        </div>
      </SectionCard>

      {/* ── Section 2: Model ──────────────────────────────────────── */}
      <SectionCard
        step={2}
        title="Model Configuration"
        subtitle="LLM provider and reasoning models"
      >
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <FieldLabel>LLM Provider</FieldLabel>
            <select
              className="vault-input"
              value={form.llm_provider}
              onChange={(e) => set('llm_provider', e.target.value)}
            >
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="google">Google</option>
            </select>
          </div>

          <div>
            <FieldLabel>Deep Think LLM</FieldLabel>
            <input
              className="vault-input terminal-text text-[12px]"
              value={form.deep_think_llm}
              onChange={(e) => set('deep_think_llm', e.target.value)}
            />
          </div>
          <div>
            <FieldLabel>Quick Think LLM</FieldLabel>
            <input
              className="vault-input terminal-text text-[12px]"
              value={form.quick_think_llm}
              onChange={(e) => set('quick_think_llm', e.target.value)}
            />
          </div>

          <div>
            <FieldLabel>Debate Rounds</FieldLabel>
            <input
              type="number"
              min={1}
              max={5}
              className="vault-input terminal-text"
              value={form.max_debate_rounds}
              onChange={(e) => set('max_debate_rounds', Number(e.target.value))}
            />
          </div>
          <div>
            <FieldLabel>Risk Discussion Rounds</FieldLabel>
            <input
              type="number"
              min={1}
              max={5}
              className="vault-input terminal-text"
              value={form.max_risk_discuss_rounds}
              onChange={(e) => set('max_risk_discuss_rounds', Number(e.target.value))}
            />
          </div>
        </div>
      </SectionCard>

      {/* ── Section 3: Analysts ───────────────────────────────────── */}
      <SectionCard
        step={3}
        title="Active Analysts"
        subtitle="Select AI analysts for this run"
      >
        <AnalystSelector
          selected={form.enabled_analysts}
          onChange={(v) => set('enabled_analysts', v)}
        />
      </SectionCard>

      {/* ── Submit ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-1 px-1">
        <div
          className="flex items-center gap-2 text-[10px]"
          style={{ color: 'var(--text-low)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em' }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1.2"/>
            <path d="M5 3v2.5l1.5 1.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
          </svg>
          2–5 min · varies by model
        </div>

        <button
          type="submit"
          disabled={loading}
          className="btn-primary"
          style={{ minWidth: '160px', justifyContent: 'center' }}
        >
          {loading ? (
            <>
              <svg
                width="13"
                height="13"
                viewBox="0 0 13 13"
                fill="none"
                style={{ animation: 'spin-slow 0.7s linear infinite' }}
              >
                <circle cx="6.5" cy="6.5" r="5" stroke="rgba(0,0,0,0.25)" strokeWidth="1.5"/>
                <path d="M6.5 1.5a5 5 0 0 1 5 5" stroke="var(--bg-base)" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              Starting…
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <polygon points="3,2 10,6 3,10" fill="var(--bg-base)"/>
              </svg>
              Run Analysis
            </>
          )}
        </button>
      </div>
    </form>
  )
}
