import React, { useState, useEffect } from 'react';
import { 
  X, 
  Key, 
  Database, 
  Volume2, 
  VolumeX, 
  Bell, 
  BellOff, 
  Eye, 
  EyeOff, 
  Check, 
  Save, 
  ShieldCheck, 
  AlertCircle,
  Cpu
} from 'lucide-react';
import { APIKeyInfo } from '../types';
import { fetchApiKeys, updateApiKeys } from '../services/api';
import { 
  isSoundEnabled, 
  setSoundEnabled, 
  isNotificationsEnabled, 
  setNotificationsEnabled,
  playChime 
} from '../services/notification';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SettingsModalComponent: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<'llm' | 'data' | 'preferences'>('llm');
  const [keysList, setKeysList] = useState<APIKeyInfo[]>([]);
  const [inputValues, setInputValues] = useState<Record<string, string>>({});
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Preference states
  const [soundOn, setSoundOn] = useState(true);
  const [notifyOn, setNotifyOn] = useState(true);

  useEffect(() => {
    if (isOpen) {
      setSoundOn(isSoundEnabled());
      setNotifyOn(isNotificationsEnabled());
      loadKeys();
    }
  }, [isOpen]);

  const loadKeys = async () => {
    try {
      setLoading(true);
      const res = await fetchApiKeys();
      setKeysList(res.keys || []);
    } catch (err: any) {
      console.error('Failed to load API keys:', err);
      setErrorMsg('Failed to load API keys from server.');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const handleInputChange = (provider: string, val: string) => {
    setInputValues((prev) => ({ ...prev, [provider]: val }));
    setSaveSuccess(false);
  };

  const toggleShowKey = (provider: string) => {
    setShowKeys((prev) => ({ ...prev, [provider]: !prev[provider] }));
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);

      // Save preferences
      setSoundEnabled(soundOn);
      setNotificationsEnabled(notifyOn);

      // Save keys if modified
      const keysToUpdate: Record<string, string> = {};
      Object.entries(inputValues).forEach(([prov, val]) => {
        if (val !== undefined && val !== null) {
          keysToUpdate[prov] = val;
        }
      });

      if (Object.keys(keysToUpdate).length > 0) {
        const updated = await updateApiKeys(keysToUpdate);
        setKeysList(updated.keys || []);
        setInputValues({});
      }

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save settings');
    } finally {
      setLoading(false);
    }
  };

  const testAudio = () => {
    playChime('success');
  };

  const llmKeys = keysList.filter((k) => k.category === 'llm');
  const dataKeys = keysList.filter((k) => k.category === 'data');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/85">
      <div className="w-full max-w-2xl bg-dark-900 border border-dark-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-dark-700/80 flex items-center justify-between bg-dark-850/60">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-dark-750 border border-dark-600 flex items-center justify-center text-brand-cyan">
              <Key className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-100 font-mono tracking-wide">
                Terminal Settings & API Management
              </h2>
              <p className="text-[11px] text-slate-400 font-sans">
                Configure cloud intelligence providers, market data feeds, and local preferences
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-dark-700/60 px-6 bg-dark-850/30">
          <button
            onClick={() => setActiveTab('llm')}
            className={`flex items-center space-x-2 py-3 px-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === 'llm'
                ? 'border-brand-cyan text-brand-cyan'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>LLM Providers ({llmKeys.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('data')}
            className={`flex items-center space-x-2 py-3 px-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === 'data'
                ? 'border-brand-emerald text-brand-emerald'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>Data Feeds ({dataKeys.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('preferences')}
            className={`flex items-center space-x-2 py-3 px-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === 'preferences'
                ? 'border-brand-amber text-brand-amber'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Volume2 className="w-3.5 h-3.5" />
            <span>Terminal Audio & Alerts</span>
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {errorMsg && (
            <div className="p-3 rounded-lg bg-brand-rose/10 border border-brand-rose/30 flex items-center space-x-2 text-xs text-brand-rose">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {saveSuccess && (
            <div className="p-3 rounded-lg bg-brand-emerald/10 border border-brand-emerald/30 flex items-center space-x-2 text-xs text-brand-emerald">
              <ShieldCheck className="w-4 h-4 flex-shrink-0" />
              <span>Settings and API credentials updated successfully!</span>
            </div>
          )}

          {/* LLM & Data Feeds View */}
          {(activeTab === 'llm' || activeTab === 'data') && (
            <div className="space-y-3.5">
              <div className="text-[11px] text-slate-400 bg-dark-850/60 p-3 rounded-lg border border-dark-700/60 flex items-start space-x-2">
                <ShieldCheck className="w-4 h-4 text-brand-emerald flex-shrink-0 mt-0.5" />
                <span>
                  Keys are held securely in your local backend process environment and are never transmitted to external analytics. Existing keys are masked.
                </span>
              </div>

              {(activeTab === 'llm' ? llmKeys : dataKeys).map((item) => {
                const isConfigured = item.configured;
                const isShowing = showKeys[item.provider];
                const curInput = inputValues[item.provider] ?? '';

                return (
                  <div
                    key={item.provider}
                    className="p-3.5 rounded-xl bg-dark-850/40 border border-dark-700/60 flex flex-col space-y-2 hover:border-dark-600 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold font-mono uppercase text-slate-100">
                          {item.provider}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400 bg-dark-800 px-1.5 py-0.5 rounded border border-dark-700">
                          {item.env_var}
                        </span>
                      </div>

                      {isConfigured ? (
                        <span className="text-[10px] font-mono font-bold text-brand-emerald bg-brand-emerald/10 border border-brand-emerald/30 px-2 py-0.5 rounded flex items-center space-x-1">
                          <Check className="w-2.5 h-2.5" />
                          <span>Active ({item.preview})</span>
                        </span>
                      ) : (
                        <span className="text-[10px] font-mono text-slate-500 bg-dark-800 border border-dark-700 px-2 py-0.5 rounded">
                          Not Configured
                        </span>
                      )}
                    </div>

                    <div className="relative flex items-center">
                      <input
                        type={isShowing ? 'text' : 'password'}
                        placeholder={isConfigured ? 'Enter new key to replace existing...' : 'Paste API key here...'}
                        value={curInput}
                        onChange={(e) => handleInputChange(item.provider, e.target.value)}
                        className="w-full bg-dark-900 border border-dark-700/80 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 font-mono focus:outline-none focus:border-brand-cyan/60 pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => toggleShowKey(item.provider)}
                        className="absolute right-2.5 text-slate-500 hover:text-slate-300"
                        title={isShowing ? 'Hide' : 'Show'}
                      >
                        {isShowing ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Preferences Tab */}
          {activeTab === 'preferences' && (
            <div className="space-y-4">
              {/* Sound Option */}
              <div className="p-4 rounded-xl bg-dark-850/40 border border-dark-700/60 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className={`p-2.5 rounded-lg border ${soundOn ? 'bg-brand-amber/10 border-brand-amber/30 text-brand-amber' : 'bg-dark-800 border-dark-700 text-slate-500'}`}>
                    {soundOn ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Quant Synthesizer Chime</h4>
                    <p className="text-[11px] text-slate-400">Play an harmonic audio alert when an analysis pipeline finishes</p>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  {soundOn && (
                    <button
                      type="button"
                      onClick={testAudio}
                      className="px-2 py-1 rounded bg-dark-800 text-[11px] font-mono text-brand-amber border border-dark-700 hover:bg-dark-750"
                    >
                      Test Sound
                    </button>
                  )}
                  <input
                    type="checkbox"
                    checked={soundOn}
                    onChange={(e) => setSoundOn(e.target.checked)}
                    className="w-4 h-4 accent-brand-amber rounded cursor-pointer"
                  />
                </div>
              </div>

              {/* Desktop Notifications Option */}
              <div className="p-4 rounded-xl bg-dark-850/40 border border-dark-700/60 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className={`p-2.5 rounded-lg border ${notifyOn ? 'bg-brand-cyan/10 border-brand-cyan/30 text-brand-cyan' : 'bg-dark-800 border-dark-700 text-slate-500'}`}>
                    {notifyOn ? <Bell className="w-5 h-5" /> : <BellOff className="w-5 h-5" />}
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Desktop Push Notifications</h4>
                    <p className="text-[11px] text-slate-400">Send system desktop notifications when tab is inactive</p>
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={notifyOn}
                  onChange={(e) => setNotifyOn(e.target.checked)}
                  className="w-4 h-4 accent-brand-cyan rounded cursor-pointer"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-3.5 border-t border-dark-700/80 bg-dark-850/80 flex items-center justify-between">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-mono text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
          >
            Close
          </button>

          <button
            onClick={handleSave}
            disabled={loading}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-lg bg-gradient-to-r from-brand-cyan to-brand-emerald text-dark-950 font-bold text-xs shadow-lg shadow-brand-cyan/20 hover:shadow-brand-cyan/30 active:scale-95 transition-all disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5 stroke-[2.5]" />
            <span>{loading ? 'Saving...' : 'Save Settings'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export const SettingsModal = React.memo(SettingsModalComponent);
