import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, Loader2, ChevronDown, Plus, Maximize2, Trash2, History, ChevronRight, CheckCircle2, XCircle, AlertCircle, ArrowRight, Pencil } from "lucide-react";
import { useChatStore, type Message } from "../stores/useChatStore";
import { fetchTools, executeTool, setRenamedToolMap, setCurrentUserMessage, clearCurrentUserMessage, prepopulateToolContext, setConversationHistory, type ToolResult } from "../lib/agentTools";
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

## TOOL CALLING RULES (CRITICAL)
When you call a tool, you MUST provide ALL required parameters in the arguments JSON object.

**Example of a CORRECT tool call for get_ticker_history:**
{"name": "get_ticker_history", "arguments": {"ticker": "SPY", "range": "1mo"}}

**Example of an INCORRECT tool call (missing ticker):**
{"name": "get_ticker_history", "arguments": {}}  <- THIS WILL FAIL

If user asks about SPY, you MUST call get_ticker_history with ticker="SPY" in the arguments, like:
{"name": "get_ticker_history", "arguments": {"ticker": "SPY"}}

DO NOT call tools without required parameters. Every parameter marked as REQUIRED must be provided.

Your available tools:
${toolList}

Always actually call the tools via tool_calls function - do not just describe what you would call.`;
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

interface ToolCallMeta {
  toolName: string;
  args: Record<string, unknown>;
  result: ToolResult;
  timestamp: number;
}

interface ToolResultDisplay extends Omit<Message, "role"> {
  role: "tool";
  toolMeta?: ToolCallMeta;
}

function ToolCallCard({ meta }: { meta: ToolCallMeta }) {
  const [expanded, setExpanded] = useState(false);
  const { toolName, args, result } = meta;
  const isSuccess = result.success;

  return (
    <div className={`rounded-lg border overflow-hidden mb-2 transition-all ${isSuccess ? "border-emerald-500/30 bg-emerald-500/5" : "border-red-500/30 bg-red-500/5"}`}>
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-slate-700/30"
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight className={`h-3 w-3 transition-transform ${expanded ? "rotate-90" : ""} ${isSuccess ? "text-emerald-400" : "text-red-400"}`} />
        {isSuccess ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
        ) : (
          <XCircle className="h-4 w-4 text-red-400" />
        )}
        <span className={`font-semibold text-sm ${isSuccess ? "text-emerald-300" : "text-red-300"}`}>
          {toolName}
        </span>
        {Object.keys(args).length > 0 && (
          <span className="text-xs text-slate-400">
            ({Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})
          </span>
        )}
      </div>

      {expanded && (
        <div className="px-3 py-2 border-t border-slate-700/50 text-xs font-mono">
          {isSuccess && result.data && (
            <div className="mb-2">
              <div className="text-slate-400 mb-1">Result Preview:</div>
              <pre className="text-emerald-300 bg-slate-900/50 p-2 rounded overflow-x-auto max-h-32">
                {JSON.stringify(result.data, null, 2).slice(0, 500)}
                {JSON.stringify(result.data).length > 500 && "..."}
              </pre>
            </div>
          )}

          {!isSuccess && result.error && (
            <div className="mb-2">
              <div className="text-red-400 mb-1 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" /> Error:
              </div>
              <div className="text-red-300 bg-red-900/20 p-2 rounded">
                {result.error}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function parseToolContent(content: string): { toolName: string; result: unknown } | null {
  const match = content.match(/^Called (\w+):\s*(.+)/);
  if (match) {
    try {
      return { toolName: match[1], result: JSON.parse(match[2]) };
    } catch {
      return { toolName: match[1], result: match[2] };
    }
  }
  return null;
}

function MessageBubble({ msg }: { msg: Message }) {
  const { setEditingMessage } = useChatStore();
  const isUser = msg.role === "user";
  const isTool = msg.role === "tool";
  const isAssistant = msg.role === "assistant";

  if (isTool) {
    const parsed = parseToolContent(msg.content);
    const toolMeta: ToolCallMeta | undefined = parsed ? {
      toolName: parsed.toolName,
      args: {},
      result: typeof parsed.result === "object" ? parsed.result as ToolResult : { success: true, data: parsed.result },
      timestamp: msg.timestamp,
    } : undefined;

    return (
      <div className="bg-slate-800/80 rounded-lg px-3 py-2 text-sm border border-slate-700">
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div className="mb-2 text-xs text-sky-400 flex items-center gap-2">
            <ArrowRight className="h-3 w-3" />
            <span>Calling: {msg.toolCalls.map(tc => tc.name).join(", ")}</span>
          </div>
        )}
        {toolMeta ? (
          <ToolCallCard meta={toolMeta} />
        ) : (
          <div className="text-slate-400 font-mono text-xs whitespace-pre-wrap break-all">
            {msg.content.slice(0, 300)}
            {msg.content.length > 300 && "..."}
          </div>
        )}
        <div className="text-[10px] text-slate-500 mt-1">
          {formatDateTime(msg.timestamp)}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`max-w-[85%] rounded-lg px-3 py-2 text-sm relative ${
        isUser
          ? "bg-sky-600/30 text-slate-200 pr-8"
          : "bg-slate-800/60 text-slate-300"
      }`}
    >
      {isUser && (
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
          <span className="font-semibold">Calling:</span> {msg.toolCalls.map(tc => tc.name).join(", ")}
        </div>
      )}
      <div className="whitespace-pre-wrap">{msg.content}</div>
      {msg.isStreaming && !msg.content && (
        <span className="inline-flex gap-1 ml-1">
          <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
        </span>
      )}
      <div className={`text-[10px] mt-1 opacity-50 ${isUser ? "text-right" : "text-left"}`}>
        {formatDateTime(msg.timestamp)}
      </div>
    </div>
  );
}

export function AgentChatBubble() {
  const { messages, isOpen, isLoading, addMessage, updateMessage, toggleChat, setLoading, clearMessages, sessions, activeSessionId, createSession, deleteSession, switchSession, editingMessageId, setEditingMessage, deleteMessagesAfter } = useChatStore();
  const [input, setInput] = useState("");
  const [largeScreenOpen, setLargeScreenOpen] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
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

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setLoading(false);
    }
  };

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

    abortControllerRef.current = new AbortController();

    try {
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

      // Set full conversation history for context extraction during tool execution
      setConversationHistory(messages.map(m => ({ role: m.role, content: m.content })));

      const TOOL_RENAME_MAP: Record<string, { name: string; description: string; originalName: string }> = {
        tickers_ticker_history: {
          name: "get_ticker_history",
          description: "REQUIRED PARAMS: ticker (string). Fetches historical price data for a stock ticker. Usage: get_ticker_history({ticker: \"SPY\", range: \"1mo\"}). Always pass ticker as a string like \"SPY\", \"AAPL\", or \"QQQ\".",
          originalName: "get_tickers_ticker_history",
        },
        tickers_ticker_runs: {
          name: "get_ticker_runs",
          description: "REQUIRED PARAMS: ticker (string). Gets analysis runs for a ticker. Usage: get_ticker_runs({ticker: \"SPY\", limit: 10}). Always pass ticker as a string.",
          originalName: "get_tickers_ticker_runs",
        },
      };

      const renamedToOriginal: Record<string, string> = {};
      for (const [, value] of Object.entries(TOOL_RENAME_MAP)) {
        renamedToOriginal[value.name] = value.originalName;
      }
      setRenamedToolMap(renamedToOriginal);

      function cleanToolName(name: string): string {
        return name.replace(/__+/g, "_").replace(/^get_/, "").replace(/_+$/, "");
      }

      const tools = await fetchTools();
      const backendTools = tools.map(tool => {
        const params = tool.parameters || {};
        const required: string[] = [];
        const properties: Record<string, unknown> = {};
        
        // First, add all params to properties and check if they're path params (required)
        for (const [key, val] of Object.entries(params)) {
          properties[key] = val;
          // Check if this param is in the path as {param}
          if (tool.path.includes(`{${key}}`)) {
            required.push(key);
          }
        }
        
        // If ticker is in path but not in params (which shouldn't happen but let's be safe)
        const pathParamMatches = tool.path.match(/\{(\w+)\}/g) || [];
        for (const placeholder of pathParamMatches) {
          const paramName = placeholder.slice(1, -1);
          if (!properties[paramName]) {
            properties[paramName] = {
              type: "string",
              description: `REQUIRED. The ${paramName} symbol (e.g. 'SPY', 'AAPL', 'QQQ').`,
            };
            required.push(paramName);
          }
        }

        const cleanedName = cleanToolName(tool.name);
        const renamed = TOOL_RENAME_MAP[cleanedName];
        const finalName = renamed ? renamed.name : cleanedName;
        const finalDesc = renamed ? renamed.description : tool.description;
        const originalName = tool.name;

        return {
          type: "function",
          function: {
            name: finalName,
            description: finalDesc,
            parameters: {
              type: "object",
              properties,
              required,
            },
          },
        };
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

      for (let round = 0; round < 50; round++) {
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
            signal: abortControllerRef.current?.signal,
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
          
          let result: ToolResult;
          try {
            result = await executeTool(call.function.name, args) as ToolResult;
          } catch (toolErr) {
            result = { success: false, error: toolErr instanceof Error ? toolErr.message : String(toolErr) };
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
        <div className="absolute bottom-16 left-0 w-[420px] h-[550px] bg-slate-900 rounded-lg shadow-2xl border border-slate-700 flex flex-col overflow-hidden">
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

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
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
                <MessageBubble msg={msg} />
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSubmit} className="p-3 border-t border-slate-700">
            {editingMessageId && (
              <div className="flex items-center justify-between px-1 mb-2">
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
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={editingMessageId ? "Edit your message..." : "Ask about your trading data..."}
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
                ) : editingMessageId ? (
                  <span className="text-xs font-medium">Resend</span>
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
              {isLoading && (
                <button
                  type="button"
                  onClick={handleStop}
                  className="p-2 rounded-lg bg-red-600 text-white hover:bg-red-700"
                  aria-label="Stop request"
                  title="Stop"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </form>
        </div>
      )}
    </div>
    </>
  );
}