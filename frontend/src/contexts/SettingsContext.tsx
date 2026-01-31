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
