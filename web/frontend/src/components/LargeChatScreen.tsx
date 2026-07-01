import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, Loader2, Plus, Minimize2, Trash2, MessageCircle, Pencil } from "lucide-react";
import { useChatStore } from "../stores/useChatStore";
import { fetchTools, executeTool, setCurrentUserMessage, clearCurrentUserMessage, prepopulateToolContext, setConversationHistory } from "../lib/agentTools";

function formatDateTime(timestamp: number): string {
  return new Date(timestamp).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatShortDate(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;
  if (diff < 60000) return "Just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return new Date(timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function getSystemPrompt(tools: Array<{ name: string; description: string }>): string {
  const now = new Date();
  const dateTimeStr = now.toLocaleString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZoneName: "short",
  });

  const toolList = tools.map(t => `- ${t.name}: ${t.description}`).join("\n");

  return `You are a knowledgeable trading assistant with access to real-time market data and analysis tools.

Current date and time: ${dateTimeStr}

You MUST always answer the user's financial questions by actually using your available tools to fetch real data. Never refuse to answer or say you can't provide advice. When a user asks about a ticker (like SPY, AAPL, QQQ), immediately call the appropriate tool to get current data.

Your available tools (auto-generated from the backend API):
${toolList}

When asked about whether to buy/sell/enter a position:
1. Call get_prices or get_tickers__ticker__history to get current/recent data
2. Call get_indicators to check market conditions
3. Provide a direct answer based on the actual data, not generic disclaimers

Always use tools to get real data when available. Analyze the data and give specific, data-driven answers.

The tool list is dynamically generated from the backend API schema.`;
}

const API_BASE = "/api/chat";

interface Props {
  onClose: () => void;
}

export function LargeChatScreen({ onClose }: Props) {
  const { messages, isLoading, addMessage, updateMessage, setLoading, sessions, activeSessionId, createSession, deleteSession, switchSession, editingMessageId, setEditingMessage, deleteMessagesAfter } = useChatStore();
  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeSessionId]);

  useEffect(() => {
    if (!editingMessageId) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setEditingMessage(null);
        setInput("");
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [editingMessageId, setEditingMessage]);

  useEffect(() => {
    if (!editingMessageId) return;
    const msg = messages.find(m => m.id === editingMessageId);
    if (msg && msg.role === "user") {
      setInput(msg.content);
      inputRef.current?.focus();
    }
  }, [editingMessageId, messages]);

  const sessionList = Object.values(sessions).sort((a, b) => b.updatedAt - a.updatedAt);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const editingId = editingMessageId;
    if (editingId) {
      deleteMessagesAfter(editingId);
      setEditingMessage(null);
    }

    addMessage({ role: "user", content: trimmed });
    setInput("");
    setLoading(true);

    try {
      const tools = await fetchTools();

      // Pre-populate tool context from the most recent ticker mentioned (scan in reverse)
      for (let i = messages.length - 1; i >= 0; i--) {
        const msg = messages[i];
        if (msg.role !== "user") continue;
        const tickerMatch = msg.content.match(/\$?([A-Z]{2,5})\b/g);
        if (tickerMatch) {
          const ticker = tickerMatch[0].startsWith("$") ? tickerMatch[0].slice(1) : tickerMatch[0];
          if (ticker.length >= 2) {
            prepopulateToolContext({ ticker });
            break;
          }
        }
      }

      // Set full conversation history for context extraction
      setConversationHistory(messages.map(m => ({ role: m.role, content: m.content })));

      const backendTools = tools.map(tool => ({
        type: "function",
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters,
        },
      }));

      const toApiMessage = (m: typeof messages[0]) => {
        const base: Record<string, unknown> = { role: m.role, content: m.content };
        if (m.role === "assistant" && m.toolCalls) {
          base.tool_calls = m.toolCalls.map(tc => ({
            id: tc.id, type: "function",
            function: { name: tc.name, arguments: JSON.stringify(tc.arguments) },
          }));
        }
        if (m.role === "tool") {
          base.tool_call_id = m.toolCallId || "";
        }
        return base;
      };

      let conversationHistory: Record<string, unknown>[] = [
        { role: "system", content: getSystemPrompt(backendTools.map(t => ({ name: t.function.name, description: t.function.description }))) },
        ...messages.filter(m => (m.content && m.content.trim()) || (m.role === "assistant" && m.toolCalls?.length > 0) || m.role === "tool").map(toApiMessage),
        { role: "user", content: trimmed },
      ];

      const assistantMsgId = addMessage({ role: "assistant", content: "", isStreaming: true });
      let currentMsgId = assistantMsgId;

      for (let round = 0; round < 50; round++) {
        const response = await fetch(`${API_BASE}/completions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: conversationHistory,
            tools: backendTools,
            stream: true,
          }),
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.error || "Chat completion failed");
        }

        // Process SSE stream
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let fullResponse = "";
        let toolCallsFromResponse: Array<{ id: string; type: string; function: { name: string; arguments: string } }> = [];

        let streamDone = false;
        while (!streamDone) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6);
            if (data === "[DONE]") { streamDone = true; break; }

            try {
              const parsed = JSON.parse(data);
              if (parsed.type === "text" && parsed.text) {
                fullResponse += parsed.text;
                updateMessage(currentMsgId, { content: fullResponse });
              }
              if (parsed.type === "tool_calls" && parsed.tool_calls) {
                toolCallsFromResponse = parsed.tool_calls;
                updateMessage(currentMsgId, {
                  content: fullResponse,
                  toolCalls: toolCallsFromResponse.map(tc => ({
                    id: tc.id, name: tc.function.name,
                    arguments: JSON.parse(tc.function.arguments || "{}"),
                  })),
                });
              }
              if (parsed.type === "error") {
                throw new Error(parsed.error || "Stream error");
              }
              if (parsed.type === "done") {
                if (parsed.tool_calls?.length > 0) {
                  toolCallsFromResponse = parsed.tool_calls;
                }
                if (parsed.content !== undefined && !fullResponse) {
                  fullResponse = parsed.content;
                  updateMessage(currentMsgId, { content: fullResponse });
                }
              }
            } catch (parseErr) {
              console.warn("LargeChatScreen: failed to parse SSE event:", data, parseErr);
            }
          }
        }

        // Fallback: parse text-based tool calls
        if (toolCallsFromResponse.length === 0 && fullResponse) {
          const toolPattern = /<tool_call>\s*<name>(.*?)<\/name>\s*<parameters>(.*?)<\/parameters>\s*<\/tool_call>/gs;
          const matches = [...fullResponse.matchAll(toolPattern)];
          if (matches.length > 0) {
            for (const match of matches) {
              const name = match[1];
              let params = {};
              try { params = JSON.parse(match[2]); } catch {}
              toolCallsFromResponse.push({
                id: `call_text_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                type: "function",
                function: { name, arguments: JSON.stringify(params) },
              });
            }
            fullResponse = fullResponse.replace(toolPattern, "").trim();
          }
        }

        updateMessage(currentMsgId, { content: fullResponse });

        if (toolCallsFromResponse.length === 0) {
          if (!fullResponse) {
            updateMessage(currentMsgId, { content: "No response", isStreaming: false });
          } else {
            updateMessage(currentMsgId, { isStreaming: false });
          }
          break;
        }

        updateMessage(currentMsgId, { content: fullResponse || "Processing..." });
        const toolResults: Array<{ role: string; tool_call_id: string; content: string }> = [];

        setCurrentUserMessage(trimmed);

        for (const call of toolCallsFromResponse) {
          let args: Record<string, unknown> = {};
          try {
            const raw = call.function.arguments;
            args = typeof raw === "string" ? (raw ? JSON.parse(raw) : {}) : (raw || {});
          } catch {
            args = {};
          }
          let result: unknown;
          try {
            result = await executeTool(call.function.name, args);
          } catch (toolErr) {
            result = { error: toolErr instanceof Error ? toolErr.message : String(toolErr) };
          }
          addMessage({
            role: "tool",
            content: `Called ${call.function.name}: ${JSON.stringify(result).slice(0, 500)}`,
            toolCallId: call.id,
          });
          toolResults.push({
            role: "tool",
            tool_call_id: call.id,
            content: JSON.stringify(result),
          });
        }

        const assistantToolMsg = {
          role: "assistant" as const,
          content: fullResponse || "",
          tool_calls: toolCallsFromResponse.map((tc: { id: string; function: { name: string; arguments: string } }) => ({
            id: tc.id,
            type: "function" as const,
            function: { name: tc.function.name, arguments: tc.function.arguments },
          })),
        };

        conversationHistory = [...conversationHistory, assistantToolMsg, ...toolResults];

        currentMsgId = addMessage({ role: "assistant", content: "", isStreaming: true });
      }
    } catch (error) {
      console.error("AgentChat error:", error);
      let errorMessage: string;
      if (error instanceof Error) {
        errorMessage = `${error.message}\n${error.stack || ""}`;
      } else if (typeof error === "object" && error !== null) {
        errorMessage = JSON.stringify(error, null, 2);
      } else {
        errorMessage = String(error);
      }
      addMessage({
        role: "assistant",
        content: `Error: ${errorMessage}`
      });
    } finally {
      setLoading(false);
      clearCurrentUserMessage();
    }
  };

  return (
    <div className="fixed inset-0 z-[100] bg-slate-950/95 flex">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? "w-72" : "w-0"} transition-all duration-200 flex-shrink-0 border-r border-slate-700/50 bg-slate-900/50 flex flex-col overflow-hidden`}>
        <div className="flex items-center justify-between px-4 py-4 border-b border-slate-700/50">
          <span className="text-sm font-semibold text-slate-300">Conversations</span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="text-slate-500 hover:text-slate-300 p-1 rounded hover:bg-slate-800 transition-colors"
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-2">
          <button
            onClick={createSession}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-sky-400 hover:bg-sky-500/10 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
          {sessionList.map((session) => (
            <div
              key={session.id}
              className={`group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
                session.id === activeSessionId
                  ? "bg-sky-500/15 text-sky-300"
                  : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-300"
              }`}
              onClick={() => switchSession(session.id)}
            >
              <MessageCircle className="h-4 w-4 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm truncate">{session.name}</div>
                <div className="text-[10px] opacity-50">{formatShortDate(session.updatedAt)}</div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                aria-label="Delete conversation"
                title="Delete conversation"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          {sessionList.length === 0 && (
            <div className="text-center text-slate-600 text-xs py-8">
              No conversations yet
            </div>
          )}
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-900">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-800 transition-colors"
                aria-label="Open sidebar"
                title="Show conversations"
              >
                <MessageCircle className="h-4 w-4" />
              </button>
            )}
            <MessageSquare className="h-5 w-5 text-sky-400" />
            <span className="text-base font-semibold text-slate-200">Trading Assistant</span>
            {activeSessionId && sessions[activeSessionId] && (
              <span className="text-xs text-slate-500 hidden sm:inline truncate max-w-[200px]">
                — {sessions[activeSessionId].name}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={createSession}
              className="text-slate-400 hover:text-slate-200 p-2 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="New chat"
              title="New chat"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 p-2 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close full screen"
              title="Minimize"
            >
              <Minimize2 className="h-4 w-4" />
            </button>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 p-2 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close chat"
              title="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4 max-w-4xl mx-auto w-full">
          {messages.length === 0 && (
            <div className="text-center text-slate-500 text-sm py-12">
              Ask me anything about your trading data.
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[75%] rounded-xl px-4 py-3 text-sm relative ${
                  msg.role === "user"
                    ? "bg-sky-600/30 text-slate-200 pr-8"
                    : msg.role === "tool"
                    ? "bg-slate-800 text-slate-400 font-mono text-xs"
                    : "bg-slate-800/60 text-slate-300"
                }`}
              >
                {msg.role === "user" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setEditingMessage(msg.id); }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded text-slate-400 hover:text-sky-400 hover:bg-slate-800/50 transition-colors"
                    aria-label="Edit message"
                    title="Edit message"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                )}
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="mb-2 text-xs text-sky-400">
                    Calling: {msg.toolCalls.map(tc => tc.name).join(", ")}
                  </div>
                )}
                {msg.content}
                {msg.isStreaming && !msg.content && (
                  <span className="inline-flex gap-1 ml-1">
                    <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </span>
                )}
                <div className={`text-[10px] mt-2 opacity-50 ${msg.role === "user" ? "text-right" : "text-left"}`}>
                  {formatDateTime(msg.timestamp)}
                </div>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="p-6 border-t border-slate-700 bg-slate-900">
          {editingMessageId && (
            <div className="flex items-center justify-between max-w-4xl mx-auto mb-2">
              <span className="text-xs text-sky-400">Editing message</span>
              <button
                type="button"
                onClick={() => { setEditingMessage(null); setInput(""); }}
                className="text-xs text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
            </div>
          )}
          <div className="flex items-center gap-3 max-w-4xl mx-auto">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={editingMessageId ? "Edit your message..." : "Ask about your trading data..."}
              className="flex-1 bg-slate-800 text-slate-200 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-sky-500/50"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="p-3 rounded-xl bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              aria-label={editingMessageId ? "Resend message" : "Send message"}
            >
              {isLoading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : editingMessageId ? (
                <span className="text-sm font-medium">Resend</span>
              ) : (
                <Send className="h-5 w-5" />
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}