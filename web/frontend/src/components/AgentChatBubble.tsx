import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, Loader2, ChevronDown } from "lucide-react";
import { useChatStore } from "../stores/useChatStore";
import { fetchTools, executeTool } from "../lib/agentTools";

const MODEL = "moonshotai/kimi-k2.6";
const SYSTEM_PROMPT = `You are a trading assistant with access to market data and analysis tools.

Your available tools are auto-generated from the backend API. You have access to:
- Watchlist management (get, add, remove, reorder tickers)
- Analysis runs (start, get status, cancel, resume)
- Price data (current prices, history)
- Indicators (get, add, update, remove, check)
- Background jobs (start, list, cancel, pause, resume)
- Configuration (get, update settings)
- Ticker accuracy agent (status, control, leaderboard)

When you need data, call the appropriate tool.
When asked to perform actions, use the action tools.
Always explain what you're doing and show results.

The tool list is dynamically generated from the backend API schema.`;

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

export function AgentChatBubble() {
  const { messages, isOpen, isLoading, addMessage, updateMessage, toggleChat, setLoading } = useChatStore();
  const [input, setInput] = useState("");
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

    if (!window.puter?.ai?.chat) {
      addMessage({ role: "assistant", content: "Puter AI is still loading. Please try again." });
      return;
    }

    addMessage({ role: "user", content: trimmed });
    setInput("");
    setLoading(true);

    try {
      const tools = await fetchTools();
      const puterTools = tools.map(tool => ({
        type: "function",
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters,
        },
      }));

      const conversationHistory = [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages
          .filter(m => m.content && m.content.trim())
          .map(m => ({ role: m.role, content: m.content })),
        { role: "user", content: trimmed },
      ];

      const assistantMsgId = addMessage({ role: "assistant", content: "", isStreaming: true });

      const response = await window.puter.ai.chat(conversationHistory, {
        model: MODEL,
        tools: puterTools,
        stream: false,
      });

      // Handle non-streaming response
      const extracted = extractResponseText(response);
      updateMessage(assistantMsgId, { content: extracted });

      // Check for tool calls in non-streaming response
      const responseObj = response as Record<string, unknown>;
      const message = responseObj?.message as Record<string, unknown> | undefined;
      if (message?.tool_calls) {
        const toolCalls = message.tool_calls as Array<{ id: string; function: { name: string; arguments: string } }>;
        for (const call of toolCalls) {
          const args = typeof call.function.arguments === "string" 
            ? JSON.parse(call.function.arguments) 
            : call.function.arguments;
          const result = await executeTool(call.function.name, args);
          addMessage({
            role: "tool",
            content: JSON.stringify(result),
          });
        }
      }

      updateMessage(assistantMsgId, { isStreaming: false });
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

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <button
        onClick={toggleChat}
        className="h-14 w-14 rounded-full bg-sky-600 text-white shadow-lg hover:bg-sky-700 transition-colors flex items-center justify-center"
        aria-label={isOpen ? "Close chat" : "Open chat"}
      >
        {isOpen ? <X className="h-6 w-6" /> : <MessageSquare className="h-6 w-6" />}
      </button>

      {isOpen && (
        <div className="absolute bottom-16 right-0 w-96 h-[500px] bg-slate-900 rounded-lg shadow-2xl border border-slate-700 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-sky-400" />
              <span className="text-sm font-semibold text-slate-200">Trading Assistant</span>
            </div>
            <button
              onClick={toggleChat}
              className="text-slate-400 hover:text-slate-200"
              aria-label="Close chat"
            >
              <ChevronDown className="h-4 w-4" />
            </button>
          </div>

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
                  {msg.isStreaming && <span className="animate-pulse ml-1">|</span>}
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
  );
}
