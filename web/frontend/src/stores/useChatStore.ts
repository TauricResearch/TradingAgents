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
  toolCallId?: string;
}

export interface ChatSession {
  id: string;
  name: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
}

const STORAGE_KEY = "trading-agents-chat-sessions";
const MAX_SESSION_NAME_LENGTH = 60;

function loadSessions(): Record<string, ChatSession> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return {};
}

function saveSessions(sessions: Record<string, ChatSession>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch { /* ignore */ }
}

function deriveName(messages: ChatMessage[]): string {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return "New Chat";
  const text = firstUser.content.trim().slice(0, MAX_SESSION_NAME_LENGTH);
  return text.length < firstUser.content.trim().length ? text + "…" : text;
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function createSession(messages?: ChatMessage[]): ChatSession {
  const now = Date.now();
  const msgs = messages ?? [];
  return {
    id: generateId(),
    name: deriveName(msgs),
    messages: msgs,
    createdAt: now,
    updatedAt: now,
  };
}

interface ChatState {
  sessions: Record<string, ChatSession>;
  activeSessionId: string | null;
  messages: ChatMessage[];
  isOpen: boolean;
  isLoading: boolean;

  addMessage: (msg: Omit<ChatMessage, "id" | "timestamp">) => string;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  toggleChat: () => void;
  setOpen: (open: boolean) => void;
  setLoading: (loading: boolean) => void;
  clearMessages: () => void;

  createSession: () => string;
  deleteSession: (id: string) => void;
  switchSession: (id: string) => void;
  renameSession: (id: string, name: string) => void;
}

function persist(state: ChatState) {
  saveSessions(state.sessions);
}

function syncMessages(sessions: Record<string, ChatSession>, activeSessionId: string | null): ChatMessage[] {
  if (activeSessionId && sessions[activeSessionId]) {
    return sessions[activeSessionId].messages;
  }
  return [];
}

export const useChatStore = create<ChatState>((set, get) => {
  const loaded = loadSessions();
  const sessionIds = Object.keys(loaded);
  const activeSessionId = sessionIds.length > 0 ? sessionIds[0] : null;

  return {
    sessions: loaded,
    activeSessionId,
    messages: syncMessages(loaded, activeSessionId),
    isOpen: false,
    isLoading: false,

    addMessage: (msg) => {
      const state = get();
      let sessionId = state.activeSessionId;
      if (!sessionId || !state.sessions[sessionId]) {
        sessionId = createSession().id;
        state.sessions[sessionId] = createSession();
      }
      const id = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      const timestamp = Date.now();
      const newMsg = { ...msg, id, timestamp };
      const session = state.sessions[sessionId];
      session.messages = [...session.messages, newMsg];
      if (session.messages.length === 1) {
        session.name = deriveName(session.messages);
      }
      session.updatedAt = Date.now();
      set({
        sessions: { ...state.sessions, [sessionId]: { ...session } },
        activeSessionId: sessionId,
        messages: [...session.messages],
      });
      persist(get());
      return id;
    },

    updateMessage: (id, updates) => {
      const state = get();
      const sessionId = state.activeSessionId;
      if (!sessionId || !state.sessions[sessionId]) return;
      const session = state.sessions[sessionId];
      session.messages = session.messages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      );
      session.updatedAt = Date.now();
      set({
        sessions: { ...state.sessions, [sessionId]: { ...session } },
        messages: [...session.messages],
      });
      persist(get());
    },

    toggleChat: () => {
      set((s) => ({ isOpen: !s.isOpen }));
    },

    setOpen: (open) => {
      set({ isOpen: open });
    },

    setLoading: (loading) => {
      set({ isLoading: loading });
    },

    clearMessages: () => {
      const state = get();
      const session = createSession();
      set({
        sessions: { ...state.sessions, [session.id]: session },
        activeSessionId: session.id,
        messages: [],
      });
      persist(get());
    },

    createSession: () => {
      const state = get();
      const session = createSession();
      set({
        sessions: { ...state.sessions, [session.id]: session },
        activeSessionId: session.id,
        messages: [],
      });
      persist(get());
      return session.id;
    },

    deleteSession: (id) => {
      const state = get();
      const { [id]: _, ...rest } = state.sessions;
      const ids = Object.keys(rest);
      const newActiveId = state.activeSessionId === id
        ? (ids.length > 0 ? ids[0] : null)
        : state.activeSessionId;
      set({
        sessions: rest,
        activeSessionId: newActiveId,
        messages: newActiveId ? rest[newActiveId].messages : [],
      });
      persist(get());
    },

    switchSession: (id) => {
      const state = get();
      if (!state.sessions[id]) return;
      set({
        activeSessionId: id,
        messages: [...state.sessions[id].messages],
      });
    },

    renameSession: (id, name) => {
      const state = get();
      if (!state.sessions[id]) return;
      const session = { ...state.sessions[id], name: name.slice(0, MAX_SESSION_NAME_LENGTH), updatedAt: Date.now() };
      set({
        sessions: { ...state.sessions, [id]: session },
      });
      persist(get());
    },
  };
});
