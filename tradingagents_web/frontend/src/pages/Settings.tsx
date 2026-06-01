import { useEffect, useState } from 'react'
import axios from 'axios'
import { Save } from 'lucide-react'

interface Settings {
  trading_mode: string
  active_broker: string
  active_data_vendor: string
  cron_enabled: boolean
  cron_schedule: string
  price_tolerance_pct: number
  llm_provider: string
  deep_think_llm: string
  quick_think_llm: string
  max_debate_rounds: number
  max_risk_rounds: number
  max_position_size_pct: number
  max_risk_per_trade_pct: number
  watchlist: string[]
  selected_analysts: string[]
}

const ANALYSTS = ['market', 'news', 'fundamentals', 'social', 'macro', 'options', 'quant', 'earnings', 'review']
const ANALYST_LABELS: Record<string, string> = {
  market: 'Piyasa', news: 'Haber', fundamentals: 'Temel', social: 'Duygu',
  macro: 'Makro', options: 'Opsiyon', quant: 'Kantitatif', earnings: 'Kazanç', review: 'İnceleme',
}

export default function Settings() {
  const [s, setS] = useState<Settings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => { axios.get('/api/settings').then(r => setS(r.data)) }, [])

  const save = async () => {
    await axios.put('/api/settings', s)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  if (!s) return <div className="p-8 text-slate-400">Yükleniyor...</div>

  const update = (k: keyof Settings, v: any) => setS(prev => prev ? { ...prev, [k]: v } : prev)

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <h2 className="text-2xl font-bold text-white">Ayarlar</h2>

      <Section title="Çalışma Modu">
        <Row label="Mod">
          <select className={Input} value={s.trading_mode} onChange={e => update('trading_mode', e.target.value)}>
            <option value="simulation">Simülasyon (Paper Trading)</option>
            <option value="live">Canlı (Live)</option>
          </select>
        </Row>
        <Row label="Aktif Broker">
          <select className={Input} value={s.active_broker} onChange={e => update('active_broker', e.target.value)}>
            <option value="simulation">Simülasyon</option>
          </select>
        </Row>
        <Row label="Veri Kaynağı">
          <select className={Input} value={s.active_data_vendor} onChange={e => update('active_data_vendor', e.target.value)}>
            <option value="yfinance">yFinance</option>
            <option value="alpha_vantage">Alpha Vantage</option>
          </select>
        </Row>
      </Section>

      <Section title="Cron / Otomatik Tarama">
        <Row label="Aktif">
          <input type="checkbox" checked={s.cron_enabled} onChange={e => update('cron_enabled', e.target.checked)} className="w-5 h-5 accent-indigo-600" />
        </Row>
        <Row label="Zamanlama (Cron)">
          <input className={Input} value={s.cron_schedule} onChange={e => update('cron_schedule', e.target.value)} placeholder="0 9 * * 1-5" />
        </Row>
        <Row label="Fiyat Toleransı (%)">
          <input type="number" step="0.1" min="0" max="50" className={Input} value={s.price_tolerance_pct} onChange={e => update('price_tolerance_pct', parseFloat(e.target.value))} />
        </Row>
      </Section>

      <Section title="LLM Ayarları">
        <Row label="Provider">
          <select className={Input} value={s.llm_provider} onChange={e => update('llm_provider', e.target.value)}>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="google">Google</option>
          </select>
        </Row>
        <Row label="Derin Düşünce Modeli">
          <input className={Input} value={s.deep_think_llm} onChange={e => update('deep_think_llm', e.target.value)} />
        </Row>
        <Row label="Hızlı Düşünce Modeli">
          <input className={Input} value={s.quick_think_llm} onChange={e => update('quick_think_llm', e.target.value)} />
        </Row>
        <Row label="Tartışma Turları">
          <input type="number" min="1" max="10" className={Input} value={s.max_debate_rounds} onChange={e => update('max_debate_rounds', parseInt(e.target.value))} />
        </Row>
        <Row label="Risk Turları">
          <input type="number" min="1" max="10" className={Input} value={s.max_risk_rounds} onChange={e => update('max_risk_rounds', parseInt(e.target.value))} />
        </Row>
      </Section>

      <Section title="Risk Yönetimi">
        <Row label="Maks. Pozisyon Büyüklüğü (%)">
          <input type="number" step="1" min="1" max="100" className={Input} value={s.max_position_size_pct} onChange={e => update('max_position_size_pct', parseFloat(e.target.value))} />
        </Row>
        <Row label="Trade Başına Risk (%)">
          <input type="number" step="0.1" min="0.1" max="50" className={Input} value={s.max_risk_per_trade_pct} onChange={e => update('max_risk_per_trade_pct', parseFloat(e.target.value))} />
        </Row>
      </Section>

      <Section title="Aktif Analistler">
        <div className="grid grid-cols-3 gap-2 pt-1">
          {ANALYSTS.map(a => (
            <label key={a} className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                className="accent-indigo-600"
                checked={s.selected_analysts.includes(a)}
                onChange={e => {
                  const next = e.target.checked
                    ? [...s.selected_analysts, a]
                    : s.selected_analysts.filter(x => x !== a)
                  update('selected_analysts', next)
                }}
              />
              <span className="text-slate-300">{ANALYST_LABELS[a]}</span>
            </label>
          ))}
        </div>
      </Section>

      <button onClick={save} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg px-5 py-2 font-semibold">
        <Save size={16} /> {saved ? 'Kaydedildi ✓' : 'Kaydet'}
      </button>
    </div>
  )
}

const Input = "bg-slate-700 text-white rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500 outline-none text-sm w-full"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-800 rounded-xl p-5 space-y-3">
      <h3 className="text-base font-semibold text-indigo-300 mb-3">{title}</h3>
      {children}
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm text-slate-400 whitespace-nowrap">{label}</span>
      <div className="flex-1 max-w-xs">{children}</div>
    </div>
  )
}
