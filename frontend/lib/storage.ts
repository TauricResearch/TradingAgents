/**
 * localStorage/sessionStorage utility for API settings with encryption
 * 
 * Storage Strategy:
 * - Logged-in users: localStorage with encryption (persistent)
 * - Anonymous users: sessionStorage (cleared on browser close)
 * 
 * API keys are encrypted using AES-256-GCM before storage (localStorage only)
 */

import { encryptObject, decryptObject, isEncrypted, clearCryptoData } from "./crypto";

export interface ApiSettings {
  // Required providers
  openai_api_key: string;
  alpha_vantage_api_key: string;
  
  // Optional providers
  anthropic_api_key: string;
  google_api_key: string;
  grok_api_key: string;
  deepseek_api_key: string;
  qwen_api_key: string;
  finmind_api_key: string;  // 台灣股市資料 API
  
  // Custom endpoint
  custom_base_url: string;
  custom_api_key: string;
}

// Storage keys
const STORAGE_KEY = "tradingagents_api_settings";
const ENCRYPTED_FLAG_KEY = "tradingagents_encrypted";
const AUTH_TOKEN_KEY = "tradingagents_auth_token";

// Storage mode type
export type StorageMode = "local" | "session";

export const DEFAULT_API_SETTINGS: ApiSettings = {
  openai_api_key: "",
  alpha_vantage_api_key: "",
  anthropic_api_key: "",
  google_api_key: "",
  grok_api_key: "",
  deepseek_api_key: "",
  qwen_api_key: "",
  finmind_api_key: "",
  custom_base_url: "",
  custom_api_key: "",
};

/**
 * Check if user is currently authenticated
 */
function isUserAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) return false;
  
  // Check if token is expired
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const exp = payload.exp * 1000;
    return Date.now() < exp;
  } catch {
    return false;
  }
}

/**
 * Get the appropriate storage based on authentication status
 * - Authenticated: localStorage (persistent)
 * - Anonymous: sessionStorage (cleared on browser close)
 */
function getStorage(): Storage {
  if (typeof window === "undefined") {
    // Return a mock storage for SSR
    return {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
      length: 0,
      key: () => null,
    };
  }
  
  return isUserAuthenticated() ? localStorage : sessionStorage;
}

/**
 * Get current storage mode
 */
export function getCurrentStorageMode(): StorageMode {
  return isUserAuthenticated() ? "local" : "session";
}

/**
 * Check if stored data is using legacy (unencrypted) format
 */
function isLegacyFormat(): boolean {
  if (typeof window === "undefined") return false;
  
  const encryptedFlag = localStorage.getItem(ENCRYPTED_FLAG_KEY);
  if (encryptedFlag === "true") return false;
  
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return false;
  
  try {
    const parsed = JSON.parse(stored);
    // Check if any API key looks like plaintext (starts with known prefixes)
    const apiKeyFields = Object.keys(parsed).filter(k => k.includes("api_key"));
    for (const field of apiKeyFields) {
      const value = parsed[field];
      if (value && typeof value === "string") {
        // OpenAI keys start with sk-, Anthropic with sk-ant-, etc.
        if (value.startsWith("sk-") || value.startsWith("AIza") || value.length < 50) {
          return true;
        }
      }
    }
  } catch {
    return false;
  }
  
  return false;
}

/**
 * Get API settings (async due to potential decryption)
 * 
 * Storage strategy:
 * - Authenticated users: Read from localStorage (encrypted)
 * - Anonymous users: Read from sessionStorage (plaintext, cleared on browser close)
 */
export async function getApiSettingsAsync(): Promise<ApiSettings> {
  if (typeof window === "undefined") {
    return DEFAULT_API_SETTINGS;
  }

  const storage = getStorage();
  const authenticated = isUserAuthenticated();

  try {
    const stored = storage.getItem(STORAGE_KEY);
    if (!stored) {
      // If authenticated, also check sessionStorage for data to migrate
      if (authenticated) {
        const sessionData = sessionStorage.getItem(STORAGE_KEY);
        if (sessionData) {
          console.log("Migrating session data to localStorage after login");
          const parsed = JSON.parse(sessionData);
          const merged = { ...DEFAULT_API_SETTINGS, ...parsed };
          await saveApiSettingsAsync(merged);
          sessionStorage.removeItem(STORAGE_KEY);
          return merged;
        }
      }
      return DEFAULT_API_SETTINGS;
    }

    const parsed = JSON.parse(stored);
    
    // For authenticated users, decrypt the data
    if (authenticated) {
      // If legacy format detected, return as-is (will be encrypted on next save)
      if (isLegacyFormat()) {
        console.warn("Legacy unencrypted settings detected. Will encrypt on next save.");
        return { ...DEFAULT_API_SETTINGS, ...parsed };
      }
      
      // Decrypt the settings
      const decrypted = await decryptObject(parsed);
      return { ...DEFAULT_API_SETTINGS, ...decrypted };
    }
    
    // For anonymous users, data is stored as plaintext in sessionStorage
    return { ...DEFAULT_API_SETTINGS, ...parsed };
  } catch (error) {
    console.error("Error reading API settings:", error);
    return DEFAULT_API_SETTINGS;
  }
}

/**
 * Get API settings synchronously (for backward compatibility)
 * WARNING: This returns encrypted values - use getApiSettingsAsync for actual values
 */
export function getApiSettings(): ApiSettings {
  if (typeof window === "undefined") {
    return DEFAULT_API_SETTINGS;
  }

  const storage = getStorage();
  
  try {
    const stored = storage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return { ...DEFAULT_API_SETTINGS, ...parsed };
    }
  } catch (error) {
    console.error("Error reading API settings:", error);
  }

  return DEFAULT_API_SETTINGS;
}

/**
 * Save API settings (async)
 * 
 * Storage strategy:
 * - Authenticated users: Save to localStorage with encryption (persistent)
 * - Anonymous users: Save to sessionStorage as plaintext (cleared on browser close)
 */
export async function saveApiSettingsAsync(settings: ApiSettings): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }

  const storage = getStorage();
  const authenticated = isUserAuthenticated();

  try {
    if (authenticated) {
      // For authenticated users, encrypt and store in localStorage
      const encrypted = await encryptObject(settings as unknown as Record<string, string>);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(encrypted));
      localStorage.setItem(ENCRYPTED_FLAG_KEY, "true");
      console.log("API settings saved to localStorage (encrypted)");
    } else {
      // For anonymous users, store as plaintext in sessionStorage
      // This will be automatically cleared when browser closes
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
      console.log("API settings saved to sessionStorage (will clear on browser close)");
    }
  } catch (error) {
    console.error("Error saving API settings:", error);
    throw error;
  }
}

/**
 * Save API settings synchronously (legacy - not recommended)
 * WARNING: This saves unencrypted data - use saveApiSettingsAsync instead
 */
export function saveApiSettings(settings: ApiSettings): void {
  if (typeof window === "undefined") {
    return;
  }

  // Call async version and ignore the promise (for backward compatibility)
  saveApiSettingsAsync(settings).catch(console.error);
}

/**
 * Clear API settings from both localStorage and sessionStorage
 */
export function clearApiSettings(): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    // Clear from localStorage
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(ENCRYPTED_FLAG_KEY);
    
    // Clear from sessionStorage
    sessionStorage.removeItem(STORAGE_KEY);
    
    // Clear crypto data
    clearCryptoData();
    
    console.log("API settings cleared from all storage");
  } catch (error) {
    console.error("Error clearing API settings:", error);
  }
}

/**
 * Migrate legacy unencrypted settings to encrypted format
 */
export async function migrateToEncrypted(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  
  if (!isLegacyFormat()) {
    return false; // Already encrypted or no data
  }
  
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return false;
    
    const parsed = JSON.parse(stored);
    const merged = { ...DEFAULT_API_SETTINGS, ...parsed };
    
    // Save with encryption
    await saveApiSettingsAsync(merged);
    
    console.log("Successfully migrated settings to encrypted format");
    return true;
  } catch (error) {
    console.error("Failed to migrate settings:", error);
    return false;
  }
}
