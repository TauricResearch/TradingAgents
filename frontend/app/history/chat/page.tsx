"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Image from "next/image";
import { useLanguage } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/auth-context";
import { getApiSettingsAsync } from "@/lib/storage";
import { getBaseUrlForModel } from "@/lib/api-helpers";
import { api } from "@/lib/api";
import { getReportsByMarketType, type SavedReport } from "@/lib/reports-db";
import { getCloudReports, isCloudSyncEnabled } from "@/lib/user-api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  MessageCircle,
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  AlertCircle,
  Trash2,
  ArrowLeft,
  Settings2,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const AVAILABLE_MODELS = [
  // OpenAI
  { id: "gpt-5.2-2025-12-11", name: "GPT-5.2", provider: "openai", logo: "/logos/openai.svg" },
  { id: "gpt-5.1", name: "GPT-5.1", provider: "openai", logo: "/logos/openai.svg" },
  { id: "gpt-5-mini", name: "GPT-5 Mini", provider: "openai", logo: "/logos/openai.svg" },
  { id: "gpt-5-nano", name: "GPT-5 Nano", provider: "openai", logo: "/logos/openai.svg" },
  { id: "gpt-4.1-mini", name: "GPT-4.1 Mini", provider: "openai", logo: "/logos/openai.svg" },
  { id: "gpt-4.1-nano", name: "GPT-4.1 Nano", provider: "openai", logo: "/logos/openai.svg" },
  { id: "o4-mini", name: "o4-mini", provider: "openai", logo: "/logos/openai.svg" },
  
  // Anthropic
  { id: "claude-sonnet-4-5-20250929", name: "Claude Sonnet 4.5", provider: "anthropic", logo: "/logos/claude-color.svg" },
  { id: "claude-haiku-4-5-20251001", name: "Claude Haiku 4.5", provider: "anthropic", logo: "/logos/claude-color.svg" },
  { id: "claude-sonnet-4-20250514", name: "Claude Sonnet 4", provider: "anthropic", logo: "/logos/claude-color.svg" },
  { id: "claude-3-haiku-20240307", name: "Claude 3 Haiku", provider: "anthropic", logo: "/logos/claude-color.svg" },

  // Google
  { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", provider: "google", logo: "/logos/gemini-color.svg" },
  { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", provider: "google", logo: "/logos/gemini-color.svg" },
  { id: "gemini-2.5-flash-lite", name: "Gemini 2.5 Flash Lite", provider: "google", logo: "/logos/gemini-color.svg" },
  { id: "gemini-2.0-flash", name: "Gemini 2.0 Flash", provider: "google", logo: "/logos/gemini-color.svg" },
  { id: "gemini-2.0-flash-lite", name: "Gemini 2.0 Flash Lite", provider: "google", logo: "/logos/gemini-color.svg" },

  // Grok
  { id: "grok-4-1-fast-reasoning", name: "Grok 4.1 Fast Reasoning", provider: "grok", logo: "/logos/grok.svg" },
  { id: "grok-4-1-fast-non-reasoning", name: "Grok 4.1 Fast Non Reasoning", provider: "grok", logo: "/logos/grok.svg" },
  { id: "grok-4-fast-reasoning", name: "Grok 4 Fast Reasoning", provider: "grok", logo: "/logos/grok.svg" },
  { id: "grok-4-fast-non-reasoning", name: "Grok 4 Fast Non Reasoning", provider: "grok", logo: "/logos/grok.svg" },
  { id: "grok-4-0709", name: "Grok 4", provider: "grok", logo: "/logos/grok.svg" },
  { id: "grok-3", name: "Grok 3", provider: "grok", logo: "/logos/grok.svg" },
  { id: "grok-3-mini", name: "Grok 3 Mini", provider: "grok", logo: "/logos/grok.svg" },

  // DeepSeek
  { id: "deepseek-reasoner", name: "DeepSeek Reasoner", provider: "deepseek", logo: "/logos/deepseek-color.svg" },
  { id: "deepseek-chat", name: "DeepSeek Chat", provider: "deepseek", logo: "/logos/deepseek-color.svg" },

  // Qwen
  { id: "qwen3-max", name: "Qwen 3 Max", provider: "qwen", logo: "/logos/qwen-color.svg" },
  { id: "qwen-plus", name: "Qwen Plus", provider: "qwen", logo: "/logos/qwen-color.svg" },
  { id: "qwen-flash", name: "Qwen Flash", provider: "qwen", logo: "/logos/qwen-color.svg" },

  // Custom
  { id: "custom", name: "Other (自訂模型)", provider: "custom", logo: null },
];

function HistoryChatContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t, locale } = useLanguage();
  const { isAuthenticated } = useAuth();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<SavedReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(true);
  
  // Default to GPT-5 Mini
  const [selectedModelId, setSelectedModelId] = useState<string>("gpt-5-mini");
  const [customModel, setCustomModel] = useState<string>("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const ticker = searchParams.get("ticker");
  const dateStr = searchParams.get("date");
  const market = searchParams.get("market");

  // Load the specific report
  useEffect(() => {
    const loadReport = async () => {
      if (!ticker || !dateStr || !market) {
        setLoadingReport(false);
        return;
      }

      try {
        setLoadingReport(true);
        // Try local DB first
        const localObj = await getReportsByMarketType(market as any);
        const match = localObj.find(
          (r) => r.ticker === ticker && r.analysis_date === dateStr
        );

        if (match) {
          setReport(match);
        } else if (isAuthenticated && isCloudSyncEnabled()) {
          // Fallback to cloud
          const cloudReports = await getCloudReports();
          if (cloudReports) {
            const cloudMatch = cloudReports.find(
              (r) =>
                r.ticker === ticker &&
                r.analysis_date === dateStr &&
                r.market_type === market
            );
            if (cloudMatch) {
              setReport({
                id: parseInt(cloudMatch.id.replace(/-/g, "").slice(0, 8), 16),
                ticker: cloudMatch.ticker,
                market_type: cloudMatch.market_type as any,
                analysis_date: cloudMatch.analysis_date,
                saved_at: new Date(cloudMatch.created_at),
                result: cloudMatch.result,
                language: cloudMatch.language,
              });
            }
          }
        }
      } catch (err) {
        console.error("Failed to load report for chat:", err);
      } finally {
        setLoadingReport(false);
      }
    };

    loadReport();
  }, [ticker, dateStr, market, isAuthenticated]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Focus input when loaded
  useEffect(() => {
    if (!loadingReport && report) {
      setTimeout(() => inputRef.current?.focus(), 200);
    }
  }, [loadingReport, report]);

  const handleClearChat = () => {
    setMessages([]);
    setError(null);
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || !report) return;

    setError(null);
    const userMessage: ChatMessage = { role: "user", content: trimmed };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const settings = await getApiSettingsAsync();

      let chatModel = "gpt-4o-mini";
      let apiKey = "";
      let baseUrl = "https://api.openai.com/v1";

      const providers = {
        openai: { key: settings.openai_api_key, defaultModel: "gpt-4o-mini" },
        anthropic: { key: settings.anthropic_api_key, defaultModel: "claude-3-5-sonnet-20241022" },
        google: { key: settings.google_api_key, defaultModel: "gemini-2.5-flash" },
        grok: { key: settings.grok_api_key, defaultModel: "grok-2-1212" },
        deepseek: { key: settings.deepseek_api_key, defaultModel: "deepseek-chat" },
        qwen: { key: settings.qwen_api_key, defaultModel: "qwen-max" },
      };

      const activeModelId = selectedModelId === "custom" ? customModel.trim() : selectedModelId;

      if (!activeModelId) {
        // Auto logic wrapper (now acts as a fallback if custom is empty)
        for (const [providerName, providerData] of Object.entries(providers)) {
          if (providerData.key && providerData.key.trim() !== "") {
            apiKey = providerData.key;
            chatModel = providerData.defaultModel;
            baseUrl = getBaseUrlForModel(chatModel, settings.custom_base_url);
            break;
          }
        }
        // Custom settings override if configured
        if (settings.custom_api_key && settings.custom_base_url && !apiKey) {
          apiKey = settings.custom_api_key;
          baseUrl = settings.custom_base_url;
        }
      } else {
        chatModel = activeModelId;
        const modelInfo = AVAILABLE_MODELS.find(m => m.id === selectedModelId);
        const providerName = modelInfo ? modelInfo.provider : "custom";
        
        const matchedProvider = (providers as any)[providerName];
        
        if (matchedProvider && matchedProvider.key) {
           apiKey = matchedProvider.key;
           baseUrl = getBaseUrlForModel(chatModel, settings.custom_base_url);
        } else if (settings.custom_api_key) {
           apiKey = settings.custom_api_key;
           baseUrl = settings.custom_base_url || "https://api.openai.com/v1";
        }
      }

      if (!apiKey) {
        setError(t.chat?.noApiKey || "Please configure your API key in settings first.");
        setIsLoading(false);
        return;
      }

      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await api.sendChatMessage({
        message: trimmed,
        reports: report.result.reports || {},
        ticker: report.ticker,
        analysis_date: report.analysis_date,
        history,
        model: chatModel,
        api_key: apiKey,
        base_url: baseUrl,
        language: locale as "en" | "zh-TW",
      });

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.reply },
      ]);
    } catch (err: any) {
      console.error("Chat error:", err);
      const errorMsg =
        err?.response?.data?.detail ||
        err?.message ||
        (t.chat?.error || "Failed to get response. Please try again.");
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (loadingReport) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950 flex flex-col items-center justify-center">
        <Loader2 className="h-10 w-10 animate-spin text-purple-600 mb-4" />
        <p className="text-gray-500">{t.history?.loading || "Loading..."}</p>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950 flex flex-col items-center justify-center p-6 text-center">
        <AlertCircle className="h-16 w-16 text-gray-400 mb-4" />
        <p className="text-lg text-gray-600 dark:text-gray-300 mb-6">
          Report not found.
        </p>
        <Button onClick={() => router.push("/history")}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t.history?.title || "Back to History"}
        </Button>
      </div>
    );
  }

  const contextLabel = t.chat?.allReports || "All Reports";

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 dark:from-gray-950 dark:via-purple-950/40 dark:to-gray-950">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-4 md:px-8 md:py-6 border-b border-gray-200 dark:border-gray-800 bg-white/50 dark:bg-gray-900/50 backdrop-blur-md sticky top-0 z-10 shadow-sm">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => router.push("/history")}
              className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-xl md:text-2xl font-bold text-gray-900 dark:text-white">
                <Sparkles className="h-6 w-6 text-purple-500" />
                <span>
                  {t.chat?.title || "Report Chat"} — {report.ticker}
                </span>
                <span className="hidden sm:inline text-purple-600 dark:text-purple-400 text-sm md:text-base font-normal ml-2 bg-purple-100 dark:bg-purple-900/30 px-3 py-1 rounded-full">
                  {contextLabel}
                </span>
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 ml-10">
                {t.history?.analysisDate || "Date"}: {report.analysis_date}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearChat}
                className="gap-2 text-red-600 border-red-200 hover:bg-red-50 dark:text-red-400 dark:border-red-900/50 dark:hover:bg-red-900/20"
                title={t.chat?.clearChat || "Clear chat"}
              >
                <Trash2 className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {t.chat?.clearChat || "Clear chat"}
                </span>
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 space-y-6">
        <div className="max-w-5xl mx-auto">
          {/* Empty state */}
          {messages.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center min-h-[50vh] text-center text-gray-400 dark:text-gray-500 gap-6">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-purple-100 to-pink-100 dark:from-purple-900/30 dark:to-pink-900/30 flex items-center justify-center shadow-inner">
                <Bot className="h-10 w-10 text-purple-600 dark:text-purple-400" />
              </div>
              <div>
                <p className="text-xl font-medium text-gray-700 dark:text-gray-200">
                  {t.chat?.emptyState || "Ask any question about this analysis report"}
                </p>
                <p className="text-base mt-2 text-gray-500 dark:text-gray-400">
                  {t.chat?.emptyHint || 'e.g. "What are the main risk factors?"'}
                </p>
              </div>
              {/* Quick suggestions */}
              <div className="flex flex-wrap gap-3 mt-4 justify-center max-w-2xl px-4">
                {(locale === "zh-TW"
                  ? [
                      "主要的風險因素有哪些？",
                      "總結這份報告的重點",
                      "建議的進場策略是什麼？",
                      "看漲和看跌的觀點有何不同？",
                    ]
                  : [
                      "What are the key risk factors?",
                      "Summarize this report",
                      "What's the recommended entry strategy?",
                      "How do bull and bear views differ?",
                    ]
                ).map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setInput(suggestion);
                      setTimeout(() => inputRef.current?.focus(), 50);
                    }}
                    className="px-4 py-2 text-sm rounded-full border border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 bg-white/50 dark:bg-gray-800/50 hover:bg-purple-50 dark:hover:bg-purple-900/50 transition-all duration-200 shadow-sm hover:shadow"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message list */}
          <div className="space-y-6 pb-4">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-4 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
              >
                {/* Avatar */}
                <div
                  className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-white text-sm shadow-sm ${
                    msg.role === "user"
                      ? "bg-gradient-to-br from-blue-500 to-cyan-500"
                      : "bg-gradient-to-br from-purple-600 to-pink-600"
                  }`}
                >
                  {msg.role === "user" ? (
                    <User className="h-5 w-5" />
                  ) : (
                    <Bot className="h-5 w-5" />
                  )}
                </div>

                <div
                  className={`max-w-[100%] md:max-w-[85%] rounded-2xl px-5 py-4 text-base leading-relaxed shadow-sm overflow-x-auto ${
                    msg.role === "user"
                      ? "bg-gradient-to-r from-blue-500 to-cyan-500 text-white rounded-tr-sm"
                      : "bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 text-gray-800 dark:text-gray-200 rounded-tl-sm"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm md:prose-base dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 prose-table:border-collapse prose-table:w-full prose-td:border prose-td:border-gray-300 dark:prose-td:border-gray-600 prose-td:p-2 prose-th:border prose-th:border-gray-300 dark:prose-th:border-gray-600 prose-th:p-2 prose-th:bg-gray-100 dark:prose-th:bg-gray-800">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  )}
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center bg-gradient-to-br from-purple-600 to-pink-600 text-white shadow-sm">
                  <Bot className="h-5 w-5 text-white animate-pulse" />
                </div>
                <div className="bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-3 text-base text-gray-500 dark:text-gray-400 font-medium">
                    <Loader2 className="h-5 w-5 animate-spin text-purple-500" />
                    <span>{t.chat?.thinking || "Thinking..."}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="flex items-start gap-3 text-red-600 dark:text-red-400 text-base bg-red-50 border border-red-100 dark:border-red-900 dark:bg-red-950/30 rounded-xl p-4 shadow-sm">
                <AlertCircle className="h-5 w-5 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      {/* Input Bar */}
      <div className="flex-shrink-0 border-t border-gray-200 dark:border-gray-800 px-4 py-4 md:px-8 md:py-6 bg-white/80 dark:bg-gray-900/80 backdrop-blur-lg">
        <div className="max-w-4xl mx-auto flex flex-col gap-3">
          {/* Model Selector */}
          <div className="flex flex-wrap items-center gap-2">
            <Select value={selectedModelId} onValueChange={setSelectedModelId}>
              <SelectTrigger className="w-fit min-w-[200px] h-9 text-sm bg-white dark:bg-gray-800 rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 shadow-sm transition-colors">
                <SelectValue placeholder="選擇模型" />
              </SelectTrigger>
              <SelectContent className="max-h-[300px]">
                {AVAILABLE_MODELS.map((m) => (
                  <SelectItem key={m.id} value={m.id} className="cursor-pointer text-xs sm:text-sm">
                    <div className="flex items-center gap-2">
                      {m.logo && <Image src={m.logo} alt={m.provider} width={16} height={16} className="shrink-0" />}
                      <span>{m.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {selectedModelId === "custom" && (
              <Input
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                placeholder="輸入模型名稱 (e.g. gpt-4)"
                className="h-8 w-[180px] text-xs rounded-full border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800"
              />
            )}
          </div>

          {/* Text Input */}
          <div className="flex gap-3 md:gap-4">
            <Input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t.chat?.placeholder || "Ask about this report..."}
              disabled={isLoading}
              className="flex-1 text-base rounded-full border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 focus-visible:ring-purple-500 h-12 md:h-14 px-6 shadow-sm"
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              size="icon"
              className="rounded-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 h-12 w-12 md:h-14 md:w-14 flex-shrink-0 shadow-md hover:shadow-lg transition-all"
            >
              {isLoading ? (
                <Loader2 className="h-6 w-6 animate-spin text-white" />
              ) : (
                <Send className="h-6 w-6 text-white ml-1" />
              )}
            </Button>
          </div>
        </div>
        <div className="max-w-4xl mx-auto mt-2 text-center">
          <p className="text-xs text-gray-400 dark:text-gray-500">
            LLM can make mistakes. Please verify important information.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function HistoryChatPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gradient-to-br from-purple-50/30 via-pink-50/20 to-purple-50/30 flex flex-col items-center justify-center">
          <Loader2 className="h-10 w-10 animate-spin text-purple-600 mb-4" />
          <p className="text-gray-500">Loading chat...</p>
        </div>
      }
    >
      <HistoryChatContent />
    </Suspense>
  );
}
