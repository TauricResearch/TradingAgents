export type AgentStatus = 'pending' | 'in_progress' | 'completed';

export interface AgentState {
  [agentName: string]: AgentStatus;
}

export interface ReportSection {
  section: string;
  title: string;
  content: string;
}

export interface Stats {
  llm_calls: number;
  tool_calls: number;
  tokens_in: number;
  tokens_out: number;
  elapsed_seconds: number;
}

export interface Settings {
  llm_provider: string;
  backend_url: string | null;
  quick_think_llm: string;
  deep_think_llm: string;
  anthropic_effort: string | null;
  google_thinking_level: string | null;
  openai_reasoning_effort: string | null;
  research_depth: number;
  analysts: string[];
  output_language: string;
  data_vendors: {
    core_stock_apis: string;
    technical_indicators: string;
    fundamental_data: string;
    news_data: string;
  };
}

export const MODEL_OPTIONS: Record<string, { quick: [string, string][]; deep: [string, string][] }> = {
  openai: {
    quick: [["GPT-4.1 Mini", "gpt-4.1-mini"], ["GPT-4.1 Nano", "gpt-4.1-nano"], ["GPT-4.1", "gpt-4.1"]],
    deep:  [["GPT-4.1", "gpt-4.1"], ["GPT-4.1 Mini", "gpt-4.1-mini"], ["o4-mini", "o4-mini"]],
  },
  anthropic: {
    quick: [["Claude Sonnet 4.6", "claude-sonnet-4-6"], ["Claude Haiku 4.5", "claude-haiku-4-5"], ["Claude Sonnet 4.5", "claude-sonnet-4-5"]],
    deep:  [["Claude Opus 4.6", "claude-opus-4-6"], ["Claude Opus 4.5", "claude-opus-4-5"], ["Claude Sonnet 4.6", "claude-sonnet-4-6"]],
  },
  google: {
    quick: [["Gemini 2.5 Flash", "gemini-2.5-flash"], ["Gemini 2.0 Flash", "gemini-2.0-flash"]],
    deep:  [["Gemini 2.5 Pro", "gemini-2.5-pro"], ["Gemini 2.5 Flash", "gemini-2.5-flash"]],
  },
  xai: {
    quick: [["Grok 3 Fast", "grok-3-fast"], ["Grok 3 Mini Fast", "grok-3-mini-fast"]],
    deep:  [["Grok 3", "grok-3"], ["Grok 3 Mini", "grok-3-mini"]],
  },
  deepseek: {
    quick: [["DeepSeek V3", "deepseek-chat"], ["DeepSeek V2.5", "deepseek-v2.5"]],
    deep:  [["DeepSeek R1", "deepseek-reasoner"], ["DeepSeek V3", "deepseek-chat"]],
  },
  qwen: {
    quick: [["Qwen Plus", "qwen-plus"], ["Qwen Turbo", "qwen-turbo"]],
    deep:  [["Qwen Max", "qwen-max"], ["Qwen Plus", "qwen-plus"]],
  },
  glm: {
    quick: [["GLM-4 Flash", "glm-4-flash"], ["GLM-4", "glm-4"]],
    deep:  [["GLM-4 Plus", "glm-4-plus"], ["GLM-4", "glm-4"]],
  },
  ollama: {
    quick: [["Qwen3:latest", "qwen3:latest"], ["Llama3.2:latest", "llama3.2:latest"]],
    deep:  [["Llama3.1:latest", "llama3.1:latest"], ["Qwen3:latest", "qwen3:latest"]],
  },
};

export const PROVIDER_URLS: Record<string, string | null> = {
  openai:     "https://api.openai.com/v1",
  anthropic:  "https://api.anthropic.com/",
  xai:        "https://api.x.ai/v1",
  deepseek:   "https://api.deepseek.com",
  qwen:       "https://dashscope.aliyuncs.com/compatible-mode/v1",
  glm:        "https://open.bigmodel.cn/api/paas/v4/",
  openrouter: "https://openrouter.ai/api/v1",
  ollama:     "http://localhost:11434/v1",
  google:     null,
  azure:      null,
};

export const LANGUAGES = [
  "English", "Chinese (中文)", "Japanese (日本語)", "Spanish (Español)",
  "French (Français)", "German (Deutsch)", "Arabic (العربية)",
  "Korean (한국어)", "Russian (Русский)",
];
