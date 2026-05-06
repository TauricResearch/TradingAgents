import { useState, useEffect } from 'react';
import type { Settings } from './types';
import AnalysisTab from './components/AnalysisTab';
import SettingsTab from './components/SettingsTab';
import './index.css';

const DEFAULT_SETTINGS: Settings = {
  llm_provider: 'openai',
  backend_url: 'https://api.openai.com/v1',
  quick_think_llm: 'gpt-4.1-mini',
  deep_think_llm: 'gpt-4.1',
  anthropic_effort: null,
  google_thinking_level: null,
  openai_reasoning_effort: null,
  research_depth: 1,
  analysts: ['market', 'news', 'fundamentals'],
  output_language: 'English',
  data_vendors: {
    core_stock_apis: 'yfinance',
    technical_indicators: 'yfinance',
    fundamental_data: 'yfinance',
    news_data: 'yfinance',
  },
};

type Tab = 'analysis' | 'settings';

export default function App() {
  const [tab, setTab] = useState<Tab>('analysis');
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);

  useEffect(() => {
    fetch('/api/settings')
      .then(r => r.json())
      .then((s: Settings) => setSettings(s))
      .catch(() => { /* use defaults */ });
  }, []);

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>TradingAgents</h1>
        <span style={{ background: 'var(--accent)', color: '#fff', fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600 }}>
          Web UI
        </span>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {(['analysis', 'settings'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '10px 20px', fontSize: 14, fontWeight: 500, background: 'none',
              color: tab === t ? 'var(--accent)' : 'var(--text-muted)',
              borderBottom: `2px solid ${tab === t ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -1, textTransform: 'capitalize',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'analysis' && <AnalysisTab settings={settings} />}
      {tab === 'settings' && <SettingsTab settings={settings} onSave={setSettings} />}
    </div>
  );
}
