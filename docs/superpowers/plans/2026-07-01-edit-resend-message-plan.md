# Edit and Resend Message Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add edit-and-resend capability to chat messages in both AgentChatBubble and LargeChatScreen.

**Architecture:** Add `editingMessageId` state to the zustand store, add hover-triggered edit buttons to user message bubbles, and modify submit handlers to delete the original message + all subsequent messages before resending.

**Tech Stack:** React, TypeScript, Zustand, Tailwind, Lucide React

**Files to modify:**
- `web/frontend/src/stores/useChatStore.ts`
- `web/frontend/src/components/AgentChatBubble.tsx`
- `web/frontend/src/components/LargeChatScreen.tsx`

---

### Task 1: Add editing state to useChatStore

**Files:**
- Modify: `web/frontend/src/stores/useChatStore.ts`

**Interfaces:**
- Consumes: existing `ChatMessage`, `ChatState` types
- Produces: `editingMessageId: string | null`, `setEditingMessage(id: string | null)`, `deleteMessagesAfter(id: string)`

- [ ] **Step 1: Add editingMessageId to ChatState interface**

Add after `isLoading`:
```typescript
editingMessageId: string | null;
setEditingMessage: (id: string | null) => void;
deleteMessagesAfter: (id: string) => void;
```

- [ ] **Step 2: Add state and actions to store**

Add to initial state in `create<ChatState>`:
```typescript
editingMessageId: null,
```

Add after `clearMessages` handler:
```typescript
setEditingMessage: (id) => {
  set({ editingMessageId: id });
},

deleteMessagesAfter: (id) => {
  const state = get();
  const sessionId = state.activeSessionId;
  if (!sessionId || !state.sessions[sessionId]) return;
  const session = state.sessions[sessionId];
  const idx = session.messages.findIndex((m) => m.id === id);
  if (idx === -1) return;
  session.messages = session.messages.slice(0, idx);
  session.updatedAt = Date.now();
  set({
    sessions: { ...state.sessions, [sessionId]: { ...session } },
    messages: [...session.messages],
  });
  persist(get());
},
```

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/stores/useChatStore.ts
git commit -m "feat: add editingMessageId state and deleteMessagesAfter action to chat store"
```

---

### Task 2: Add edit button to user messages in AgentChatBubble

**Files:**
- Modify: `web/frontend/src/components/AgentChatBubble.tsx`

- [ ] **Step 1: Add Pencil import to lucide-react imports**

Line 2 currently has: `import { MessageSquare, X, Send, Loader2, ChevronDown, Plus, Maximize2, Trash2, History, ChevronRight, CheckCircle2, XCircle, AlertCircle, ArrowRight } from "lucide-react";`

Add `Pencil` after `ArrowRight`:
```typescript
ArrowRight, Pencil } from "lucide-react";
```

- [ ] **Step 2: Add setEditingMessage to destructured store values**

In `AgentChatBubble` function, add to destructured values at line 227:
```typescript
const { messages, isOpen, isLoading, addMessage, updateMessage, toggleChat, setLoading, clearMessages, sessions, activeSessionId, createSession, deleteSession, switchSession, editingMessageId, setEditingMessage, deleteMessagesAfter } = useChatStore();
```

- [ ] **Step 3: Add edit button and resend button to MessageBubble**

In `MessageBubble` component, for user messages, add an edit icon (always visible to work on both desktop and touch). Change the existing user message return block (lines 198-224) to:

```typescript
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
```

- [ ] **Step 4: Handle editing state in handleSubmit**

In `handleSubmit`, add this at the very beginning, right after `if (!trimmed || isLoading) return;`:

```typescript
const editingId = editingMessageId;
if (editingId) {
  deleteMessagesAfter(editingId);
  setEditingMessage(null);
}
```

- [ ] **Step 5: Add cancel-on-Escape handler**

Add a `useEffect` and `handleKeyDown` handler. Add after line 247 (`}, [isOpen]);`):

```typescript
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
```

- [ ] **Step 6: Add editing indicator and cancel button to input area**

In the form section (around line 663), add editing indicator above the input field. Before the input, add:

```typescript
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
```

Also update the input's `placeholder` to change when editing:
```typescript
placeholder={editingMessageId ? "Edit your message..." : "Ask about your trading data..."}
```

- [ ] **Step 7: Change send icon to "Resend" text when editing**

In the form's submit button, replace the conditional Send/Loader2 icon rendering with:

```typescript
{isLoading ? (
  <Loader2 className="h-4 w-4 animate-spin" />
) : editingMessageId ? (
  <span className="text-xs font-medium">Resend</span>
) : (
  <Send className="h-4 w-4" />
)}
```

- [ ] **Step 8: Populate input when editing message is set**

Add `useEffect` to populate input when editing. Add after the Escape handler effect:

```typescript
useEffect(() => {
  if (!editingMessageId) return;
  const msg = messages.find(m => m.id === editingMessageId);
  if (msg && msg.role === "user") {
    setInput(msg.content);
    inputRef.current?.focus();
  }
}, [editingMessageId, messages]);
```

- [ ] **Step 8: Commit**

```bash
git add web/frontend/src/components/AgentChatBubble.tsx
git commit -m "feat: add edit and resend UI to agent chat bubble"
```

---

### Task 3: Add same edit UI to LargeChatScreen

**Files:**
- Modify: `web/frontend/src/components/LargeChatScreen.tsx`

- [ ] **Step 1: Add Pencil import to lucide-react imports**

Line 2: Change to add `Pencil`:
```typescript
import { MessageSquare, X, Send, Loader2, Plus, Minimize2, Trash2, MessageCircle, Pencil } from "lucide-react";
```

- [ ] **Step 2: Add editing state destructuring**

In `LargeChatScreen` function, add to the existing destructure:
```typescript
const { messages, isLoading, addMessage, updateMessage, setLoading, sessions, activeSessionId, createSession, deleteSession, switchSession, editingMessageId, setEditingMessage, deleteMessagesAfter } = useChatStore();
```

- [ ] **Step 3: Add edit button to user message bubbles**

Similar to AgentChatBubble - add edit icon + `pr-8` padding on user messages. Replace the message rendering section (around line 406) with:

```typescript
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
          onClick={() => setEditingMessage(msg.id)}
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
```

- [ ] **Step 4: Handle editing in handleSubmit**

Add at beginning of handleSubmit, after `if (!trimmed || isLoading) return;`:
```typescript
const editingId = editingMessageId;
if (editingId) {
  deleteMessagesAfter(editingId);
  setEditingMessage(null);
}
```

- [ ] **Step 5: Add editing indicator and Escape handler**

Add Escape handler effect after the existing `useEffect`:
```typescript
useEffect(() => {
  if (!editingMessageId) return;
  const handleKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      setEditingMessage(null);
      setInput("");
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
```

- [ ] **Step 6: Add editing indicator in input area**

Before the input element, add the editing indicator:
```typescript
{editingMessageId && (
  <div className="flex items-center justify-between mb-2">
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
```

Also update input placeholder:
```typescript
placeholder={editingMessageId ? "Edit your message..." : "Ask about your trading data..."}
```

- [ ] **Step 7: Change send icon to "Resend" text when editing**

In the form's submit button, change the conditional rendering from:
```typescript
{isLoading ? (
  <Loader2 className="h-5 w-5 animate-spin" />
) : (
  <Send className="h-5 w-5" />
)}
```
to:
```typescript
{isLoading ? (
  <Loader2 className="h-5 w-5 animate-spin" />
) : editingMessageId ? (
  <span className="text-xs font-medium">Resend</span>
) : (
  <Send className="h-5 w-5" />
)}
```

- [ ] **Step 8: Commit**

```bash
git add web/frontend/src/components/LargeChatScreen.tsx
git commit -m "feat: add edit and resend UI to large chat screen"
```
