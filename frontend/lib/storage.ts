/**
 * localStorage utility for API settings with encryption
 * API keys are encrypted using AES-256-GCM before storage
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

const STORAGE_KEY = "tradingagents_api_settings";
const ENCRYPTED_FLAG_KEY = "tradingagents_encrypted";

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
 * Get API settings from localStorage (async due to decryption)
 */
export async function getApiSettingsAsync(): Promise<ApiSettings> {
  if (typeof window === "undefined") {
    return DEFAULT_API_SETTINGS;
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return DEFAULT_API_SETTINGS;
    }

    const parsed = JSON.parse(stored);
    
    // If legacy format detected, return as-is (will be encrypted on next save)
    if (isLegacyFormat()) {
      console.warn("Legacy unencrypted settings detected. Will encrypt on next save.");
      return { ...DEFAULT_API_SETTINGS, ...parsed };
    }
    
    // Decrypt the settings
    const decrypted = await decryptObject(parsed);
    return { ...DEFAULT_API_SETTINGS, ...decrypted };
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

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return { ...DEFAULT_API_SETTINGS, ...parsed };
    }
  } catch (error) {
    console.error("Error reading API settings from localStorage:", error);
  }

  return DEFAULT_API_SETTINGS;
}

/**
 * Save API settings to localStorage with encryption
 */
export async function saveApiSettingsAsync(settings: ApiSettings): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }

  try {
    // Encrypt sensitive fields
    const encrypted = await encryptObject(settings as unknown as Record<string, string>);
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(encrypted));
    localStorage.setItem(ENCRYPTED_FLAG_KEY, "true");
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
 * Clear API settings from localStorage
 */
export function clearApiSettings(): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(ENCRYPTED_FLAG_KEY);
    clearCryptoData();
  } catch (error) {
    console.error("Error clearing API settings from localStorage:", error);
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
