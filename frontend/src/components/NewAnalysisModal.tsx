import React, { useState, useEffect, useMemo } from 'react';
import { ConfigOptions, JobCreatePayload } from '../types';
import { X, Sparkles, Sliders, Users, Check, AlertCircle, Cpu, Zap, BrainCircuit, Globe } from 'lucide-react';
import { toast } from './Toast';

interface NewAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (payload: JobCreatePayload) => Promise<void>;
  configOptions: ConfigOptions | null;
}

export const NewAnalysisModal: React.FC<NewAnalysisModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  configOptions,
}) => {
  const [ticker, setTicker] = useState('NVDA');
  const [tradeDate, setTradeDate] = useState(new Date().toISOString().split('T')[0]);
  const [provider, setProvider] = useState('openai');
  const [deepModel, setDeepModel] = useState('gpt-5.6');
  const [quickModel, setQuickModel] = useState('gpt-5.6-luna');
  const [debateRounds, setDebateRounds] = useState(1);
  const [riskRounds, setRiskRounds] = useState(1);
  const [language, setLanguage] = useState('English');
  const [isCustomModel, setIsCustomModel] = useState(false);
  const [selectedPresetTab, setSelectedPresetTab] = useState<'stocks' | 'crypto' | 'commodities'>('stocks');
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([
    'market',
    'social',
    'news',
    'fundamentals',
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pure derived state from ticker
  const normalizedTicker = ticker.trim().toUpperCase();
  const isCrypto = useMemo(() => {
    const cryptoSuffixes = ['-USD', '-USDT', '-USDC', '-BTC', '-ETH'];
    return cryptoSuffixes.some((s) => normalizedTicker.endsWith(s)) ||
      normalizedTicker.startsWith('BTC') ||
      normalizedTicker.startsWith('ETH') ||
      normalizedTicker.startsWith('SOL');
  }, [normalizedTicker]);

  const isCommodity = useMemo(() => {
    return ['XAUUSD', 'GC=F', 'XAU', 'GOLD', 'SILVER', 'SI=F', 'XAGUSD'].includes(normalizedTicker);
  }, [normalizedTicker]);

  const assetType: 'stock' | 'crypto' = isCrypto ? 'crypto' : 'stock';

  // Curated Model Packages
  const modelPresets = [
    { id: 'openai-flagship', provider: 'openai', name: 'OpenAI Flagship', deep: 'gpt-4o', quick: 'gpt-4o-mini', desc: 'Balanced accuracy & speed' },
    { id: 'google-speed', provider: 'google', name: 'Google Gemini', deep: 'gemini-1.5-pro', quick: 'gemini-1.5-flash', desc: 'Fast analysis with wide context' },
    { id: 'anthropic-reasoning', provider: 'anthropic', name: 'Anthropic Claude', deep: 'claude-3-5-sonnet', quick: 'claude-3-5-haiku', desc: 'Exceptional qualitative synthesis' },
    { id: 'deepseek-quant', provider: 'deepseek', name: 'DeepSeek AI', deep: 'deepseek-chat', quick: 'deepseek-chat', desc: 'Cost-effective quantitative speed' },
  ];

  // Initialize from backend default_config if present
  useEffect(() => {
    if (configOptions?.default_config) {
      const def = configOptions.default_config;
      if (def.llm_provider) setProvider(def.llm_provider);
      if (def.deep_think_llm) setDeepModel(def.deep_think_llm);
      if (def.quick_think_llm) setQuickModel(def.quick_think_llm);
      if (def.output_language) setLanguage(def.output_language);
    }
  }, [configOptions]);

  const handleSelectModelPreset = (preset: typeof modelPresets[0]) => {
    setProvider(preset.provider);
    setDeepModel(preset.deep);
    setQuickModel(preset.quick);
    setIsCustomModel(false);
  };

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider);
    if (configOptions?.providers) {
      const p = configOptions.providers.find((item) => item.id === newProvider);
      if (p) {
        setDeepModel(p.default_deep);
        setQuickModel(p.default_quick);
      }
    }
  };

  if (!isOpen) return null;

  const handleToggleAnalyst = (key: string) => {
    if (key === 'fundamentals' && (isCrypto || isCommodity)) return;
    setSelectedAnalysts((prev) =>
      prev.includes(key) ? prev.filter((a) => a !== key) : [...prev, key]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!normalizedTicker) {
      setError('Ticker symbol is required.');
      return;
    }

    const activeAnalysts = (isCrypto || isCommodity)
      ? selectedAnalysts.filter((a) => a !== 'fundamentals')
      : selectedAnalysts;

    if (activeAnalysts.length === 0) {
      setError('Please select at least one analyst.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await onSubmit({
        ticker: normalizedTicker,
        trade_date: tradeDate,
        asset_type: assetType,
        analysts: activeAnalysts,
        llm_provider: provider,
        deep_think_llm: deepModel,
        quick_think_llm: quickModel,
        max_debate_rounds: debateRounds,
        max_risk_discuss_rounds: riskRounds,
        output_language: language,
      });
      toast.success(`Analysis launched for ${normalizedTicker}!`);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to start analysis job');
    } finally {
      setLoading(false);
    }
  };

  const presetInstruments = {
    stocks: ['NVDA', 'AAPL', 'MSFT', 'TSLA', 'QQQ', 'SPY', 'AMZN'],
    crypto: ['BTC-USD', 'ETH-USD', 'SOL-USD'],
    commodities: ['XAUUSD', 'GC=F', 'SILVER', 'XAGUSD'],
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-dark-950/85 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-2xl bg-dark-900 border border-dark-700/90 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92dvh]">
        {/* Header */}
        <div className="px-5 py-4 border-b border-dark-700/80 flex items-center justify-between bg-dark-850/60 shrink-0">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-brand-emerald/15 border border-brand-emerald/30 flex items-center justify-center text-brand-emerald shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm sm:text-base font-bold text-slate-100 font-mono tracking-tight">
                Launch New Analysis
              </h2>
              <p className="text-[11px] text-slate-400 font-sans">
                Configure quantitative multi-agent trading deliberation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body Form */}
        <form onSubmit={handleSubmit} className="p-5 sm:p-6 overflow-y-auto space-y-5 flex-1">
          {error && (
            <div className="p-3 rounded-lg bg-brand-rose/10 border border-brand-rose/30 flex items-center space-x-2 text-xs text-brand-rose">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Section 1: Instrument & Date */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
                1. Target Asset & Date
              </label>
              <div className="flex items-center space-x-1 text-[11px]">
                {(['stocks', 'crypto', 'commodities'] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setSelectedPresetTab(tab)}
                    className={`px-2 py-0.5 rounded capitalize transition-colors ${
                      selectedPresetTab === tab
                        ? 'bg-dark-700 text-brand-cyan font-semibold border border-dark-600'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Ticker Symbol</label>
                <div className="relative">
                  <input
                    type="text"
                    value={ticker}
                    onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    placeholder="e.g. NVDA, BTC-USD, XAUUSD"
                    className="w-full bg-dark-850 border border-dark-700 rounded-lg px-3 py-2 text-sm font-mono font-bold text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-emerald transition-colors"
                  />
                  <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-dark-750 text-brand-cyan min-w-[54px] text-center pointer-events-none border border-dark-650">
                    {isCommodity ? 'COMMODITY' : assetType}
                  </span>
                </div>
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Trade / Backtest Date</label>
                <input
                  type="date"
                  value={tradeDate}
                  onChange={(e) => setTradeDate(e.target.value)}
                  className="w-full bg-dark-850 border border-dark-700 rounded-lg px-3 py-2 text-sm font-mono text-slate-100 focus:outline-none focus:border-brand-emerald transition-colors"
                />
              </div>
            </div>

            {/* Quick Presets for Selected Category */}
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[10px] text-slate-500 font-mono mr-1">Presets:</span>
              {presetInstruments[selectedPresetTab].map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTicker(t)}
                  className={`text-[11px] font-mono px-2 py-0.5 rounded border transition-colors ${
                    ticker === t
                      ? 'bg-brand-emerald/20 border-brand-emerald/50 text-brand-emerald font-semibold'
                      : 'bg-dark-800/80 border-dark-700 text-slate-400 hover:text-slate-200 hover:bg-dark-750'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Section 2: Analyst Team Selection */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono flex items-center space-x-1.5">
                <Users className="w-3.5 h-3.5 text-brand-cyan" />
                <span>2. Analyst Specializations</span>
              </label>
              <span className="text-[11px] text-slate-500 font-mono">
                {selectedAnalysts.length} Selected
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {[
                { id: 'market', name: 'Market Technical Analyst', desc: 'MACD, RSI, Moving Averages, Bollinger Bands, ATR' },
                { id: 'social', name: 'Sentiment Analyst', desc: 'StockTwits, Reddit, and Retail crowd positioning' },
                { id: 'news', name: 'Macro & News Analyst', desc: 'World events, FRED Fed rates, Polymarket probability' },
                { id: 'fundamentals', name: 'Fundamentals Analyst', desc: 'Balance sheet, free cash flow, margin trends' },
              ].map((an) => {
                const isDisabled = an.id === 'fundamentals' && (isCrypto || isCommodity);
                const isSelected = selectedAnalysts.includes(an.id) && !isDisabled;

                return (
                  <div
                    key={an.id}
                    onClick={() => !isDisabled && handleToggleAnalyst(an.id)}
                    className={`p-3 rounded-xl border flex items-start space-x-2.5 cursor-pointer transition-all ${
                      isDisabled
                        ? 'opacity-35 cursor-not-allowed bg-dark-900 border-dark-800'
                        : isSelected
                        ? 'bg-brand-cyan/10 border-brand-cyan/40 text-slate-100 shadow-sm'
                        : 'bg-dark-850/50 border-dark-700/60 text-slate-400 hover:bg-dark-800 hover:border-dark-600'
                    }`}
                  >
                    <div
                      className={`w-4 h-4 mt-0.5 rounded flex items-center justify-center border transition-colors ${
                        isSelected ? 'bg-brand-cyan border-brand-cyan text-dark-950' : 'border-dark-600 bg-dark-900'
                      }`}
                    >
                      {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                    </div>
                    <div className="flex-1">
                      <div className="text-xs font-semibold text-slate-200">{an.name}</div>
                      <div className="text-[10px] text-slate-400 leading-tight mt-0.5 font-sans">{an.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Section 3: Model & Debate Configuration */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono flex items-center space-x-1.5">
                <Sliders className="w-3.5 h-3.5 text-brand-amber" />
                <span>3. LLM Intelligence & Debate</span>
              </label>
              <button
                type="button"
                onClick={() => setIsCustomModel(!isCustomModel)}
                className="text-[11px] font-mono text-brand-cyan hover:underline"
              >
                {isCustomModel ? 'Use Recommended Presets' : 'Custom Models'}
              </button>
            </div>

            {/* Quick Model Presets */}
            {!isCustomModel ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {modelPresets.map((p) => {
                  const isSelected = provider === p.provider;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => handleSelectModelPreset(p)}
                      className={`p-2.5 rounded-xl border text-left transition-all ${
                        isSelected
                          ? 'bg-brand-cyan/15 border-brand-cyan text-white shadow-sm'
                          : 'bg-dark-850 border-dark-700/60 text-slate-400 hover:border-dark-600 hover:text-slate-200'
                      }`}
                    >
                      <div className="text-xs font-bold truncate text-slate-100">{p.name}</div>
                      <div className="text-[10px] text-slate-400 truncate mt-0.5">{p.desc}</div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3 rounded-xl bg-dark-850/60 border border-dark-700/80">
                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => handleProviderChange(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-brand-emerald"
                  >
                    {configOptions?.providers ? (
                      configOptions.providers.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))
                    ) : (
                      <>
                        <option value="openai">OpenAI</option>
                        <option value="google">Google Gemini</option>
                        <option value="anthropic">Anthropic Claude</option>
                        <option value="deepseek">DeepSeek</option>
                        <option value="ollama">Ollama (Local)</option>
                      </>
                    )}
                  </select>
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Deep Thinker (PM)</label>
                  <input
                    type="text"
                    value={deepModel}
                    onChange={(e) => setDeepModel(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-brand-emerald"
                  />
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block mb-1">Quick Thinker (Agents)</label>
                  <input
                    type="text"
                    value={quickModel}
                    onChange={(e) => setQuickModel(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-brand-emerald"
                  />
                </div>
              </div>
            )}

            {/* Rounds & Language */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
              <div className="p-3 rounded-xl bg-dark-850 border border-dark-700/60">
                <div className="flex justify-between text-xs mb-1 font-mono">
                  <span className="text-slate-400">Bull/Bear Debate:</span>
                  <span className="font-bold text-brand-cyan">{debateRounds} Round(s)</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="3"
                  value={debateRounds}
                  onChange={(e) => setDebateRounds(parseInt(e.target.value))}
                  className="w-full cursor-pointer accent-brand-cyan"
                />
                <div className="text-[10px] text-slate-500 mt-1">
                  {debateRounds === 1 ? 'Quick (~45s)' : debateRounds === 2 ? 'Standard (~90s)' : 'Exhaustive (~180s)'}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-dark-850 border border-dark-700/60">
                <div className="flex justify-between text-xs mb-1 font-mono">
                  <span className="text-slate-400">Risk Discussion:</span>
                  <span className="font-bold text-brand-amber">{riskRounds} Round(s)</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="3"
                  value={riskRounds}
                  onChange={(e) => setRiskRounds(parseInt(e.target.value))}
                  className="w-full cursor-pointer accent-brand-amber"
                />
                <div className="text-[10px] text-slate-500 mt-1">
                  {riskRounds === 1 ? 'Conservative check' : riskRounds === 2 ? 'Aggressive scrutiny' : 'Multi-level audit'}
                </div>
              </div>

              <div className="p-3 rounded-xl bg-dark-850 border border-dark-700/60 flex flex-col justify-between">
                <label className="text-xs text-slate-400 font-mono block mb-1">Report Language</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-brand-emerald"
                >
                  <option value="English">English</option>
                  <option value="Vietnamese">Vietnamese (Tiếng Việt)</option>
                  <option value="Chinese">Chinese (中文)</option>
                  <option value="Japanese">Japanese (日本語)</option>
                  <option value="German">German</option>
                  <option value="French">French</option>
                </select>
                <div className="text-[10px] text-slate-500 mt-1 font-sans">
                  Output formatting language
                </div>
              </div>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="pt-4 border-t border-dark-700/80 flex items-center justify-end space-x-3 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-dark-700 text-xs font-semibold text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={loading}
              className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-brand-emerald to-emerald-600 hover:from-emerald-400 hover:to-brand-emerald text-dark-950 font-bold text-xs shadow-lg shadow-brand-emerald/25 disabled:opacity-50 transition-all active:scale-95"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-dark-950 border-t-transparent rounded-full animate-spin" />
                  <span>Launching Agents...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Execute Analysis</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
