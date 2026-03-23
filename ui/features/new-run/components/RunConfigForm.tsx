'use client'
import { useState } from 'react'
import AnalystSelector from './AnalystSelector'
import { useRunSubmit } from '../hooks/useRunSubmit'
import { DEFAULT_FORM } from '../types'
import type { NewRunFormState } from '../types'

function SectionHeader({ step, title, subtitle }: { step: number; title: string; subtitle?: string }) {
  return (
    <div className="flex items-start gap-3.5 mb-5">
      <div
        className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 mt-0.5"
        style={{
          background:  'var(--accent-dim, #1A3A88)',
          color:       'var(--accent-light)',
          border:      '1px solid var(--accent)',
          fontFamily:  'var(--font-manrope)',
        }}
      >
        {step}
      </div>
      <div>
        <div
          className="text-sm font-semibold"
          style={{ color: 'var(--text-high)', fontFamily: 'var(--font-manrope)' }}
        >
          {title}
        </div>
        {subtitle && (
          <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-low)' }}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
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
      {/* Error banner */}
      {error && (
        <div
          className="px-4 py-3 rounded-lg text-sm"
          style={{
            background: 'var(--error-bg)',
            color:      'var(--error)',
            border:     '1px solid rgba(255,68,68,0.25)',
          }}
        >
          {error}
        </div>
      )}

      {/* ── Section 1: Target ──────────────────────────────────────── */}
      <section
        className="p-5"
        style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '10px',
        }}
      >
        <SectionHeader
          step={1}
          title="Analysis Target"
          subtitle="Choose the security and date for the analysis"
        />
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Ticker Symbol
            </label>
            <input
              className="vault-input font-mono text-sm font-semibold tracking-wider"
              placeholder="e.g. NVDA"
              value={form.ticker}
              onChange={(e) => set('ticker', e.target.value.toUpperCase())}
              required
            />
          </div>
          <div>
            <label
              htmlFor="trade-date"
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Trade Date
            </label>
            <input
              id="trade-date"
              type="date"
              className="vault-input"
              value={form.date}
              onChange={(e) => set('date', e.target.value)}
              required
            />
          </div>
        </div>
      </section>

      {/* ── Section 2: Model ───────────────────────────────────────── */}
      <section
        className="p-5"
        style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '10px',
        }}
      >
        <SectionHeader
          step={2}
          title="Model Configuration"
          subtitle="Select your LLM provider and reasoning models"
        />
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 sm:col-span-1">
            <label
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              LLM Provider
            </label>
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
          <div />
          <div>
            <label
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Deep Think LLM
            </label>
            <input
              className="vault-input text-[13px]"
              value={form.deep_think_llm}
              onChange={(e) => set('deep_think_llm', e.target.value)}
            />
          </div>
          <div>
            <label
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Quick Think LLM
            </label>
            <input
              className="vault-input text-[13px]"
              value={form.quick_think_llm}
              onChange={(e) => set('quick_think_llm', e.target.value)}
            />
          </div>
          <div>
            <label
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Debate Rounds
            </label>
            <input
              type="number"
              min={1}
              max={5}
              className="vault-input"
              value={form.max_debate_rounds}
              onChange={(e) => set('max_debate_rounds', Number(e.target.value))}
            />
          </div>
          <div>
            <label
              className="block text-[11px] font-medium mb-1.5"
              style={{ color: 'var(--text-mid)', fontFamily: 'var(--font-manrope)' }}
            >
              Risk Discussion Rounds
            </label>
            <input
              type="number"
              min={1}
              max={5}
              className="vault-input"
              value={form.max_risk_discuss_rounds}
              onChange={(e) => set('max_risk_discuss_rounds', Number(e.target.value))}
            />
          </div>
        </div>
      </section>

      {/* ── Section 3: Analysts ────────────────────────────────────── */}
      <section
        className="p-5"
        style={{
          background:   'var(--bg-card)',
          border:       '1px solid var(--border)',
          borderRadius: '10px',
        }}
      >
        <SectionHeader
          step={3}
          title="Active Analysts"
          subtitle="Select which AI analysts participate in this run"
        />
        <AnalystSelector
          selected={form.enabled_analysts}
          onChange={(v) => set('enabled_analysts', v)}
        />
      </section>

      {/* ── Submit ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-1">
        <p
          className="text-[11px]"
          style={{ color: 'var(--text-low)' }}
        >
          Analysis takes 2–5 minutes depending on model and configuration.
        </p>
        <button
          type="submit"
          disabled={loading}
          className="btn-primary"
          style={{ minWidth: '150px', justifyContent: 'center' }}
        >
          {loading ? (
            <>
              <svg
                width="13"
                height="13"
                viewBox="0 0 13 13"
                fill="none"
                style={{ animation: 'spin-slow 0.8s linear infinite' }}
              >
                <circle
                  cx="6.5"
                  cy="6.5"
                  r="5"
                  stroke="rgba(255,255,255,0.3)"
                  strokeWidth="1.5"
                />
                <path
                  d="M6.5 1.5a5 5 0 0 1 5 5"
                  stroke="white"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
              Starting…
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <polygon points="3,2 10,6 3,10" fill="white"/>
              </svg>
              Run Analysis
            </>
          )}
        </button>
      </div>
    </form>
  )
}
