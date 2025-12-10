/**
 * Helper functions for API configuration
 */

import { ApiSettings } from "./storage";

/**
 * Get the base URL for a given LLM model
 * If custom_base_url is set, it takes precedence
 */
export function getBaseUrlForModel(model: string, customBaseUrl?: string): string {
  // OpenAI models - always use OpenAI API
  if (
    model.startsWith("gpt-") ||
    model.startsWith("o4-") ||
    model.startsWith("o1-")
  ) {
    return "https://api.openai.com/v1";
  }

  // Anthropic models - always use Anthropic API
  if (model.startsWith("claude-")) {
    return "https://api.anthropic.com/v1";
  }

  // Google models - always use Google API
  if (model.startsWith("gemini-")) {
    return "https://generativelanguage.googleapis.com/v1beta/openai";
  }

  // Grok models - always use Grok API
  if (model.startsWith("grok-")) {
    return "https://api.x.ai/v1";
  }

  // DeepSeek models - always use DeepSeek API
  if (model.startsWith("deepseek-")) {
    return "https://api.deepseek.com/v1";
  }

  // Qwen models - always use Qwen API
  if (model.startsWith("qwen")) {
    return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1";
  }

  // For "custom" or unknown models, use custom_base_url if provided
  if (customBaseUrl && customBaseUrl.trim() !== "") {
    return customBaseUrl;
  }

  // Default to OpenAI
  return "https://api.openai.com/v1";
}

/**
 * Get the API key for a given LLM model from saved settings
 * If custom_base_url is set and custom_api_key exists, use custom key
 */
export function getApiKeyForModel(
  model: string,
  settings: ApiSettings
): string {
  // OpenAI models - always use OpenAI API key
  if (
    model.startsWith("gpt-") ||
    model.startsWith("o4-") ||
    model.startsWith("o1-")
  ) {
    return settings.openai_api_key;
  }

  // Anthropic models - always use Anthropic API key
  if (model.startsWith("claude-")) {
    return settings.anthropic_api_key || "";
  }

  // Google models - always use Google API key
  if (model.startsWith("gemini-")) {
    return settings.google_api_key || "";
  }

  // Grok models - always use Grok API key
  if (model.startsWith("grok-")) {
    return settings.grok_api_key || "";
  }

  // DeepSeek models - always use DeepSeek API key
  if (model.startsWith("deepseek-")) {
    return settings.deepseek_api_key || "";
  }

  // Qwen models - always use Qwen API key
  if (model.startsWith("qwen")) {
    return settings.qwen_api_key || "";
  }

  // For "custom" or unknown models, use custom_api_key if provided
  if (settings.custom_api_key && settings.custom_api_key.trim() !== "") {
    return settings.custom_api_key;
  }

  // Default to OpenAI
  return settings.openai_api_key;
}
