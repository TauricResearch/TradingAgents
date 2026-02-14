import { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  X, Settings, Cpu, Key, Zap, Brain, Sparkles,
  Eye, EyeOff, Check, AlertCircle, RefreshCw, Clock
} from 'lucide-react';
import { useSettings, MODELS, PROVIDERS, TIMEZONES } from '../contexts/SettingsContext';
import type { ModelId, ProviderId, TimezoneId } from '../contexts/SettingsContext';

export default function SettingsModal() {
  const { settings, updateSettings, resetSettings, isSettingsOpen, closeSettings } = useSettings();
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  if (!isSettingsOpen) return null;

  const handleProviderChange = (providerId: ProviderId) => {
    updateSettings({ provider: providerId });
  };

  const handleModelChange = (type: 'deepThinkModel' | 'quickThinkModel', modelId: ModelId) => {
    updateSettings({ [type]: modelId });
  };

  const handleApiKeyChange = (value: string) => {
    updateSettings({ anthropicApiKey: value });
    setTestResult(null);
  };

  const testApiKey = async () => {
    if (!settings.anthropicApiKey) {
      setTestResult({ success: false, message: 'Please enter an API key' });
      return;
    }

    setIsTesting(true);
    setTestResult(null);

    try {
      // Simple validation - just check format
      if (!settings.anthropicApiKey.startsWith('sk-ant-')) {
        setTestResult({ success: false, message: 'Invalid API key format. Should start with sk-ant-' });
      } else {
        setTestResult({ success: true, message: 'API key format looks valid' });
      }
    } catch (error) {
      setTestResult({ success: false, message: 'Failed to validate API key' });
    } finally {
      setIsTesting(false);
    }
  };

  const selectedProvider = PROVIDERS[settings.provider];

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={closeSettings}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-2xl shadow-2xl transform transition-all">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-slate-700">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-nifty-100 dark:bg-nifty-900/30 rounded-lg">
                <Settings className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">Configure AI models and API settings</p>
              </div>
            </div>
            <button
              onClick={closeSettings}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5 text-gray-500" />
            </button>
          </div>

          {/* Content */}
          <div className="p-4 space-y-6 max-h-[70vh] overflow-y-auto">
            {/* Provider Selection */}
            <section>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                <Zap className="w-4 h-4 text-amber-500" />
                LLM Provider
              </h3>
              <div className="grid gap-2">
                {Object.values(PROVIDERS).map(provider => (
                  <button
                    key={provider.id}
                    onClick={() => handleProviderChange(provider.id as ProviderId)}
                    className={`
                      flex items-start gap-3 p-3 rounded-xl border-2 transition-all text-left
                      ${settings.provider === provider.id
                        ? 'border-nifty-500 bg-nifty-50 dark:bg-nifty-900/20'
                        : 'border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600'
                      }
                    `}
                  >
                    <div className={`
                      w-5 h-5 rounded-full border-2 flex items-center justify-center mt-0.5
                      ${settings.provider === provider.id
                        ? 'border-nifty-500 bg-nifty-500'
                        : 'border-gray-300 dark:border-slate-600'
                      }
                    `}>
                      {settings.provider === provider.id && (
                        <Check className="w-3 h-3 text-white" />
                      )}
                    </div>
                    <div>
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        {provider.name}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {provider.description}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            {/* API Key (only shown for API provider) */}
            {selectedProvider.requiresApiKey && (
              <section>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  <Key className="w-4 h-4 text-purple-500" />
                  API Key
                </h3>
                <div className="space-y-2">
                  <div className="relative">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={settings.anthropicApiKey}
                      onChange={(e) => handleApiKeyChange(e.target.value)}
                      placeholder="sk-ant-..."
                      className="w-full px-4 py-2.5 pr-20 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-nifty-500 font-mono text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                      {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={testApiKey}
                      disabled={isTesting || !settings.anthropicApiKey}
                      className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-slate-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {isTesting ? (
                        <RefreshCw className="w-3 h-3 animate-spin" />
                      ) : (
                        <Check className="w-3 h-3" />
                      )}
                      Validate Key
                    </button>
                    {testResult && (
                      <span className={`flex items-center gap-1 text-xs ${testResult.success ? 'text-green-600' : 'text-red-600'}`}>
                        {testResult.success ? <Check className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                        {testResult.message}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Your API key is stored locally in your browser and never sent to our servers.
                  </p>
                </div>
              </section>
            )}

            {/* Model Selection */}
            <section>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                <Cpu className="w-4 h-4 text-blue-500" />
                Model Selection
              </h3>

              {/* Deep Think Model */}
              <div className="mb-4">
                <label className="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                  <Brain className="w-3 h-3" />
                  Deep Think Model (Complex Analysis)
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {Object.values(MODELS).map(model => (
                    <button
                      key={model.id}
                      onClick={() => handleModelChange('deepThinkModel', model.id as ModelId)}
                      className={`
                        p-2 rounded-lg border-2 transition-all text-center
                        ${settings.deepThinkModel === model.id
                          ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                          : 'border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600'
                        }
                      `}
                    >
                      <div className={`text-sm font-medium ${
                        settings.deepThinkModel === model.id
                          ? 'text-blue-700 dark:text-blue-300'
                          : 'text-gray-700 dark:text-gray-300'
                      }`}>
                        {model.name.replace('Claude ', '')}
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Quick Think Model */}
              <div>
                <label className="flex items-center gap-2 text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                  <Sparkles className="w-3 h-3" />
                  Quick Think Model (Fast Operations)
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {Object.values(MODELS).map(model => (
                    <button
                      key={model.id}
                      onClick={() => handleModelChange('quickThinkModel', model.id as ModelId)}
                      className={`
                        p-2 rounded-lg border-2 transition-all text-center
                        ${settings.quickThinkModel === model.id
                          ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                          : 'border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600'
                        }
                      `}
                    >
                      <div className={`text-sm font-medium ${
                        settings.quickThinkModel === model.id
                          ? 'text-green-700 dark:text-green-300'
                          : 'text-gray-700 dark:text-gray-300'
                      }`}>
                        {model.name.replace('Claude ', '')}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </section>

            {/* Analysis Settings */}
            <section>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                <Settings className="w-4 h-4 text-gray-500" />
                Analysis Settings
              </h3>
              <div>
                <label className="flex items-center justify-between text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                  <span>Max Debate Rounds</span>
                  <span className="text-nifty-600 dark:text-nifty-400">{settings.maxDebateRounds}</span>
                </label>
                <input
                  type="range"
                  min="1"
                  max="5"
                  value={settings.maxDebateRounds}
                  onChange={(e) => updateSettings({ maxDebateRounds: parseInt(e.target.value) })}
                  className="w-full h-2 bg-gray-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-nifty-600"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>1 (Faster)</span>
                  <span>5 (More thorough)</span>
                </div>
              </div>

              {/* Parallel Workers */}
              <div className="mt-4">
                <label className="flex items-center justify-between text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">
                  <span>Parallel Workers (Analyze All)</span>
                  <span className="text-nifty-600 dark:text-nifty-400">{settings.parallelWorkers}</span>
                </label>
                <input
                  type="range"
                  min="1"
                  max="5"
                  value={settings.parallelWorkers}
                  onChange={(e) => updateSettings({ parallelWorkers: parseInt(e.target.value) })}
                  className="w-full h-2 bg-gray-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-nifty-600"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-1">
                  <span>1 (Conservative)</span>
                  <span>5 (Aggressive)</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Number of stocks to analyze simultaneously during Analyze All
                </p>
              </div>
            </section>

            {/* Auto-Analyze Schedule */}
            <section>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                <Clock className="w-4 h-4 text-indigo-500" />
                Auto-Analyze Schedule
              </h3>

              {/* Enable Toggle */}
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-xs font-medium text-gray-700 dark:text-gray-300">
                    Daily Auto-Analyze
                  </div>
                  <div className="text-[10px] text-gray-500 dark:text-gray-400">
                    Automatically run Analyze All at the scheduled time
                  </div>
                </div>
                <button
                  onClick={() => updateSettings({ autoAnalyzeEnabled: !settings.autoAnalyzeEnabled })}
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    settings.autoAnalyzeEnabled
                      ? 'bg-nifty-600'
                      : 'bg-gray-300 dark:bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                    settings.autoAnalyzeEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`} />
                </button>
              </div>

              {/* Timezone */}
              <div className={`mb-3 ${!settings.autoAnalyzeEnabled ? 'opacity-40 pointer-events-none' : ''}`}>
                <label className="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1 block">Timezone</label>
                <select
                  value={settings.autoAnalyzeTimezone}
                  onChange={(e) => updateSettings({ autoAnalyzeTimezone: e.target.value as TimezoneId })}
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-nifty-500"
                >
                  {TIMEZONES.map(tz => (
                    <option key={tz.id} value={tz.id}>
                      {tz.label} (UTC{tz.offset})
                    </option>
                  ))}
                </select>
              </div>

              {/* Time Picker */}
              <div className={`flex items-center gap-3 ${!settings.autoAnalyzeEnabled ? 'opacity-40 pointer-events-none' : ''}`}>
                <div className="flex-1">
                  <label className="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1 block">Hour</label>
                  <select
                    value={settings.autoAnalyzeTime.split(':')[0]}
                    onChange={(e) => {
                      const minute = settings.autoAnalyzeTime.split(':')[1];
                      updateSettings({ autoAnalyzeTime: `${e.target.value}:${minute}` });
                    }}
                    className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-nifty-500"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={String(i).padStart(2, '0')}>
                        {String(i).padStart(2, '0')}
                      </option>
                    ))}
                  </select>
                </div>
                <span className="text-lg font-bold text-gray-400 dark:text-gray-500 mt-4">:</span>
                <div className="flex-1">
                  <label className="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1 block">Minute</label>
                  <select
                    value={settings.autoAnalyzeTime.split(':')[1]}
                    onChange={(e) => {
                      const hour = settings.autoAnalyzeTime.split(':')[0];
                      updateSettings({ autoAnalyzeTime: `${hour}:${e.target.value}` });
                    }}
                    className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-nifty-500"
                  >
                    {Array.from({ length: 12 }, (_, i) => (
                      <option key={i} value={String(i * 5).padStart(2, '0')}>
                        {String(i * 5).padStart(2, '0')}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Preview */}
              {settings.autoAnalyzeEnabled && (
                <div className="mt-3 p-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800">
                  <p className="text-xs text-indigo-700 dark:text-indigo-300 font-medium">
                    Runs daily at {settings.autoAnalyzeTime} {TIMEZONES.find(tz => tz.id === settings.autoAnalyzeTimezone)?.label || settings.autoAnalyzeTimezone} when the backend is running
                  </p>
                </div>
              )}
            </section>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-slate-700">
            <button
              onClick={resetSettings}
              className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            >
              Reset to Defaults
            </button>
            <button
              onClick={closeSettings}
              className="px-4 py-2 text-sm font-medium bg-nifty-600 text-white rounded-lg hover:bg-nifty-700 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
