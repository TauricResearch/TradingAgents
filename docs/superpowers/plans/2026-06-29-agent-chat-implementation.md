# Agent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert single-message chat components into a full conversation agent with access to the backend API, plus a global floating chat bubble.

**Architecture:** Hybrid streaming approach - Puter.js AI in frontend with auto-generated tool definitions from backend API. Backend exposes `/api/chat/tools` for tool discovery and `/api/chat/proxy` for executing actions. Frontend streams AI responses and executes tool calls via proxy.

**Tech Stack:** FastAPI (Python), React, TypeScript, Zustand, Puter.js, Vite

## Global Constraints

- Free AI via Puter.js (user-pays model)
- Auto-generated tools from existing FastAPI routes (zero duplication)
- Maintain existing TickerChatBar and IndicatorRailView functionality
- Follow existing code patterns in web/frontend/src/
- Use Zustand for state management (already in project)
- TypeScript strict mode

---

## File Structure

```
web/server/
├── chat_router.py                    # NEW: /api/chat/* endpoints
└── app.py                            # MODIFY: include chat_router

web/frontend/src/
├── lib/
│   ├── agentTools.ts                 # NEW: tool fetching + proxy execution
│   └── api.ts                        # MODIFY: add chat API functions
├── stores/
│   └── useChatStore.ts               # NEW: Zustand store for chat state
├── components/
│   ├── AgentChatBubble.tsx           # NEW: floating chat bubble + panel
│   └── TickerChatBar.tsx             # MODIFY: integrate with agent
└── App.tsx                           # MODIFY: add AgentChatBubble
```

---

### Task 1: Backend - Chat Router with Tool Discovery

**Files:**
- Create: `web/server/chat_router.py`
- Modify: `web/server/app.py:1` (add import and include_router)

**Interfaces:**
- Consumes: FastAPI app instance, existing route definitions
- Produces: `GET /api/chat/tools`, `POST /api/chat/proxy`

- [ ] **Step 1: Create chat_router.py with tool discovery**

```python
# web/server/chat_router.py
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Optional
import httpx

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ProxyRequest(BaseModel):
    method: str
    path: str
    params: Optional[dict[str, Any]] = None
    body: Optional[dict[str, Any]] = None


def extract_tool_definitions(app) -> list[dict[str, Any]]:
    """Extract tool definitions from FastAPI routes."""
    tools = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            # Skip chat routes and websocket routes
            if route.path.startswith("/api/chat") or route.path.startswith("/ws"):
                continue
            
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    tool_name = route.path.replace("/api/", "").replace("/", "_").strip("_")
                    if not tool_name:
                        tool_name = "root"
                    
                    # Get description from route or generate one
                    description = ""
                    if hasattr(route, "endpoint") and route.endpoint.__doc__:
                        description = route.endpoint.__doc__.strip().split("\n")[0]
                    else:
                        description = f"Execute {method} on {route.path}"
                    
                    # Extract parameters from path
                    parameters = {}
                    import re
                    path_params = re.findall(r"\{(\w+)\}", route.path)
                    for param in path_params:
                        parameters[param] = {"type": "string", "description": f"Path parameter: {param}"}
                    
                    tools.append({
                        "name": f"{method.lower()}_{tool_name}",
                        "description": description,
                        "method": method,
                        "path": route.path,
                        "parameters": parameters,
                    })
    return tools


@router.get("/tools")
async def get_tools(request: Request):
    """Get available tool definitions auto-generated from API routes."""
    app = request.app
    tools = extract_tool_definitions(app)
    return {"tools": tools}


@router.api_route("/proxy", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_request(proxy_req: ProxyRequest, request: Request):
    """Forward requests to any backend endpoint."""
    # Build the target URL
    base_url = str(request.base_url).rstrip("/")
    target_url = f"{base_url}{proxy_req.path}"
    
    # Forward the request
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=proxy_req.method.upper(),
            url=target_url,
            params=proxy_req.params or {},
            json=proxy_req.body if proxy_req.method.upper() in ("POST", "PUT", "PATCH") else None,
            headers={"Cookie": request.headers.get("cookie", "")},
        )
    
    # Return the response
    return JSONResponse(
        content=response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
        status_code=response.status_code,
    )
```

- [ ] **Step 2: Add chat_router to app.py**

```python
# At the top of web/server/app.py, add import:
from chat_router import router as chat_router

# After creating the app, add:
app.include_router(chat_router)
```

- [ ] **Step 3: Test tool discovery endpoint**

Run: `cd web/server && python -c "from chat_router import extract_tool_definitions; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add web/server/chat_router.py web/server/app.py
git commit -m "feat: add chat router with auto-generated tool discovery and proxy endpoint"
```

---

### Task 2: Frontend - Agent Tools Library

**Files:**
- Create: `web/frontend/src/lib/agentTools.ts`

**Interfaces:**
- Consumes: Backend `/api/chat/tools` and `/api/chat/proxy` endpoints
- Produces: `fetchTools()`, `executeTool()`, `ToolDefinition` type

- [ ] **Step 1: Create agentTools.ts**

```typescript
// web/frontend/src/lib/agentTools.ts
import { base } from "./api";

export interface ToolParameter {
  type: string;
  description?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  method: string;
  path: string;
  parameters: Record<string, ToolParameter>;
}

export interface ToolResult {
  success: boolean;
  data?: unknown;
  error?: string;
}

let cachedTools: ToolDefinition[] | null = null;

/**
 * Fetch tool definitions from backend (cached after first call)
 */
export async function fetchTools(): Promise<ToolDefinition[]> {
  if (cachedTools) return cachedTools;
  
  const response = await fetch(`${base}/api/chat/tools`);
  if (!response.ok) {
    throw new Error(`Failed to fetch tools: ${response.statusText}`);
  }
  
  const data = await response.json();
  cachedTools = data.tools;
  return cachedTools;
}

/**
 * Execute a tool via the proxy endpoint
 */
export async function executeTool(
  name: string,
  params: Record<string, unknown>
): Promise<ToolResult> {
  const tools = await fetchTools();
  const tool = tools.find(t => t.name === name);
  
  if (!tool) {
    return { success: false, error: `Tool not found: ${name}` };
  }
  
  try {
    const response = await fetch(`${base}/api/chat/proxy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        method: tool.method,
        path: tool.path,
        params: tool.method === "GET" ? params : undefined,
        body: tool.method !== "GET" ? params : undefined,
      }),
    });
    
    if (!response.ok) {
      return { success: false, error: `Request failed: ${response.statusText}` };
    }
    
    const data = await response.json();
    return { success: true, data };
  } catch (error) {
    return { 
      success: false, 
      error: error instanceof Error ? error.message : "Unknown error" 
    };
  }
}

/**
 * Clear cached tools (for testing or after API changes)
 */
export function clearToolCache(): void {
  cachedTools = null;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web/frontend && npx tsc --noEmit src/lib/agentTools.ts`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/lib/agentTools.ts
git commit -m "feat: add agent tools library for fetching tool definitions and executing via proxy"
```

---

### Task 3: Frontend - Chat Store (Zustand)

**Files:**
- Create: `web/frontend/src/stores/useChatStore.ts`

**Interfaces:**
- Consumes: None (standalone store)
- Produces: `useChatStore` hook, `ChatMessage`, `ChatStore` types

- [ ] **Step 1: Create useChatStore.ts**

```typescript
// web/frontend/src/stores/useChatStore.ts
import { create } from "zustand";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  toolCallId: string;
  content: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: number;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  isStreaming?: boolean;
}

interface ChatState {
  messages: ChatMessage[];
  isOpen: boolean;
  isLoading: boolean;
  
  // Actions
  addMessage: (msg: Omit<ChatMessage, "id" | "timestamp">) => string;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  toggleChat: () => void;
  setOpen: (open: boolean) => void;
  setLoading: (loading: boolean) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isOpen: false,
  isLoading: false,
  
  addMessage: (msg) => {
    const id = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const timestamp = Date.now();
    set((state) => ({
      messages: [...state.messages, { ...msg, id, timestamp }],
    }));
    return id;
  },
  
  updateMessage: (id, updates) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === id ? { ...msg, ...updates } : msg
      ),
    }));
  },
  
  toggleChat: () => {
    set((state) => ({ isOpen: !state.isOpen }));
  },
  
  setOpen: (open) => {
    set({ isOpen: open });
  },
  
  setLoading: (loading) => {
    set({ isLoading: loading });
  },
  
  clearMessages: () => {
    set({ messages: [] });
  },
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web/frontend && npx tsc --noEmit src/stores/useChatStore.ts`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/stores/useChatStore.ts
git commit -m "feat: add Zustand chat store for conversation state management"
```

---

### Task 4: Frontend - AgentChatBubble Component

**Files:**
- Create: `web/frontend/src/components/AgentChatBubble.tsx`

**Interfaces:**
- Consumes: `useChatStore`, `fetchTools`, `executeTool`
- Produces: `<AgentChatBubble />` component

- [ ] **Step 1: Create AgentChatBubble.tsx**

```typescript
// web/frontend/src/components/AgentChatBubble.tsx
import { useState, useRef, useEffect } from "react";
import { MessageSquare, X, Send, Loader2, ChevronDown } from "lucide-react";
import { useChatStore } from "../stores/useChatStore";
import { fetchTools, executeTool } from "../lib/agentTools";

declare global {
  interface Window {
    puter?: {
      ai?: {
        chat?: (
          prompt: string | Array<{ role: string; content: string }>,
          options?: { model?: string; tools?: unknown[]; stream?: boolean }
        ) => Promise<unknown>;
      };
    };
  }
}

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

    // Add user message
    addMessage({ role: "user", content: trimmed });
    setInput("");
    setLoading(true);

    try {
      // Fetch tools
      const tools = await fetchTools();
      const puterTools = tools.map(tool => ({
        name: tool.name,
        description: tool.description,
        parameters: tool.parameters,
      }));

      // Build conversation for Puter.js
      const conversationHistory = [
        { role: "system", content: SYSTEM_PROMPT },
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: "user", content: trimmed },
      ];

      // Add placeholder for streaming response
      const assistantMsgId = addMessage({ role: "assistant", content: "", isStreaming: true });

      // Call Puter.js AI with streaming
      const response = await window.puter.ai.chat(conversationHistory, {
        model: MODEL,
        tools: puterTools,
        stream: true,
      });

      // Handle streaming response
      let fullResponse = "";
      if (response && typeof response === "object" && Symbol.asyncIterator in (response as object)) {
        for await (const chunk of response as AsyncIterable<Record<string, unknown>>) {
          if (chunk.text) {
            fullResponse += chunk.text;
            updateMessage(assistantMsgId, { content: fullResponse });
          }
          if (chunk.tool_calls) {
            // Execute tool calls
            const toolCalls = chunk.tool_calls as Array<{ id: string; name: string; arguments: Record<string, unknown> }>;
            updateMessage(assistantMsgId, { 
              toolCalls: toolCalls.map(tc => ({ id: tc.id, name: tc.name, arguments: tc.arguments }))
            });
            
            for (const call of toolCalls) {
              const result = await executeTool(call.name, call.arguments);
              // Add tool result to conversation
              addMessage({ 
                role: "tool", 
                content: JSON.stringify(result),
              });
            }
          }
        }
      } else {
        // Non-streaming response
        fullResponse = extractResponseText(response);
        updateMessage(assistantMsgId, { content: fullResponse });
      }

      updateMessage(assistantMsgId, { isStreaming: false });
    } catch (error) {
      addMessage({ 
        role: "assistant", 
        content: `Error: ${error instanceof Error ? error.message : "Unknown error"}` 
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {/* Chat Bubble Button */}
      <button
        onClick={toggleChat}
        className="h-14 w-14 rounded-full bg-sky-600 text-white shadow-lg hover:bg-sky-700 transition-colors flex items-center justify-center"
        aria-label={isOpen ? "Close chat" : "Open chat"}
      >
        {isOpen ? <X className="h-6 w-6" /> : <MessageSquare className="h-6 w-6" />}
      </button>

      {/* Chat Panel */}
      {isOpen && (
        <div className="absolute bottom-16 right-0 w-96 h-[500px] bg-slate-900 rounded-lg shadow-2xl border border-slate-700 flex flex-col overflow-hidden">
          {/* Header */}
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

          {/* Messages */}
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

          {/* Input */}
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
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web/frontend && npx tsc --noEmit src/components/AgentChatBubble.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/components/AgentChatBubble.tsx
git commit -m "feat: add AgentChatBubble component with streaming AI and tool calling"
```

---

### Task 5: Frontend - Add AgentChatBubble to App

**Files:**
- Modify: `web/frontend/src/App.tsx`

**Interfaces:**
- Consumes: `<AgentChatBubble />` component
- Produces: Updated App with floating chat bubble

- [ ] **Step 1: Add AgentChatBubble import and render**

```typescript
// In web/frontend/src/App.tsx, add import at top:
import { AgentChatBubble } from "./components/AgentChatBubble";

// Add before closing </div> or </App>:
<AgentChatBubble />
```

- [ ] **Step 2: Verify app builds**

Run: `cd web/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/App.tsx
git commit -m "feat: add floating AgentChatBubble to app layout"
```

---

### Task 6: Frontend - Update TickerChatBar to Use Agent

**Files:**
- Modify: `web/frontend/src/components/TickerChatBar.tsx`

**Interfaces:**
- Consumes: `useChatStore`, `fetchTools`, `executeTool`
- Produces: Updated TickerChatBar with agent capabilities

- [ ] **Step 1: Update TickerChatBar to use agent store and tools**

Replace the entire file content with:

```typescript
// web/frontend/src/components/TickerChatBar.tsx
import { useMemo, useRef, useState } from "react";
import { Loader2, MessageSquare, Send, X } from "lucide-react";
import type { RunDetail } from "../lib/api";
import type { WsEvent } from "../lib/events";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import { useStageReports } from "./LiveEventStream";
import { useChatStore } from "../stores/useChatStore";
import { fetchTools, executeTool } from "../lib/agentTools";

declare global {
  interface Window {
    puter?: {
      ai?: {
        chat?: (
          prompt: string | Array<{ role: string; content: string }>,
          options?: { model?: string; tools?: unknown[]; stream?: boolean }
        ) => Promise<unknown>;
      };
    };
  }
}

interface Props {
  ticker: string;
  price: Record<string, unknown>;
  run?: RunDetail | null;
}

const MODEL = "moonshotai/kimi-k2.6";
const MAX_REPORT_CHARS = 1800;
const MAX_CONTEXT_CHARS = 18000;

function clip(value: unknown, max = 600): string {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? null);
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}...` : text;
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

function compactEvent(e: WsEvent): Record<string, unknown> {
  const data = (e.data ?? {}) as Record<string, unknown>;
  return {
    type: e.type,
    ts: e.ts,
    stage: data.stage,
    node: data.node,
    tool: data.tool,
    message: clip(data.message ?? data.error ?? data.result ?? data.report_text ?? data, 500),
  };
}

function buildTickerContext(
  ticker: string,
  price: Record<string, unknown>,
  run: RunDetail | null | undefined,
  events: WsEvent[],
  reports: { stage: string; text: string }[],
): string {
  const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
  const decision = decisionEvent?.data ?? (run?.decision_action
    ? {
        action: run.decision_action,
        target: run.decision_target,
        confidence: run.decision_confidence,
        rationale: run.decision_rationale,
      }
    : null);

  const context = {
    ticker,
    current_price_feed: price,
    selected_run: run
      ? {
          id: run.id,
          status: run.status,
          started_at: run.started_at,
          finished_at: run.finished_at,
          llm_provider: run.llm_provider,
          deep_think_model: run.deep_think_model,
          quick_think_model: run.quick_think_model,
          start_price: run.start_price,
          start_price_at: run.start_price_at,
          total_duration_s: run.total_duration_s,
        }
      : null,
    decision,
    analyst_reports: reports,
    recent_events: events.slice(-24).map(compactEvent),
    recent_llm_calls: (run?.llm_calls ?? []).slice(-6).map((call) => ({
      node: call.node_name,
      model: call.model,
      started_at: call.started_at,
      prompt_excerpt: clip(call.prompt_text, 700),
      response_excerpt: clip(call.response_text, 900),
      total_tokens: call.total_tokens,
      duration_ms: call.duration_ms,
    })),
  };

  return clip(JSON.stringify(context, null, 2), MAX_CONTEXT_CHARS);
}

export function TickerChatBar({ ticker, price, run }: Props) {
  const events = useFocusedRunEvents();
  const reports = useStageReports(events).map((report) => ({
    stage: report.stage,
    text: clip(report.text, MAX_REPORT_CHARS),
  }));
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { messages, addMessage, updateMessage, clearMessages } = useChatStore();

  const context = useMemo(() => buildTickerContext(ticker, price, run, events, reports), [ticker, price, run, events, reports]);
  const hasContext = events.length > 0 || run != null || Object.keys(price).length > 0;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isAsking) return;
    setError("");

    if (!window.puter?.ai?.chat) {
      setError("Puter AI is still loading or unavailable. Check the network connection and try again.");
      return;
    }

    const userMessage = { role: "user" as const, content: trimmed };
    addMessage(userMessage);
    setQuestion("");
    setIsAsking(true);

    try {
      const tools = await fetchTools();
      const puterTools = tools.map(tool => ({
        name: tool.name,
        description: tool.description,
        parameters: tool.parameters,
      }));

      const systemPrompt = [
        `You are a market-analysis assistant answering questions about ticker ${ticker}.`,
        "Use the provided dashboard context first. If context is missing or stale, say what is missing.",
        "Do not invent current prices, filings, news, or decisions that are not in the context.",
        "Keep the answer concise, cite the relevant context fields, and avoid presenting this as financial advice.",
        "",
        "DASHBOARD CONTEXT JSON:",
        context,
      ].join("\n");

      const conversationHistory = [
        { role: "system", content: systemPrompt },
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: "user", content: trimmed },
      ];

      const assistantMsgId = addMessage({ role: "assistant", content: "", isStreaming: true });

      const response = await window.puter.ai.chat(conversationHistory, {
        model: MODEL,
        tools: puterTools,
        stream: true,
      });

      let fullResponse = "";
      if (response && typeof response === "object" && Symbol.asyncIterator in (response as object)) {
        for await (const chunk of response as AsyncIterable<Record<string, unknown>>) {
          if (chunk.text) {
            fullResponse += chunk.text;
            updateMessage(assistantMsgId, { content: fullResponse });
          }
        }
      } else {
        fullResponse = extractResponseText(response);
        updateMessage(assistantMsgId, { content: fullResponse });
      }

      updateMessage(assistantMsgId, { isStreaming: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The chat request failed.");
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <section className="glass-panel mb-4 overflow-hidden">
      {messages.length > 0 && (
        <div className="max-h-80 overflow-y-auto border-b border-slate-700/50 px-3 py-3">
          {messages.map((msg) => (
            <div key={msg.id} className={`mb-2 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-sky-600/30 text-slate-200"
                  : "bg-slate-800/60 text-slate-300"
              }`}>
                {msg.content}
                {msg.isStreaming && <span className="animate-pulse ml-1">|</span>}
              </div>
            </div>
          ))}
          {isAsking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-lg bg-slate-800/60 px-3 py-2 text-sm text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}
      <form onSubmit={ask} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-950/40 px-3 py-2">
          <MessageSquare className="h-4 w-4 shrink-0 text-sky-400" aria-hidden="true" />
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
            placeholder={`Ask about ${ticker}`}
            aria-label={`Ask about ${ticker}`}
          />
          {question && (
            <button
              type="button"
              onClick={() => setQuestion("")}
              className="rounded-md p-1 text-slate-500 transition-colors hover:text-slate-300"
              aria-label="Clear question"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
        <button
          type="submit"
          disabled={!question.trim() || isAsking}
          className="btn-primary inline-flex items-center justify-center gap-2 text-xs sm:w-auto"
          title={hasContext ? `Ask ${MODEL} with ticker context` : "Ask with limited ticker context"}
        >
          {isAsking ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Send className="h-3.5 w-3.5" aria-hidden="true" />}
          Ask
        </button>
      </form>
      {error && (
        <div className="border-t border-slate-700/50 px-3 py-3">
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd web/frontend && npx tsc --noEmit src/components/TickerChatBar.tsx`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/components/TickerChatBar.tsx
git commit -m "feat: update TickerChatBar to use agent with tool calling"
```

---

### Task 7: Testing and Integration

**Files:**
- None (testing only)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Verified working system

- [ ] **Step 1: Run backend server and test endpoints**

```bash
cd web/server
python -c "from chat_router import router; print('Chat router OK')"
```

- [ ] **Step 2: Run frontend build**

```bash
cd web/frontend
npm run build
```

- [ ] **Step 3: Start dev server and test manually**

```bash
cd web/frontend
npm run dev
```

Test in browser:
1. Open app, click floating chat bubble
2. Ask "What tickers are in my watchlist?"
3. Verify AI calls tool and returns data
4. Go to ticker detail page
5. Ask "What was the last analysis for this ticker?"
6. Verify TickerChatBar works with agent

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete agent chat with full backend API access"
```

---

## Summary

| Task | Description | Files Created/Modified |
|------|-------------|------------------------|
| 1 | Backend chat router | chat_router.py, app.py |
| 2 | Frontend agent tools | agentTools.ts |
| 3 | Chat store (Zustand) | useChatStore.ts |
| 4 | AgentChatBubble component | AgentChatBubble.tsx |
| 5 | Add bubble to App | App.tsx |
| 6 | Update TickerChatBar | TickerChatBar.tsx |
| 7 | Testing and integration | - |
