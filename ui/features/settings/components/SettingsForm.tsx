'use client'
import { useEffect, useState } from 'react'
import { getSettings, updateSettings } from '@/lib/api-client'
import type { SettingsFormState } from '../types'

const DEFAULTS: SettingsFormState = {
  deep_think_llm:         'gpt-5.2',
  quick_think_llm:        'gpt-5-mini',
  max_debate_rounds:      1,
  max_risk_discuss_rounds: 1,
}

export default function SettingsForm() {
  const [form, setForm]   = useState<SettingsFormState>(DEFAULTS)
  const [saved, setSaved] = useState(false)
  const set = (k: keyof SettingsFormState, v: unknown) =>
    setForm((f) => ({ ...f, [k]: v }))

  useEffect(() => { getSettings().then(setForm).catch(() => {}) }, [])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    await updateSettings(form)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <form onSubmit={save} className="max-w-lg space-y-4">

      {/* ── Model Configuration ─────────────────────────────────── */}
      <section className="rounded-lg p-6 space-y-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2
          className="apex-label"
          style={{ fontFamily: 'var(--font-manrope)' }}
        >
          Model Configuration
        </h2>
        {(['deep_think_llm', 'quick_think_llm'] as const).map((key) => (
          <div key={key}>
            <label className="block text-xs mb-2 capitalize" style={{ color: 'var(--text-mid)' }}>
              {key.replace(/_/g, ' ')}
            </label>
            <input
              className="vault-input"
              value={form[key]}
              onChange={(e) => set(key, e.target.value)}
            />
          </div>
        ))}
      </section>

      {/* ── Analysis Parameters ─────────────────────────────────── */}
      <section className="rounded-lg p-6 space-y-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <h2
          className="apex-label"
          style={{ fontFamily: 'var(--font-manrope)' }}
        >
          Analysis Parameters
        </h2>
        {(['max_debate_rounds', 'max_risk_discuss_rounds'] as const).map((key) => (
          <div key={key}>
            <label className="block text-xs mb-2 capitalize" style={{ color: 'var(--text-mid)' }}>
              {key.replace(/_/g, ' ')}
            </label>
            <input
              type="number" min={1} max={5}
              className="vault-input"
              value={form[key]}
              onChange={(e) => set(key, Number(e.target.value))}
            />
          </div>
        ))}
      </section>

      {/* ── Security notice ─────────────────────────────────────── */}
      <div className="rounded-lg px-5 py-3.5 text-xs leading-relaxed" style={{ background: 'var(--bg-elevated)', color: 'var(--text-mid)', border: '1px solid var(--border)' }}>
        API keys and secrets are configured via <code style={{ color: 'var(--accent-light)' }} className="font-mono">.env</code> on the server and are not editable here.
      </div>

      {/* ── Actions ─────────────────────────────────────────────── */}
      <div className="flex gap-3 justify-end pt-1">
        <button
          type="button"
          onClick={() => setForm(DEFAULTS)}
          className="btn-secondary px-4 py-2.5 text-sm"
        >
          Reset to Defaults
        </button>
        <button
          type="submit"
          className="btn-primary px-5 py-2.5 text-sm"
        >
          {saved ? '✓ Saved' : 'Save Changes'}
        </button>
      </div>
    </form>
  )
}
