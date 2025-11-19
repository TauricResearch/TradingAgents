"use client";

import { useState } from "react";
import { AnalysisRequest, AnalystType, LLMProvider } from "@/lib/types";

interface AnalysisFormProps {
  onSubmit: (request: AnalysisRequest) => void;
  isLoading?: boolean;
}

const LLM_OPTIONS = {
  [LLMProvider.OPENAI]: {
    quick: [
      { label: "GPT-4o-mini - Fast and efficient", value: "gpt-4o-mini" },
      { label: "GPT-4.1-nano - Ultra-lightweight", value: "gpt-4.1-nano" },
      { label: "GPT-4.1-mini - Compact model", value: "gpt-4.1-mini" },
      { label: "GPT-4o - Standard model", value: "gpt-4o" },
    ],
    deep: [
      { label: "GPT-4.1-nano - Ultra-lightweight", value: "gpt-4.1-nano" },
      { label: "GPT-4.1-mini - Compact model", value: "gpt-4.1-mini" },
      { label: "GPT-4o - Standard model", value: "gpt-4o" },
      { label: "o4-mini - Reasoning model (compact)", value: "o4-mini" },
      { label: "o3-mini - Advanced reasoning (lightweight)", value: "o3-mini" },
      { label: "o3 - Full advanced reasoning", value: "o3" },
      { label: "o1 - Premier reasoning model", value: "o1" },
    ],
  },
  [LLMProvider.ANTHROPIC]: {
    quick: [
      { label: "Claude Haiku 3.5 - Fast inference", value: "claude-3-5-haiku-latest" },
      { label: "Claude Sonnet 3.5 - Highly capable", value: "claude-3-5-sonnet-latest" },
      { label: "Claude Sonnet 3.7 - Exceptional hybrid", value: "claude-3-7-sonnet-latest" },
      { label: "Claude Sonnet 4 - High performance", value: "claude-sonnet-4-0" },
    ],
    deep: [
      { label: "Claude Haiku 3.5 - Fast inference", value: "claude-3-5-haiku-latest" },
      { label: "Claude Sonnet 3.5 - Highly capable", value: "claude-3-5-sonnet-latest" },
      { label: "Claude Sonnet 3.7 - Exceptional hybrid", value: "claude-3-7-sonnet-latest" },
      { label: "Claude Sonnet 4 - High performance", value: "claude-sonnet-4-0" },
      { label: "Claude Opus 4 - Most powerful", value: "claude-opus-4-0" },
    ],
  },
  [LLMProvider.GOOGLE]: {
    quick: [
      { label: "Gemini 2.0 Flash-Lite - Cost efficient", value: "gemini-2.0-flash-lite" },
      { label: "Gemini 2.0 Flash - Next generation", value: "gemini-2.0-flash" },
      { label: "Gemini 2.5 Flash - Adaptive thinking", value: "gemini-2.5-flash-preview-05-20" },
    ],
    deep: [
      { label: "Gemini 2.0 Flash-Lite - Cost efficient", value: "gemini-2.0-flash-lite" },
      { label: "Gemini 2.0 Flash - Next generation", value: "gemini-2.0-flash" },
      { label: "Gemini 2.5 Flash - Adaptive thinking", value: "gemini-2.5-flash-preview-05-20" },
      { label: "Gemini 2.5 Pro", value: "gemini-2.5-pro-preview-06-05" },
    ],
  },
  [LLMProvider.OPENROUTER]: {
    quick: [
      { label: "Meta: Llama 4 Scout", value: "meta-llama/llama-4-scout:free" },
      { label: "Meta: Llama 3.3 8B Instruct", value: "meta-llama/llama-3.3-8b-instruct:free" },
      { label: "Google Gemini 2.0 Flash", value: "google/gemini-2.0-flash-exp:free" },
    ],
    deep: [
      { label: "DeepSeek V3", value: "deepseek/deepseek-chat-v3-0324:free" },
    ],
  },
  [LLMProvider.OLLAMA]: {
    quick: [
      { label: "llama3.1 local", value: "llama3.1" },
      { label: "llama3.2 local", value: "llama3.2" },
    ],
    deep: [
      { label: "llama3.1 local", value: "llama3.1" },
      { label: "qwen3", value: "qwen3" },
    ],
  },
};

const BACKEND_URLS: Record<LLMProvider, string> = {
  [LLMProvider.OPENAI]: "https://api.openai.com/v1",
  [LLMProvider.ANTHROPIC]: "https://api.anthropic.com/",
  [LLMProvider.GOOGLE]: "https://generativelanguage.googleapis.com/v1",
  [LLMProvider.OPENROUTER]: "https://openrouter.ai/api/v1",
  [LLMProvider.OLLAMA]: "http://localhost:11434/v1",
};

export default function AnalysisForm({ onSubmit, isLoading }: AnalysisFormProps) {
  const [ticker, setTicker] = useState("SPY");
  const [analysisDate, setAnalysisDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [selectedAnalysts, setSelectedAnalysts] = useState<AnalystType[]>([
    AnalystType.MARKET,
    AnalystType.SOCIAL,
    AnalystType.NEWS,
    AnalystType.FUNDAMENTALS,
  ]);
  const [researchDepth, setResearchDepth] = useState(1);
  const [llmProvider, setLlmProvider] = useState<LLMProvider>(LLMProvider.OPENAI);
  const [quickThinkLLM, setQuickThinkLLM] = useState("gpt-4o-mini");
  const [deepThinkLLM, setDeepThinkLLM] = useState("o4-mini");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const request: AnalysisRequest = {
      ticker: ticker.toUpperCase(),
      analysis_date: analysisDate,
      analysts: selectedAnalysts,
      research_depth: researchDepth,
      llm_provider: llmProvider,
      backend_url: BACKEND_URLS[llmProvider],
      quick_think_llm: quickThinkLLM,
      deep_think_llm: deepThinkLLM,
    };
    onSubmit(request);
  };

  const toggleAnalyst = (analyst: AnalystType) => {
    setSelectedAnalysts((prev) =>
      prev.includes(analyst)
        ? prev.filter((a) => a !== analyst)
        : [...prev, analyst]
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label className="block text-sm font-medium mb-2">Ticker Symbol</label>
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          className="w-full px-3 py-2 border rounded-md"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Analysis Date</label>
        <input
          type="date"
          value={analysisDate}
          onChange={(e) => setAnalysisDate(e.target.value)}
          max={new Date().toISOString().split("T")[0]}
          className="w-full px-3 py-2 border rounded-md"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Analysts</label>
        <div className="space-y-2">
          {Object.values(AnalystType).map((analyst) => (
            <label key={analyst} className="flex items-center space-x-2">
              <input
                type="checkbox"
                checked={selectedAnalysts.includes(analyst)}
                onChange={() => toggleAnalyst(analyst)}
                className="rounded"
              />
              <span className="capitalize">{analyst} Analyst</span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Research Depth</label>
        <select
          value={researchDepth}
          onChange={(e) => setResearchDepth(Number(e.target.value))}
          className="w-full px-3 py-2 border rounded-md"
        >
          <option value={1}>Shallow - Quick research</option>
          <option value={3}>Medium - Moderate debate</option>
          <option value={5}>Deep - Comprehensive research</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">LLM Provider</label>
        <select
          value={llmProvider}
          onChange={(e) => {
            const provider = e.target.value as LLMProvider;
            setLlmProvider(provider);
            const options = LLM_OPTIONS[provider];
            setQuickThinkLLM(options.quick[0].value);
            setDeepThinkLLM(options.deep[0].value);
          }}
          className="w-full px-3 py-2 border rounded-md"
        >
          {Object.values(LLMProvider).map((provider) => (
            <option key={provider} value={provider}>
              {provider}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Quick-Thinking LLM</label>
        <select
          value={quickThinkLLM}
          onChange={(e) => setQuickThinkLLM(e.target.value)}
          className="w-full px-3 py-2 border rounded-md"
        >
          {LLM_OPTIONS[llmProvider].quick.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-2">Deep-Thinking LLM</label>
        <select
          value={deepThinkLLM}
          onChange={(e) => setDeepThinkLLM(e.target.value)}
          className="w-full px-3 py-2 border rounded-md"
        >
          {LLM_OPTIONS[llmProvider].deep.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        disabled={isLoading || selectedAnalysts.length === 0}
        className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? "Starting Analysis..." : "Start Analysis"}
      </button>
    </form>
  );
}

