"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useLanguage } from "@/contexts/LanguageContext";
import { getApiSettingsAsync } from "@/lib/storage";
import { getBaseUrlForModel, getApiKeyForModel } from "@/lib/api-helpers";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  MessageCircle,
  X,
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  AlertCircle,
} from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ReportChatProps {
  reports: any;
  ticker: string;
  analysisDate: string;
}

export function ReportChat({ reports, ticker, analysisDate }: ReportChatProps) {
  const { t, locale } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setError(null);
    const userMessage: ChatMessage = { role: "user", content: trimmed };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Get user's API settings
      const settings = await getApiSettingsAsync();

      // Determine which model/key to use (prefer quick think model)
      // We'll try to detect the model from saved settings
      // Default to the first available key
      let model = "gpt-5-mini";
      let apiKey = "";
      let baseUrl = "https://api.openai.com/v1";

      // Try each provider in order of preference
      const providers = [
        { key: settings.openai_api_key, model: "gpt-5-mini", prefix: "gpt-" },
        { key: settings.anthropic_api_key, model: "claude-sonnet-4-20250514", prefix: "claude-" },
        { key: settings.google_api_key, model: "gemini-2.5-flash", prefix: "gemini-" },
        { key: settings.grok_api_key, model: "grok-3-mini", prefix: "grok-" },
        { key: settings.deepseek_api_key, model: "deepseek-chat", prefix: "deepseek-" },
        { key: settings.qwen_api_key, model: "qwen-flash", prefix: "qwen" },
      ];

      for (const provider of providers) {
        if (provider.key && provider.key.trim() !== "") {
          apiKey = provider.key;
          model = provider.model;
          baseUrl = getBaseUrlForModel(model, settings.custom_base_url);
          break;
        }
      }

      // If custom endpoint is set, use that
      if (settings.custom_api_key && settings.custom_base_url) {
        apiKey = settings.custom_api_key;
        baseUrl = settings.custom_base_url;
      }

      if (!apiKey) {
        setError(t.chat?.noApiKey || "Please configure your API key in settings first.");
        setIsLoading(false);
        return;
      }

      // Build history from previous messages
      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await api.sendChatMessage({
        message: trimmed,
        reports,
        ticker,
        analysis_date: analysisDate,
        history,
        model,
        api_key: apiKey,
        base_url: baseUrl,
        language: locale as "en" | "zh-TW",
      });

      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: response.reply,
      };
      setMessages((prev) => [...prev, assistantMessage]);
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
  }, [input, isLoading, messages, reports, ticker, analysisDate, locale, t]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Floating Chat Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg transition-all duration-300 hover:scale-110 hover:shadow-xl hover:from-purple-700 hover:to-pink-700 animate-fade-in"
          aria-label={t.chat?.title || "Chat"}
        >
          <MessageCircle className="h-6 w-6" />
          <span className="absolute -top-1 -right-1 flex h-4 w-4">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-pink-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-4 w-4 bg-pink-500" />
          </span>
        </button>
      )}

      {/* Chat Panel */}
      {isOpen && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col w-[400px] h-[520px] rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl animate-slide-up overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" />
              <span className="font-semibold text-sm">
                {t.chat?.title || "Ask About Report"} — {ticker}
              </span>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="rounded-full p-1 hover:bg-white/20 transition-colors"
              aria-label={t.common?.close || "Close"}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            {/* Empty state */}
            {messages.length === 0 && !isLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 dark:text-gray-500 gap-3">
                <Bot className="h-10 w-10 opacity-50" />
                <div>
                  <p className="text-sm font-medium">
                    {t.chat?.emptyState || "Ask any question about this analysis report"}
                  </p>
                  <p className="text-xs mt-1 opacity-70">
                    {t.chat?.emptyHint || "e.g. \"What are the main risk factors?\""}
                  </p>
                </div>
              </div>
            )}

            {/* Message list */}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-2 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
              >
                {/* Avatar */}
                <div
                  className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-white text-xs ${
                    msg.role === "user"
                      ? "bg-gradient-to-br from-blue-500 to-cyan-500"
                      : "bg-gradient-to-br from-purple-500 to-pink-500"
                  }`}
                >
                  {msg.role === "user" ? (
                    <User className="h-3.5 w-3.5" />
                  ) : (
                    <Bot className="h-3.5 w-3.5" />
                  )}
                </div>

                {/* Bubble */}
                <div
                  className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-gradient-to-r from-blue-500 to-cyan-500 text-white rounded-tr-sm"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-tl-sm"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
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
              <div className="flex gap-2">
                <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-gradient-to-br from-purple-500 to-pink-500 text-white text-xs">
                  <Bot className="h-3.5 w-3.5" />
                </div>
                <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
                  <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>{t.chat?.thinking || "Thinking..."}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="flex items-start gap-2 text-red-500 text-xs bg-red-50 dark:bg-red-950/30 rounded-lg p-2">
                <AlertCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Bar */}
          <div className="border-t border-gray-200 dark:border-gray-700 px-3 py-3">
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t.chat?.placeholder || "Ask about this report..."}
                disabled={isLoading}
                className="flex-1 text-sm rounded-full border-gray-200 dark:border-gray-700 focus-visible:ring-purple-500"
              />
              <Button
                onClick={handleSend}
                disabled={!input.trim() || isLoading}
                size="icon"
                className="rounded-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 h-9 w-9 flex-shrink-0"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
