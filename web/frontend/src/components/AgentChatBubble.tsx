import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, Loader2, ChevronDown, Plus, Maximize2, Trash2, History } from "lucide-react";
import { useChatStore } from "../stores/useChatStore";
import { fetchTools, executeTool } from "../lib/agentTools";
import { LargeChatScreen } from "./LargeChatScreen";

function formatDateTime(timestamp: number): string {
  return new Date(timestamp).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
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

function extractResponseText(response: unknown): string {
  if (typeof response === "string") return response;
  if (response && typeof response === "object") {
    const record = response as Record<string, unknown>;
    const candidates = [
      record.text,
      record.message,
      record.content,
      Array.isArray(record.choices)
        ? (record.choices[0] as Record<string, unknown> | undefined)?.message
        : null,
    ];
    for (const candidate of candidates) {
      if (typeof candidate === "string") return candidate;
      if (candidate && typeof candidate === "object") {
        const content = (candidate as Record<string, unknown>).content;
        if (typeof content === "string") return content;
      }
    }
  }
  return JSON.stringify(response, null, 2);
}

const API_BASE = "/api/chat";

export function AgentChatBubble() {
  const { messages, isOpen, isLoading, addMessage, updateMessage, toggleChat, setLoading, clearMessages, sessions, activeSessionId, createSession, deleteSession, switchSession } = useChatStore();
  const [input, setInput] = useState("");
  const [largeScreenOpen, setLargeScreenOpen] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    addMessage({ role: "user", content: trimmed });
    setInput("");
    setLoading(true);

    try {
      const tools = await fetchTools();
      const backendTools = tools.map(tool => {
        const params = tool.parameters || {};
        const required: string[] = [];
        const properties: Record<string, unknown> = {};
        for (const [key, val] of Object.entries(params)) {
          properties[key] = val;
          if (tool.path.includes(`{${key}}`)) {
            required.push(key);
          }
        }
        const backendTool = {
          type: "function",
          function: {
            name: tool.name,
            description: tool.description,
            parameters: {
              type: "object",
              properties,
              ...(required.length > 0 ? { required } : {}),
            },
          },
        };
        return backendTool;
      });

      const toApiMessage = (m: typeof messages[0]) => {
        const base: Record<string, unknown> = { role: m.role, content: m.content };
        if (m.role === "assistant" && m.toolCalls) {
          base.tool_calls = m.toolCalls.map(tc => ({
            id: tc.id, type: "function",
            function: { name: tc.name, arguments: JSON.stringify(tc.arguments) },
          }));
        }
        if (m.role === "tool") {
          base.tool_call_id = m.toolCallId || (m as any).tool_call_id || "";
        }
        return base;
      };

      let conversationHistory: Record<string, unknown>[] = [
        { role: "system", content: getSystemPrompt(tools) },
        ...messages.filter(m => m.content && m.content.trim()).map(toApiMessage),
        { role: "user", content: trimmed },
      ];

      const assistantMsgId = addMessage({ role: "assistant", content: "", isStreaming: true });
      let currentMsgId = assistantMsgId;
      let hadExecutedTools = false;

      // Loop until AI stops making tool calls (safety limit of 20 rounds)
      for (let round = 0; round < 20; round++) {
        let response: Response;
        try {
          response = await fetch(`${API_BASE}/completions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              messages: conversationHistory,
              tools: backendTools,
              stream: true,
            }),
          });
        } catch (fetchErr) {
          updateMessage(currentMsgId, {
            content: `Network error: ${fetchErr instanceof Error ? fetchErr.message : String(fetchErr)}`,
            isStreaming: false,
          });
          break;
        }

        if (!response.ok) {
          let errText = "Chat completion failed";
          try { errText = (await response.json()).error || errText; } catch {}
          updateMessage(currentMsgId, { content: `Error: ${errText}`, isStreaming: false });
          break;
        }

        // Process SSE stream
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let fullResponse = "";
        let toolCallsFromResponse: Array<{ id: string; type: string; function: { name: string; arguments: string } }> = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const data = line.slice(6);
            if (data === "[DONE]") break;

            try {
              const parsed = JSON.parse(data);
              if (parsed.type === "text" && parsed.text) {
                fullResponse += parsed.text;
                updateMessage(currentMsgId, { content: fullResponse });
              }
              if (parsed.type === "tool_calls" && parsed.tool_calls) {
                toolCallsFromResponse = parsed.tool_calls;
                try {
                  updateMessage(currentMsgId, {
                    content: fullResponse,
                    toolCalls: toolCallsFromResponse.map(tc => ({
                      id: tc.id, name: tc.function.name,
                      arguments: (() => { try { return JSON.parse(tc.function.arguments || "{}"); } catch { return {}; } })(),
                    })),
                  });
                } catch {}
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
            } catch {}
          }
        }

        // Fallback: parse text-based tool calls if LLM outputs them as text
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

        // Also parse ```tool_call name="..." parameters="..." ``` format
        if (toolCallsFromResponse.length === 0 && fullResponse) {
          const blockPattern = /```tool_call\s*([\s\S]*?)\s*```/g;
          const blockMatches = [...fullResponse.matchAll(blockPattern)];
          if (blockMatches.length > 0) {
            for (const match of blockMatches) {
              const block = match[1];
              const nameMatch = block.match(/name="([^"]*)"/);
              const paramsMatch = block.match(/parameters="({.*?})"/);
              if (nameMatch) {
                const name = nameMatch[1];
                let params = {};
                try { params = JSON.parse(paramsMatch?.[1] || "{}"); } catch {}
                toolCallsFromResponse.push({
                  id: `call_text_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
                  type: "function",
                  function: { name, arguments: JSON.stringify(params) },
                });
              }
            }
            fullResponse = fullResponse.replace(blockPattern, "").trim();
          }
        }

        updateMessage(currentMsgId, { content: fullResponse });

        // If no tool calls, we're done
        if (toolCallsFromResponse.length === 0) {
          if (!fullResponse || !fullResponse.trim()) {
            if (hadExecutedTools) {
              updateMessage(currentMsgId, { isStreaming: false });
            } else {
              updateMessage(currentMsgId, { content: "No response", isStreaming: false });
            }
          } else {
            updateMessage(currentMsgId, { isStreaming: false });
          }
          break;
        }

        // Execute tool calls
        updateMessage(currentMsgId, { content: fullResponse || "Processing..." });
        const toolResults: Array<{ role: string; tool_call_id: string; content: string }> = [];

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
          const resultStr = JSON.stringify(result);
          addMessage({
            role: "tool",
            content: `Called ${call.function.name}: ${resultStr.slice(0, 500)}`,
            toolCallId: call.id,
          });
          toolResults.push({
            role: "tool",
            tool_call_id: call.id,
            content: resultStr.slice(0, 2000),
          });
        }

        hadExecutedTools = true;

        // Build next conversation history - ensure correct format
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

        // Create new message for next round
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
    }
  };

  const openLargeScreen = () => {
    toggleChat();
    setLargeScreenOpen(true);
  };

  return (
    <>
      {largeScreenOpen && (
        <LargeChatScreen onClose={() => setLargeScreenOpen(false)} />
      )}
    <div className="fixed bottom-4 left-4 z-50">
      <button
        onClick={toggleChat}
        className="h-14 w-14 rounded-full bg-sky-600 text-white shadow-lg hover:bg-sky-700 transition-colors flex items-center justify-center"
        aria-label={isOpen ? "Close chat" : "Open chat"}
      >
        {isOpen ? <X className="h-6 w-6" /> : <MessageSquare className="h-6 w-6" />}
      </button>

      {isOpen && (
        <div className="absolute bottom-16 left-0 w-96 h-[500px] bg-slate-900 rounded-lg shadow-2xl border border-slate-700 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-sky-400" />
              <span className="text-sm font-semibold text-slate-200">Trading Assistant</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={openLargeScreen}
                className="text-slate-400 hover:text-slate-200"
                aria-label="Open full screen"
                title="Open full screen"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setShowSessions(!showSessions); }}
                className={`text-slate-400 hover:text-slate-200 ${showSessions ? "text-sky-400" : ""}`}
                aria-label="Session history"
                title="Session history"
              >
                <History className="h-4 w-4" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); clearMessages(); }}
                className="text-slate-400 hover:text-slate-200"
                aria-label="New chat"
              >
                <Plus className="h-4 w-4" />
              </button>
              <button
                onClick={toggleChat}
                className="text-slate-400 hover:text-slate-200"
                aria-label="Close chat"
              >
                <ChevronDown className="h-4 w-4" />
              </button>
            </div>
          </div>

          {showSessions && (
            <div className="max-h-40 overflow-y-auto border-b border-slate-700">
              {Object.values(sessions).sort((a, b) => b.updatedAt - a.updatedAt).map((session) => (
                <div
                  key={session.id}
                  className={`flex items-center justify-between px-3 py-2 text-xs cursor-pointer hover:bg-slate-800/50 ${
                    session.id === activeSessionId ? "bg-sky-600/20 text-sky-300" : "text-slate-400"
                  }`}
                  onClick={() => { switchSession(session.id); setShowSessions(false); }}
                >
                  <span className="truncate flex-1">{session.name}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                    className="ml-2 text-slate-500 hover:text-red-400 shrink-0"
                    aria-label="Delete session"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-slate-500 text-sm py-8">
                Ask me anything about your trading data.
              </div>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-sky-600/30 text-slate-200"
                      : msg.role === "tool"
                      ? "bg-slate-800 text-slate-400 font-mono text-xs"
                      : "bg-slate-800/60 text-slate-300"
                  }`}
                >
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
                  <div className={`text-[10px] mt-1 opacity-50 ${msg.role === "user" ? "text-right" : "text-left"}`}>
                    {formatDateTime(msg.timestamp)}
                  </div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSubmit} className="p-3 border-t border-slate-700">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your trading data..."
                className="flex-1 bg-slate-800 text-slate-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-sky-500/50"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="p-2 rounded-lg bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label="Send message"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
    </>
  );
}
