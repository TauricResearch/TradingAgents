/**
 * localStorage utility for API settings
 */

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

export const DEFAULT_API_SETTINGS: ApiSettings = {
  openai_api_key: "",
  alpha_vantage_api_key: "",
  anthropic_api_key: "",
  google_api_key: "",
  grok_api_key: "",
  deepseek_api_key: "",
  qwen_api_key: "",
  finmind_api_key: "",  // 台灣股市資料 API
  custom_base_url: "",
  custom_api_key: "",
};

/**
 * Get API settings from localStorage
 */
export function getApiSettings(): ApiSettings {
  if (typeof window === "undefined") {
    return DEFAULT_API_SETTINGS;
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // Merge with defaults to handle any missing fields
      return { ...DEFAULT_API_SETTINGS, ...parsed };
    }
  } catch (error) {
    console.error("Error reading API settings from localStorage:", error);
  }

  return DEFAULT_API_SETTINGS;
}

/**
 * Save API settings to localStorage
 */
export function saveApiSettings(settings: ApiSettings): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (error) {
    console.error("Error saving API settings to localStorage:", error);
    throw error;
  }
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
  } catch (error) {
    console.error("Error clearing API settings from localStorage:", error);
  }
}
