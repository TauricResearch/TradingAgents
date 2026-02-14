import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';

// Model options
export const MODELS = {
  opus: { id: 'opus', name: 'Claude Opus', description: 'Most capable, best for complex reasoning' },
  sonnet: { id: 'sonnet', name: 'Claude Sonnet', description: 'Balanced performance and speed' },
  haiku: { id: 'haiku', name: 'Claude Haiku', description: 'Fastest, good for simple tasks' },
} as const;

// Provider options
export const PROVIDERS = {
  claude_subscription: {
    id: 'claude_subscription',
    name: 'Claude Subscription',
    description: 'Use your Claude Max subscription (no API key needed)',
    requiresApiKey: false
  },
  anthropic_api: {
    id: 'anthropic_api',
    name: 'Anthropic API',
    description: 'Use Anthropic API directly with your API key',
    requiresApiKey: true
  },
} as const;

export type ModelId = keyof typeof MODELS;
export type ProviderId = keyof typeof PROVIDERS;

// Common timezones with labels and IANA identifiers
export const TIMEZONES = [
  { id: 'Asia/Kolkata', label: 'IST (India)', offset: '+05:30' },
  { id: 'Asia/Tokyo', label: 'JST (Japan)', offset: '+09:00' },
  { id: 'Asia/Shanghai', label: 'CST (China)', offset: '+08:00' },
  { id: 'Asia/Singapore', label: 'SGT (Singapore)', offset: '+08:00' },
  { id: 'Asia/Dubai', label: 'GST (Dubai)', offset: '+04:00' },
  { id: 'Asia/Hong_Kong', label: 'HKT (Hong Kong)', offset: '+08:00' },
  { id: 'Europe/London', label: 'GMT/BST (London)', offset: '+00:00' },
  { id: 'Europe/Paris', label: 'CET (Paris/Berlin)', offset: '+01:00' },
  { id: 'Europe/Moscow', label: 'MSK (Moscow)', offset: '+03:00' },
  { id: 'America/New_York', label: 'EST (New York)', offset: '-05:00' },
  { id: 'America/Chicago', label: 'CST (Chicago)', offset: '-06:00' },
  { id: 'America/Los_Angeles', label: 'PST (Los Angeles)', offset: '-08:00' },
  { id: 'America/Sao_Paulo', label: 'BRT (Sao Paulo)', offset: '-03:00' },
  { id: 'Australia/Sydney', label: 'AEST (Sydney)', offset: '+10:00' },
  { id: 'Australia/Perth', label: 'AWST (Perth)', offset: '+08:00' },
  { id: 'Pacific/Auckland', label: 'NZST (Auckland)', offset: '+12:00' },
  { id: 'Africa/Johannesburg', label: 'SAST (Johannesburg)', offset: '+02:00' },
  { id: 'UTC', label: 'UTC', offset: '+00:00' },
] as const;

export type TimezoneId = typeof TIMEZONES[number]['id'];

interface Settings {
  // Model settings
  deepThinkModel: ModelId;
  quickThinkModel: ModelId;

  // Provider settings
  provider: ProviderId;

  // API keys (only used when provider is anthropic_api)
  anthropicApiKey: string;

  // Analysis settings
  maxDebateRounds: number;
  parallelWorkers: number;

  // Auto-analyze schedule
  autoAnalyzeEnabled: boolean;
  autoAnalyzeTime: string; // "HH:MM" in 24hr format
  autoAnalyzeTimezone: TimezoneId;
}

interface SettingsContextType {
  settings: Settings;
  updateSettings: (newSettings: Partial<Settings>) => void;
  resetSettings: () => void;
  isSettingsOpen: boolean;
  openSettings: () => void;
  closeSettings: () => void;
}

const DEFAULT_SETTINGS: Settings = {
  deepThinkModel: 'opus',
  quickThinkModel: 'sonnet',
  provider: 'claude_subscription',
  anthropicApiKey: '',
  maxDebateRounds: 1,
  parallelWorkers: 3,
  autoAnalyzeEnabled: false,
  autoAnalyzeTime: '09:00',
  autoAnalyzeTimezone: 'Asia/Kolkata',
};

const STORAGE_KEY = 'nifty50ai_settings';

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(() => {
    // Load from localStorage on initial render
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          return { ...DEFAULT_SETTINGS, ...parsed };
        } catch (e) {
          console.error('Failed to parse settings from localStorage:', e);
        }
      }
    }
    return DEFAULT_SETTINGS;
  });

  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Persist settings to localStorage whenever they change
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // Don't store the API key in plain text - encrypt it or use a more secure method in production
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    }
  }, [settings]);

  // Sync auto-analyze schedule to backend whenever it changes
  useEffect(() => {
    const syncSchedule = async () => {
      try {
        await fetch('http://localhost:8001/settings/schedule', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            enabled: settings.autoAnalyzeEnabled,
            time: settings.autoAnalyzeTime,
            timezone: settings.autoAnalyzeTimezone,
            config: {
              deep_think_model: settings.deepThinkModel,
              quick_think_model: settings.quickThinkModel,
              provider: settings.provider,
              api_key: settings.anthropicApiKey || undefined,
              max_debate_rounds: settings.maxDebateRounds,
              parallel_workers: settings.parallelWorkers,
            },
          }),
        });
      } catch {
        // Backend may not be running — silently ignore
      }
    };
    syncSchedule();
  }, [settings.autoAnalyzeEnabled, settings.autoAnalyzeTime, settings.autoAnalyzeTimezone, settings.deepThinkModel, settings.quickThinkModel, settings.provider, settings.anthropicApiKey, settings.maxDebateRounds, settings.parallelWorkers]);

  const updateSettings = (newSettings: Partial<Settings>) => {
    setSettings(prev => ({ ...prev, ...newSettings }));
  };

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS);
    if (typeof window !== 'undefined') {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  const openSettings = () => setIsSettingsOpen(true);
  const closeSettings = () => setIsSettingsOpen(false);

  return (
    <SettingsContext.Provider value={{
      settings,
      updateSettings,
      resetSettings,
      isSettingsOpen,
      openSettings,
      closeSettings,
    }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
