import { useState } from 'react';
import type { Settings } from '../types';
import { MODEL_OPTIONS, PROVIDER_URLS, LANGUAGES } from '../types';

const PROVIDERS: [string, string][] = [
  ['Anthropic', 'anthropic'], ['OpenAI', 'openai'], ['Google', 'google'],
  ['xAI', 'xai'], ['DeepSeek', 'deepseek'], ['Qwen', 'qwen'],
  ['GLM', 'glm'], ['OpenRouter', 'openrouter'], ['Azure OpenAI', 'azure'],
  ['Ollama (local)', 'ollama'],
];

const ANALYSTS: [string, string][] = [
  ['Market', 'market'], ['Social Media', 'social'],
  ['News', 'news'], ['Fundamentals', 'fundamentals'],
];

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: 'var(--bg-card)', borderRadius: 10, padding: 20 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>{label}</label>
      {children}
    </div>
  );
}

const selectStyle = {
  width: '100%', background: 'var(--bg-input)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13,
} as const;

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={selectStyle}>
      {options.map(([label, val]) => <option key={val} value={val}>{label}</option>)}
    </select>
  );
}

function Pills({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {options.map(([label, val]) => (
        <button
          key={val}
          onClick={() => onChange(val)}
          style={{
            padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500, border: '1px solid',
            borderColor: value === val ? 'var(--accent)' : 'var(--border)',
            background: value === val ? 'rgba(124,58,237,0.2)' : 'var(--bg-input)',
            color: value === val ? 'var(--accent-light)' : 'var(--text-muted)',
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

interface Props {
  settings: Settings;
  onSave: (s: Settings) => void;
}

export default function SettingsTab({ settings, onSave }: Props) {
  const [local, setLocal] = useState<Settings>(settings);
  const [saved, setSaved] = useState(false);

  const update = (patch: Partial<Settings>) => setLocal(prev => ({ ...prev, ...patch }));

  const hasModelCatalog = (p: string) => p in MODEL_OPTIONS;

  const handleProviderChange = (provider: string) => {
    update({
      llm_provider: provider,
      backend_url: PROVIDER_URLS[provider] ?? null,
      quick_think_llm: hasModelCatalog(provider) ? MODEL_OPTIONS[provider].quick[0][1] : '',
      deep_think_llm:  hasModelCatalog(provider) ? MODEL_OPTIONS[provider].deep[0][1]  : '',
      anthropic_effort:       provider === 'anthropic' ? (local.anthropic_effort ?? 'high')     : null,
      google_thinking_level:  provider === 'google'    ? (local.google_thinking_level ?? 'high') : null,
      openai_reasoning_effort: provider === 'openai'   ? (local.openai_reasoning_effort ?? 'medium') : null,
    });
  };

  const handleAnalystToggle = (key: string) => {
    const next = local.analysts.includes(key)
      ? local.analysts.filter(a => a !== key)
      : [...local.analysts, key];
    if (next.length > 0) update({ analysts: next });
  };

  const handleSave = async () => {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(local),
    });
    onSave(local);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const quickOptions: [string, string][] = hasModelCatalog(local.llm_provider) ? MODEL_OPTIONS[local.llm_provider].quick : [];
  const deepOptions:  [string, string][] = hasModelCatalog(local.llm_provider) ? MODEL_OPTIONS[local.llm_provider].deep  : [];

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

        {/* LLM Provider */}
        <Card title="LLM Provider">
          <Field label="Provider">
            <Select value={local.llm_provider} onChange={handleProviderChange} options={PROVIDERS} />
          </Field>

          <Field label="API Endpoint">
            <input
              value={local.backend_url ?? ''}
              onChange={e => update({ backend_url: e.target.value || null })}
              placeholder="https://..."
              style={selectStyle}
            />
          </Field>

          <Field label="Quick-Thinking Model">
            {hasModelCatalog(local.llm_provider) ? (
              <Select value={local.quick_think_llm} onChange={v => update({ quick_think_llm: v })} options={quickOptions} />
            ) : (
              <input value={local.quick_think_llm} onChange={e => update({ quick_think_llm: e.target.value })} placeholder="Enter model ID..." style={selectStyle} />
            )}
          </Field>

          <Field label="Deep-Thinking Model">
            {hasModelCatalog(local.llm_provider) ? (
              <Select value={local.deep_think_llm} onChange={v => update({ deep_think_llm: v })} options={deepOptions} />
            ) : (
              <input value={local.deep_think_llm} onChange={e => update({ deep_think_llm: e.target.value })} placeholder="Enter model ID..." style={selectStyle} />
            )}
          </Field>

          {local.llm_provider === 'anthropic' && (
            <Field label="Effort Level">
              <Pills value={local.anthropic_effort ?? 'high'} onChange={v => update({ anthropic_effort: v })}
                options={[['High', 'high'], ['Medium', 'medium'], ['Low', 'low']]} />
            </Field>
          )}
          {local.llm_provider === 'openai' && (
            <Field label="Reasoning Effort">
              <Pills value={local.openai_reasoning_effort ?? 'medium'} onChange={v => update({ openai_reasoning_effort: v })}
                options={[['High', 'high'], ['Medium', 'medium'], ['Low', 'low']]} />
            </Field>
          )}
          {local.llm_provider === 'google' && (
            <Field label="Thinking Mode">
              <Pills value={local.google_thinking_level ?? 'high'} onChange={v => update({ google_thinking_level: v })}
                options={[['Enable', 'high'], ['Minimal', 'minimal']]} />
            </Field>
          )}
        </Card>

        {/* Analysis Defaults */}
        <Card title="Analysis Defaults">
          <Field label="Analysts">
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {ANALYSTS.map(([label, key]) => {
                const checked = local.analysts.includes(key);
                return (
                  <button key={key} onClick={() => handleAnalystToggle(key)} style={{
                    padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500, border: '1px solid',
                    borderColor: checked ? 'var(--green)' : 'var(--border)',
                    background: checked ? 'rgba(16,185,129,0.15)' : 'var(--bg-input)',
                    color: checked ? 'var(--green)' : 'var(--text-muted)',
                  }}>
                    {label}
                  </button>
                );
              })}
            </div>
          </Field>

          <div style={{ height: 1, background: 'var(--border)', margin: '12px 0' }} />

          <Field label="Research Depth">
            <Pills
              value={String(local.research_depth)}
              onChange={v => update({ research_depth: Number(v) })}
              options={[['Shallow', '1'], ['Medium', '3'], ['Deep', '5']]}
            />
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, fontStyle: 'italic' }}>
              Controls debate rounds between Bull/Bear researchers and risk analysts.
            </p>
          </Field>

          <div style={{ height: 1, background: 'var(--border)', margin: '12px 0' }} />

          <Field label="Output Language">
            <Select
              value={local.output_language}
              onChange={v => update({ output_language: v })}
              options={LANGUAGES.map(l => [l, l])}
            />
          </Field>
        </Card>

        {/* Data Sources — full width */}
        <div style={{ gridColumn: '1 / -1' }}>
          <Card title="Data Sources">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
              {(['core_stock_apis', 'technical_indicators', 'fundamental_data', 'news_data'] as const).map(key => {
                const labels: Record<string, string> = {
                  core_stock_apis: 'Stock Data', technical_indicators: 'Technical Indicators',
                  fundamental_data: 'Fundamentals', news_data: 'News',
                };
                return (
                  <Field key={key} label={labels[key]}>
                    <Select
                      value={local.data_vendors[key]}
                      onChange={v => update({ data_vendors: { ...local.data_vendors, [key]: v } })}
                      options={[['yfinance (free)', 'yfinance'], ['Alpha Vantage', 'alpha_vantage']]}
                    />
                  </Field>
                );
              })}
            </div>
          </Card>
        </div>

      </div>

      {/* Save row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 20, paddingTop: 20, borderTop: '1px solid var(--border)' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Saved to ~/.tradingagents/web_config.json
        </span>
        <button
          onClick={handleSave}
          style={{ background: saved ? 'var(--green)' : 'var(--accent)', color: '#fff', borderRadius: 6, padding: '10px 28px', fontSize: 14, fontWeight: 600 }}
        >
          {saved ? 'Saved ✓' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
