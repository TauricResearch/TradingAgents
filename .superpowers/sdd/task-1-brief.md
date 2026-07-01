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

