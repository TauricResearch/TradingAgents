# Agent Chat Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the one remaining backend test failure and convert `IndicatorRailView` to a full conversation agent backed by the global `useChatStore`, Puter.js, and the auto-generated tool proxy.

**Architecture:** Reuse the global Zustand chat store so the indicator-side conversation shares history with the floating `AgentChatBubble` and the `TickerChatBar`. The chat logic follows the same streaming + tool-use pattern already proven in `TickerChatBar.tsx`.

**Tech Stack:** React, TypeScript, Zustand, Puter.js, FastAPI, pytest, Vite

## Global Constraints

- Maintain existing UI layout of `IndicatorRailView` (list + notifier settings + bottom chat)
- Keep TypeScript strict mode
- Follow existing ESLint / formatting rules
- Use `uv run` for Python tests
- Use `npm run build` for frontend verification

---

## File Structure

| File | Action | Reason |
|------|--------|--------|
| `web/server/tests/test_chat_router.py` | Modify line 62 | Assertion outdated after tool-name sanitization fix |
| `web/frontend/src/components/IndicatorRailView.tsx` | Major rewrite of chat section | Replace local keyword-based chat with global agent chat |

---

### Task 1: Fix Backend Failing Test

**Files:**
- Modify: `web/server/tests/test_chat_router.py:62`

**Interfaces:**
- `extract_tool_definitions(app)` now sanitises every non-alphanumeric char to `_`; therefore `{ticker}` becomes `__ticker__`.

- [ ] **Step 1: Update assertion**

```python
# OLD (line 62)
    assert "get_tickers_{ticker}_runs" in names or "get_tickers_{ticker}_runs" in names

# NEW
    assert "get_tickers__ticker__runs" in names
```

- [ ] **Step 2: Run test**

Run:
```bash
uv run python -m pytest web/server/tests/test_chat_router.py::test_extract_tool_definitions_discovers_routes -v
```
Expected: `PASSED`

- [ ] **Step 3: Run full backend suite**

Run:
```bash
uv run python -m pytest web/server/tests/test_chat_router.py -v
```
Expected: `11/11 passed`

- [ ] **Step 4: Commit**

```bash
git add web/server/tests/test_chat_router.py
git commit -m "test: align tool-name assertion with sanitised path params"
```

---

### Task 2: Convert IndicatorRailView to Agent Chat

**Files:**
- Modify: `web/frontend/src/components/IndicatorRailView.tsx`

**Interfaces:**
- Consumes: `useChatStore` (global), `fetchTools`, `executeTool`, `window.puter.ai.chat`
- Produces: Indicator-side conversation that shares the global `ChatMessage[]`

**Plan:** Replace the local `messages` / `setMessages` / `handleChatSubmit` / `addAssistantMessage` block with the same streaming + tool-use loop used in `TickerChatBar.tsx`. Keep the rest of the indicator-management UI intact.

- [ ] **Step 1: Add `Loader2` to lucide-react import and import chat utilities**

Change:
```typescript
import { Activity, Bell, BellOff, Send, Trash2, X } from "lucide-react";
```
To:
```typescript
import { Activity, Bell, BellOff, Loader2, Send, Trash2, X } from "lucide-react";
```

Add imports after the existing `../lib/api` import block:
```typescript
import { useChatStore } from "../stores/useChatStore";
import { fetchTools, executeTool } from "../lib/agentTools";
```

- [ ] **Step 2: Replace local chat state and helpers with global store**

Locate:
```typescript
  const [chat, setChat] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
```

Replace with:
```typescript
  const [input, setInput] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const { messages, addMessage, updateMessage } = useChatStore();
```

Locate and **remove** the `addAssistantMessage` function.

Also remove the old `handleChatSubmit` and the `scrollToBottom` / `useEffect` for local messages (we will keep `scrollToBottom` and re-use it with the global array).

- [ ] **Step 3: Insert the new `ask` handler**

Insert directly before the `return` statement:

```typescript
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isAsking) return;

    if (!window.puter?.ai?.chat) {
      addMessage({ role: "assistant", content: "Puter AI is unavailable. Please refresh and try again." });
      return;
    }

    addMessage({ role: "user", content: trimmed });
    setInput("");
    setIsAsking(true);

    const assistantMsgId = addMessage({
      role: "assistant",
      content: "",
      isStreaming: true,
    });

    try {
      const tools = await fetchTools();
      const puterTools = tools.map((tool) => ({
        type: "function" as const,
        function: {
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters,
        },
      }));

      const systemPrompt = [
        "You are a trading indicators assistant.",
        "Help the user manage, add, remove, update, and check indicator conditions.",
        "Use the available tools to perform actions, then explain the results clearly.",
        "Be concise.",
      ].join("\n");

      const conversationHistory = [
        { role: "system", content: systemPrompt },
        ...messages.filter((m) => m.content && m.content.trim()).map((m) => ({ role: m.role, content: m.content })),
        { role: "user", content: trimmed },
      ];

      const response = await window.puter.ai.chat(conversationHistory, {
        model: "moonshotai/kimi-k2.6",
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
          if ((chunk as Record<string, unknown>).type === "tool_use") {
            const toolCall = chunk as { id: string; name: string; input: Record<string, unknown> };
            const result = await executeTool(toolCall.name, toolCall.input);
            addMessage({ role: "tool", content: JSON.stringify(result) });
          }
        }
      } else {
        const text = typeof response === "string" ? response : JSON.stringify(response);
        updateMessage(assistantMsgId, { content: text });
      }
      updateMessage(assistantMsgId, { isStreaming: false });
    } catch (err) {
      updateMessage(assistantMsgId, {
        isStreaming: false,
        content: `Error: ${err instanceof Error ? err.message : "Unknown error"}`,
      });
    } finally {
      setIsAsking(false);
    }
  };
```

**Notes for the implementer:**
- Ensure `useEffect` is imported from React.
- `messages` inside `ask` comes from the global store and is stable because we map it fresh inside the handler.

- [ ] **Step 4: Strip manual command interception and old UI chat helpers**

Locate the old `handleChatSubmit` and delete its entire body if it still exists.

In `addMutation.onSuccess`, remove the `addAssistantMessage` call (or replace with nothing since the function is gone). Same for `removeMutation.onSuccess`, `updateMutation.onSuccess`, and `updateMutation.onError` — delete the message-adding lines.

- [ ] **Step 5: Replace messages list JSX**

Locate the block:
```tsx
      {messages.length > 0 && (
        <div className="shrink-0 max-h-48 overflow-y-auto border-t border-slate-800 px-2 py-2 space-y-1.5">
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-lg px-2 py-1.5 text-[11px] leading-snug ${
                msg.role === "user"
                  ? "bg-sky-600/30 text-slate-200"
                  : "bg-slate-800/60 text-slate-400"
              }`}>
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}
```

Replace with:
```tsx
      {messages.length > 0 && (
        <div className="shrink-0 max-h-48 overflow-y-auto border-t border-slate-800 px-2 py-2 space-y-1.5">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-lg px-2 py-1.5 text-[11px] leading-snug ${
                  msg.role === "user"
                    ? "bg-sky-600/30 text-slate-200"
                    : msg.role === "tool"
                      ? "bg-slate-800 text-slate-400 font-mono"
                      : "bg-slate-800/60 text-slate-400"
                }`}
              >
                {msg.content}
                {msg.isStreaming && <span className="animate-pulse ml-1">|</span>}
              </div>
            </div>
          ))}
          {isAsking && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 rounded-lg bg-slate-800/60 px-3 py-2 text-sm text-slate-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Thinking…
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}
```

- [ ] **Step 6: Replace the chat input form**

Locate:
```tsx
      <form onSubmit={handleChatSubmit} className="shrink-0 border-t border-slate-800 p-2">
        {messages.length === 0 && (
          <p className="mb-2 rounded-lg bg-slate-800/50 px-2 py-1.5 text-[11px] leading-snug text-slate-400">
            Ask me to add or remove an indicator.
          </p>
        )}
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 bg-slate-950/40 px-2 py-1.5">
          <input
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="add VIX 25..."
            className="min-w-0 flex-1 bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-600"
            aria-label="Indicator chat command"
          />
          <button
            type="submit"
            disabled={!chat.trim() || addMutation.isPending || removeMutation.isPending}
            className="rounded-md p-1 text-sky-400 transition-colors hover:bg-sky-500/10 disabled:text-slate-600"
            aria-label="Send indicator command"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </form>
```

Replace with:
```tsx
      <form onSubmit={ask} className="shrink-0 border-t border-slate-800 p-2">
        {messages.length === 0 && (
          <p className="mb-2 rounded-lg bg-slate-800/50 px-2 py-1.5 text-[11px] leading-snug text-slate-400">
            Ask me to manage indicators using natural language.
          </p>
        )}
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 bg-slate-950/40 px-2 py-1.5">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about indicators..."
            className="min-w-0 flex-1 bg-transparent text-xs text-slate-200 outline-none placeholder:text-slate-600"
            aria-label="Indicator chat command"
          />
          <button
            type="submit"
            disabled={!input.trim() || isAsking}
            className="rounded-md p-1 text-sky-400 transition-colors hover:bg-sky-500/10 disabled:text-slate-600"
            aria-label="Send indicator command"
          >
            {isAsking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          </button>
        </div>
      </form>
```

- [ ] **Step 7: Verify TypeScript**

Run:
```bash
cd web/frontend && npx tsc --noEmit
```
Expected: `0 errors`

- [ ] **Step 8: Verify build**

Run:
```bash
cd web/frontend && npm run build
```
Expected: `✓ built` with no errors.

- [ ] **Step 9: Commit**

```bash
git add web/frontend/src/components/IndicatorRailView.tsx
git commit -m "feat: convert IndicatorRailView to agent chat with tool calling and global store"
```

---

### Task 3: Final Polish & Integration Verification

**Files:**
- None (verification only)

**Interfaces:**
- Ensures all prior tasks play well together.

- [ ] **Step 1: Run backend chat_router test suite**

```bash
uv run python -m pytest web/server/tests/test_chat_router.py -v
```
Expected: `11/11 passed`

- [ ] **Step 2: Frontend TypeScript check**

Run:
```bash
cd web/frontend && npx tsc --noEmit
```
Expected: `0 errors`

- [ ] **Step 3: Frontend production build**

Run:
```bash
cd web/frontend && npm run build
```
Expected `✓ built`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "polish: final integration verification for agent chat feature"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Fix backend test | `web/server/tests/test_chat_router.py` |
| 2 | Convert IndicatorRailView | `web/frontend/src/components/IndicatorRailView.tsx` |
| 3 | Final verification | - |
