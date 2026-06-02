import { useEffect, useState } from 'react'
import axios from 'axios'
import { Save, BookmarkPlus, Trash2, Play, Bell } from 'lucide-react'
import { useMeta } from '../hooks/useMeta'
import { requestBrowserNotifyPermission, setBrowserNotifyPref, isBrowserNotifyEnabled } from '../utils/browserNotify'

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
  backend_url: string | null
  openai_reasoning_effort: string | null
  anthropic_effort: string | null
  google_thinking_level: string | null
  output_language: string
  analyst_concurrency_limit: number
  checkpoint_enabled: boolean
  max_recur_limit: number
  news_article_limit: number
  global_news_article_limit: number
  global_news_lookback_days: number
  benchmark_ticker: string | null
  azure_deployment: string | null
  data_vendor_core_stock: string
  data_vendor_technicals: string
  data_vendor_fundamentals: string
  data_vendor_news: string
  max_debate_rounds: number
  max_risk_rounds: number
  max_position_size_pct: number
  max_risk_per_trade_pct: number
  include_historical_analyses: boolean
  webhook_url: string | null
  webhook_enabled: boolean
  webhook_events: string
  watchlist: string[]
  selected_analysts: string[]
}

interface Preset { id: number; name: string; description: string | null; created_at: string }

interface ModelOption { label: string; value: string }
type Catalog = Record<string, { quick: ModelOption[]; deep: ModelOption[] }>

// Fallback provider names — used only until /api/meta loads (provider_labels).
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic (Claude)',
  google: 'Google (Gemini)',
  xai: 'xAI (Grok)',
  deepseek: 'DeepSeek',
  qwen: 'Qwen (Global)',
  'qwen-cn': 'Qwen (China)',
  glm: 'GLM / Z.AI (Global)',
  'glm-cn': 'GLM / BigModel (China)',
  minimax: 'MiniMax (Global)',
  'minimax-cn': 'MiniMax (China)',
  ollama: 'Ollama (Local)',
  nvidia: 'NVIDIA NIM',
  litellm: 'LiteLLM Proxy',
  azure: 'Azure OpenAI',
}

function ModelSelect({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: ModelOption[]
  value: string
  onChange: (v: string) => void
}) {
  const isCustom = !options.some(o => o.value === value) || value === 'custom'
  const [showCustom, setShowCustom] = useState(isCustom)
  const [customVal, setCustomVal] = useState(isCustom ? value : '')

  useEffect(() => {
    const custom = !options.some(o => o.value === value) || value === 'custom'
    setShowCustom(custom)
    if (custom) setCustomVal(value === 'custom' ? '' : value)
  }, [value, options])

  const handleSelect = (v: string) => {
    if (v === 'custom') {
      setShowCustom(true)
      setCustomVal('')
    } else {
      setShowCustom(false)
      onChange(v)
    }
  }

  return (
    <Row label={label}>
      <div className="space-y-1">
        <select
          className={Input}
          value={showCustom ? 'custom' : value}
          onChange={e => handleSelect(e.target.value)}
        >
          {options.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
          {/* Ensure "Custom" option is present even if catalog already has it */}
          {!options.some(o => o.value === 'custom') && (
            <option value="custom">Özel model ID</option>
          )}
        </select>
        {showCustom && (
          <input
            className={Input}
            placeholder="Model ID girin..."
            value={customVal}
            onChange={e => {
              setCustomVal(e.target.value)
              onChange(e.target.value)
            }}
          />
        )}
      </div>
    </Row>
  )
}

export default function Settings() {
  const [s, setS] = useState<Settings | null>(null)
  const [catalog, setCatalog] = useState<Catalog>({})
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [presetName, setPresetName] = useState('')
  const [presetSaving, setPresetSaving] = useState(false)
  const [browserNotify, setBrowserNotify] = useState(isBrowserNotifyEnabled())
  const [webhookTesting, setWebhookTesting] = useState(false)
  const [webhookTestResult, setWebhookTestResult] = useState<string | null>(null)
  const meta = useMeta()

  useEffect(() => {
    Promise.all([
      axios.get('/api/settings').then(r => r.data),
      axios.get('/api/settings/llm-catalog').then(r => r.data),
      axios.get('/api/presets').then(r => r.data),
    ]).then(([settings, cat, presetList]) => {
      setS(settings)
      setCatalog(cat)
      setPresets(presetList)
    })
  }, [])

  const loadPresets = () => axios.get('/api/presets').then(r => setPresets(r.data))

  const savePreset = async () => {
    if (!presetName.trim() || !s) return
    setPresetSaving(true)
    try {
      await axios.post('/api/presets', { name: presetName.trim(), settings_json: JSON.stringify(s) })
      setPresetName('')
      await loadPresets()
    } finally { setPresetSaving(false) }
  }

  const applyPreset = async (id: number) => {
    const r = await axios.post(`/api/presets/${id}/apply`)
    setS(r.data)
  }

  const deletePreset = async (id: number) => {
    await axios.delete(`/api/presets/${id}`)
    setPresets(prev => prev.filter(p => p.id !== id))
  }

  const testWebhook = async () => {
    if (!s?.webhook_url) return
    setWebhookTesting(true); setWebhookTestResult(null)
    try {
      await axios.post('/api/settings/test-webhook', { url: s.webhook_url })
      setWebhookTestResult('✓ Başarılı')
    } catch { setWebhookTestResult('✗ Başarısız') }
    finally { setWebhookTesting(false) }
  }

  const toggleBrowserNotify = async () => {
    if (!browserNotify) {
      const granted = await requestBrowserNotifyPermission()
      setBrowserNotify(granted)
    } else {
      setBrowserNotifyPref(false)
      setBrowserNotify(false)
    }
  }

  const save = async () => {
    setSaveError(null)
    try {
      await axios.put('/api/settings', s)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || 'Kaydetme başarısız.')
    }
  }

  if (!s) return <div className="p-8 text-slate-400">Yükleniyor...</div>

  const update = (k: keyof Settings, v: any) => setS(prev => prev ? { ...prev, [k]: v } : prev)

  const providerList = Object.keys(catalog)
  const currentProviderModels = catalog[s.llm_provider]

  // Backend-driven choice lists (fall back to minimal defaults until meta loads)
  const providerLabels = meta?.provider_labels ?? PROVIDER_LABELS
  const tradingModes = meta?.trading_modes ?? [{ value: 'simulation', label: 'Simülasyon (Paper Trading)' }, { value: 'live', label: 'Canlı (Live)' }]
  const brokers = meta?.brokers ?? [{ value: 'simulation', label: 'Simülasyon' }]
  const dataVendors = meta?.data_vendors ?? [{ value: 'yfinance', label: 'yFinance' }, { value: 'alpha_vantage', label: 'Alpha Vantage' }]
  const languages = meta?.languages ?? [{ value: 'English', label: 'English' }, { value: 'Turkish', label: 'Türkçe' }]
  const analysts = meta?.analysts ?? []

  // Single setS call to avoid double render (bug fix)
  const handleProviderChange = (provider: string) => {
    const modes = catalog[provider]
    setS(prev => {
      if (!prev) return prev
      return {
        ...prev,
        llm_provider: provider,
        deep_think_llm: modes?.deep?.[0]?.value || prev.deep_think_llm,
        quick_think_llm: modes?.quick?.[0]?.value || prev.quick_think_llm,
      }
    })
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5 max-w-2xl">
      <h2 className="text-xl font-bold text-white tracking-tight">Ayarlar</h2>

      <Section title="Çalışma Modu">
        <Row label="Mod">
          <select className={Input} value={s.trading_mode} onChange={e => update('trading_mode', e.target.value)}>
            {tradingModes.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Row>
        <Row label="Aktif Broker">
          <select className={Input} value={s.active_broker} onChange={e => update('active_broker', e.target.value)}>
            {brokers.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Row>
        <Row label="Veri Kaynağı">
          <select className={Input} value={s.active_data_vendor} onChange={e => update('active_data_vendor', e.target.value)}>
            {dataVendors.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
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
          <select
            className={Input}
            value={s.llm_provider}
            onChange={e => handleProviderChange(e.target.value)}
          >
            {providerList.length > 0
              ? providerList.map(p => (
                  <option key={p} value={p}>{providerLabels[p] || p}</option>
                ))
              : (
                // Fallback if catalog not loaded
                <>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic (Claude)</option>
                  <option value="google">Google (Gemini)</option>
                  <option value="xai">xAI (Grok)</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="ollama">Ollama (Local)</option>
                </>
              )
            }
          </select>
        </Row>

        {currentProviderModels ? (
          <>
            <ModelSelect
              label="Derin Düşünce Modeli"
              options={currentProviderModels.deep || []}
              value={s.deep_think_llm}
              onChange={v => update('deep_think_llm', v)}
            />
            <ModelSelect
              label="Hızlı Düşünce Modeli"
              options={currentProviderModels.quick || []}
              value={s.quick_think_llm}
              onChange={v => update('quick_think_llm', v)}
            />
          </>
        ) : (
          // Providers like azure/openrouter not in catalog: free text
          <>
            <Row label="Derin Düşünce Modeli">
              <input className={Input} value={s.deep_think_llm} onChange={e => update('deep_think_llm', e.target.value)} placeholder="Model ID" />
            </Row>
            <Row label="Hızlı Düşünce Modeli">
              <input className={Input} value={s.quick_think_llm} onChange={e => update('quick_think_llm', e.target.value)} placeholder="Model ID" />
            </Row>
          </>
        )}

        {/* Backend URL — show for Ollama, LiteLLM, Azure, custom endpoints */}
        {['ollama', 'litellm', 'azure', 'nvidia'].includes(s.llm_provider) && (
          <Row label="API Base URL">
            <input
              className={Input}
              value={s.backend_url || ''}
              onChange={e => update('backend_url', e.target.value || null)}
              placeholder="http://localhost:11434"
            />
          </Row>
        )}

        {/* Provider-specific reasoning settings */}
        {s.llm_provider === 'openai' && (
          <Row label="Reasoning Effort">
            <select className={Input} value={s.openai_reasoning_effort || ''} onChange={e => update('openai_reasoning_effort', e.target.value || null)}>
              <option value="">Varsayılan</option>
              <option value="low">Low — Hızlı, ucuz</option>
              <option value="medium">Medium — Dengeli</option>
              <option value="high">High — En derin düşünce</option>
            </select>
          </Row>
        )}
        {s.llm_provider === 'anthropic' && (
          <Row label="Thinking Effort">
            <select className={Input} value={s.anthropic_effort || ''} onChange={e => update('anthropic_effort', e.target.value || null)}>
              <option value="">Varsayılan</option>
              <option value="low">Low — Hızlı</option>
              <option value="medium">Medium — Dengeli</option>
              <option value="high">High — Extended thinking</option>
            </select>
          </Row>
        )}
        {s.llm_provider === 'google' && (
          <Row label="Thinking Level">
            <select className={Input} value={s.google_thinking_level || ''} onChange={e => update('google_thinking_level', e.target.value || null)}>
              <option value="">Varsayılan</option>
              <option value="minimal">Minimal — En hızlı</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High — En derin</option>
            </select>
          </Row>
        )}

        <Row label="Çıktı Dili">
          <select className={Input} value={s.output_language} onChange={e => update('output_language', e.target.value)}>
            {languages.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Row>

        <Row label="Tartışma Turları">
          <input type="number" min="1" max="10" className={Input} value={s.max_debate_rounds} onChange={e => update('max_debate_rounds', parseInt(e.target.value))} />
        </Row>
        <Row label="Risk Turları">
          <input type="number" min="1" max="10" className={Input} value={s.max_risk_rounds} onChange={e => update('max_risk_rounds', parseInt(e.target.value))} />
        </Row>
        <Row label="Paralel Analist Sayısı">
          <input type="number" min="1" max="16" className={Input} value={s.analyst_concurrency_limit} onChange={e => update('analyst_concurrency_limit', parseInt(e.target.value))} />
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
        {analysts.length === 0 ? (
          <p className="text-gray-600 text-sm">Yükleniyor...</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1">
            {analysts.map(a => (
              <label key={a.key} title={a.description} className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  className="accent-indigo-600"
                  checked={s.selected_analysts.includes(a.key)}
                  onChange={e => {
                    const next = e.target.checked
                      ? [...s.selected_analysts, a.key]
                      : s.selected_analysts.filter(x => x !== a.key)
                    update('selected_analysts', next)
                  }}
                />
                <span className="text-slate-300">{a.label}</span>
              </label>
            ))}
          </div>
        )}
      </Section>

      <Section title="Veri Kaynakları (Kategori Bazlı)">
        {(
          [
            ['data_vendor_core_stock', 'Hisse Fiyatı'],
            ['data_vendor_technicals', 'Teknik Göstergeler'],
            ['data_vendor_fundamentals', 'Temel Veriler'],
            ['data_vendor_news', 'Haber'],
          ] as [keyof Settings, string][]
        ).map(([field, label]) => (
          <Row key={field} label={label}>
            <select className={Input} value={s[field] as string} onChange={e => update(field, e.target.value)}>
              {dataVendors.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Row>
        ))}
      </Section>

      <Section title="Gelişmiş Ayarlar">
        <Row label="Checkpoint (Devam Etme)">
          <input type="checkbox" checked={s.checkpoint_enabled} onChange={e => update('checkpoint_enabled', e.target.checked)} className="w-5 h-5 accent-indigo-600" />
        </Row>
        <Row label="Eskiye Dönük Analizler">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={s.include_historical_analyses}
              onChange={e => update('include_historical_analyses', e.target.checked)}
              className="w-5 h-5 accent-indigo-600"
            />
            <span className="text-xs text-gray-500">Önceki raporları AI'ya dahil et (son 5 analiz)</span>
          </div>
        </Row>
        <Row label="Haber Sayısı (Ticker)">
          <input type="number" min="1" max="100" className={Input} value={s.news_article_limit} onChange={e => update('news_article_limit', parseInt(e.target.value))} />
        </Row>
        <Row label="Global Haber Sayısı">
          <input type="number" min="1" max="50" className={Input} value={s.global_news_article_limit} onChange={e => update('global_news_article_limit', parseInt(e.target.value))} />
        </Row>
        <Row label="Global Haber Geriye (Gün)">
          <input type="number" min="1" max="30" className={Input} value={s.global_news_lookback_days} onChange={e => update('global_news_lookback_days', parseInt(e.target.value))} />
        </Row>
        <Row label="Max Recursion Limiti">
          <input type="number" min="100" max="5000" className={Input} value={s.max_recur_limit} onChange={e => update('max_recur_limit', parseInt(e.target.value))} />
        </Row>
        <Row label="Benchmark Sembolü">
          <input className={Input} value={s.benchmark_ticker || ''} onChange={e => update('benchmark_ticker', e.target.value || null)} placeholder="Boş bırakın = otomatik (SPY)" />
        </Row>
        {s.llm_provider === 'azure' && (
          <Row label="Azure Deployment Adı">
            <input className={Input} value={s.azure_deployment || ''} onChange={e => update('azure_deployment', e.target.value || null)} placeholder="gpt-4o" />
          </Row>
        )}
      </Section>

      {/* Preset Management (MOD2) */}
      <Section title="Ayar Şablonları">
        <div className="flex gap-2">
          <input
            className={Input}
            placeholder="Şablon adı..."
            value={presetName}
            onChange={e => setPresetName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && savePreset()}
          />
          <button
            onClick={savePreset}
            disabled={presetSaving || !presetName.trim()}
            className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm px-3 py-1.5 rounded-xl transition whitespace-nowrap"
          >
            <BookmarkPlus size={14} /> Kaydet
          </button>
        </div>
        {presets.length === 0 ? (
          <p className="text-gray-600 text-xs">Henüz şablon yok.</p>
        ) : (
          <div className="space-y-1.5 pt-1">
            {presets.map(p => (
              <div key={p.id} className="flex items-center justify-between bg-gray-800 rounded-xl px-3 py-2">
                <span className="text-sm text-gray-300">{p.name}</span>
                <div className="flex items-center gap-2">
                  <button onClick={() => applyPreset(p.id)} className="text-violet-400 hover:text-violet-300 transition-colors" title="Uygula">
                    <Play size={13} />
                  </button>
                  <button onClick={() => deletePreset(p.id)} className="text-gray-600 hover:text-red-400 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Notifications (MOD4) */}
      <Section title="Bildirimler">
        <Row label="Webhook URL">
          <input
            className={Input}
            placeholder="https://hooks.slack.com/..."
            value={s.webhook_url || ''}
            onChange={e => update('webhook_url', e.target.value || null)}
          />
        </Row>
        <Row label="Webhook Aktif">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={s.webhook_enabled}
              onChange={e => update('webhook_enabled', e.target.checked)}
              className="w-5 h-5 accent-indigo-600"
            />
            {s.webhook_url && (
              <button
                onClick={testWebhook}
                disabled={webhookTesting}
                className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-2 py-1 rounded-lg transition"
              >
                {webhookTesting ? '...' : 'Test Et'}
              </button>
            )}
            {webhookTestResult && (
              <span className={`text-xs ${webhookTestResult.startsWith('✓') ? 'text-emerald-400' : 'text-red-400'}`}>
                {webhookTestResult}
              </span>
            )}
          </div>
        </Row>
        <Row label="Bildirim Olayları">
          <div className="flex flex-col gap-1.5">
            {[
              ['analysis_complete', 'Analiz tamamlandı'],
              ['trade_executed', 'İşlem gerçekleşti'],
              ['alert_triggered', 'Fiyat alarmı tetiklendi'],
            ].map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  className="accent-indigo-600"
                  checked={s.webhook_events.includes(key)}
                  onChange={e => {
                    const events = s.webhook_events ? s.webhook_events.split(',').filter(Boolean) : []
                    const next = e.target.checked ? [...events, key] : events.filter(x => x !== key)
                    update('webhook_events', next.join(','))
                  }}
                />
                {label}
              </label>
            ))}
          </div>
        </Row>
        <Row label="Tarayıcı Bildirimleri">
          <div className="flex items-center gap-3">
            <button
              onClick={toggleBrowserNotify}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${browserNotify ? 'bg-violet-600' : 'bg-gray-700'}`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${browserNotify ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
            <Bell size={14} className={browserNotify ? 'text-violet-400' : 'text-gray-600'} />
            <span className="text-xs text-gray-500">{browserNotify ? 'Açık' : 'Kapalı'}</span>
          </div>
        </Row>
      </Section>

      <div className="flex items-center gap-3">
        <button onClick={save} className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-5 py-2.5 text-sm font-semibold shadow-lg shadow-violet-500/20 transition-all">
          <Save size={15} /> {saved ? 'Kaydedildi ✓' : 'Kaydet'}
        </button>
        {saveError && <span className="text-red-400 text-sm">{saveError}</span>}
      </div>
    </div>
  )
}

const Input = "bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm w-full transition"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 space-y-3">
      <h3 className="text-sm font-semibold text-violet-400 uppercase tracking-wider mb-1">{title}</h3>
      {children}
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1.5 sm:gap-4">
      <span className="text-sm text-gray-400 whitespace-nowrap sm:pt-2 min-w-0 shrink-0">{label}</span>
      <div className="flex-1 sm:max-w-xs">{children}</div>
    </div>
  )
}
