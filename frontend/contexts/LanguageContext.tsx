"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode, useSyncExternalStore } from 'react';
import { translations, Locale, defaultLocale, TranslationKeys } from '@/lib/i18n';

interface LanguageContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: TranslationKeys;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

const STORAGE_KEY = 'tradingagentsx-locale';

// Helper to safely get localStorage value
function getStoredLocale(): Locale {
  if (typeof window === 'undefined') {
    return defaultLocale;
  }
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'en' || stored === 'zh-TW') {
    return stored;
  }
  return defaultLocale;
}

// Subscribe to storage events for cross-tab sync
function subscribeToStorage(callback: () => void) {
  window.addEventListener('storage', callback);
  return () => window.removeEventListener('storage', callback);
}

// Server snapshot always returns default locale
function getServerSnapshot(): Locale {
  return defaultLocale;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  // Use useSyncExternalStore for proper SSR hydration
  const storedLocale = useSyncExternalStore(
    subscribeToStorage,
    getStoredLocale,
    getServerSnapshot
  );
  
  const [locale, setLocaleState] = useState<Locale>(storedLocale);

  // Sync with stored value when it changes (e.g., from another tab)
  useEffect(() => {
    setLocaleState(storedLocale);
  }, [storedLocale]);

  // Save locale to localStorage when it changes
  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, newLocale);
    }
  }, []);

  // Get translations for current locale
  const t = translations[locale];

  const value: LanguageContextType = {
    locale,
    setLocale,
    t,
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextType {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
}

// Convenience hook for just getting translations
export function useTranslation(): TranslationKeys {
  const { t } = useLanguage();
  return t;
}
