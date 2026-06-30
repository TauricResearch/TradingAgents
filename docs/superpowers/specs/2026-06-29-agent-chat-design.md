# Agent Chat Design Spec

## Overview

Convert the existing single-message chat components (TickerChatBar and IndicatorRailView) into a full conversation agent with access to the backend API. Add a global floating chat bubble for agent access from anywhere in the app.

## Goals

1. Full conversation with history (not single Q&A)
2. AI agent with access to all backend API endpoints
3. Free AI via Puter.js (user-pays model)
4. Auto-generated tools from existing API routes
5. Global access via floating chat bubble
6. Ticker-specific context in TickerChatBar

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│  ┌─────────────┐    ┌─────────────────┐    ┌────────────────┐  │
│  │  Puter.js   │◄──►│  ChatAgent.tsx  │◄──►│  Tool Executor │  │
│  │  (AI Chat)  │    │  (Conversation) │    │  (fetch calls) │  │
│  └─────────────┘    └─────────────────┘    └────────────────┘  │
│                             │                       │           │
│                             ▼                       ▼           │
│                    ┌─────────────────┐    ┌────────────────┐   │
│                    │  useChatStore   │    │  /api/chat/*   │   │
│                    │  (Zustand)      │    │  (Backend)     │   │
│                    └─────────────────┘    └────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. User types message → Puter.js AI generates response (streaming)
2. If AI needs data → calls backend tool endpoint via proxy
3. Backend returns data → AI incorporates into response
4. If AI wants to perform action → calls backend action endpoint via proxy
5. Backend executes action → returns result to AI
6. AI explains result to user

## Backend Endpoints

### Auto-Generated Tools

```python
# /api/chat/tools - Auto-generated from FastAPI routes
GET /api/chat/tools
Response: {
  "tools": [
    {
      "name": "get_watchlist",
      "description": "Get list of all tickers in watchlist",
      "method": "GET",
      "path": "/api/watchlist",
      "parameters": {},
      "returns": "WatchlistRow[]"
    },
    {
      "name": "add_to_watchlist",
      "description": "Add a ticker to watchlist",
      "method": "POST",
      "path": "/api/watchlist",
      "parameters": { "ticker": "string" },
      "returns": "WatchlistRow"
    },
    # ... auto-generated from all existing routes
  ]
}
```

### Generic Proxy

```python
# /api/chat/proxy - Forward requests to any endpoint
POST /api/chat/proxy
Body: {
  "method": "GET",
  "path": "/api/watchlist",
  "params": {},
  "body": null
}
Response: forwarded response from the actual endpoint
```

**Benefits:**
- Zero duplication - tools auto-generated from existing routes
- Adding new API endpoints automatically adds new tools
- Single maintenance point (existing routes)

## Frontend Components

### New Files

```
web/frontend/src/
├── components/
│   ├── AgentChatBubble.tsx      # Floating chat bubble + panel
│   └── TickerChatBar.tsx        # Updated to use agent
├── stores/
│   └── useChatStore.ts          # Zustand store for chat state
├── lib/
│   └── agentTools.ts            # Tool fetching + proxy execution
```

### AgentChatBubble.tsx

- Fixed position bottom-right corner
- Click to expand/collapse chat panel
- Shows conversation history with scroll
- Input field for user messages
- Streaming response display
- Tool call/result visualization

### useChatStore.ts

```typescript
interface ChatMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
}

interface ChatStore {
  messages: ChatMessage[];
  isOpen: boolean;
  isLoading: boolean;
  addMessage: (msg: ChatMessage) => void;
  toggleChat: () => void;
  clearMessages: () => void;
}
```

### agentTools.ts

```typescript
// Fetch tool definitions from backend
export async function fetchTools(): Promise<ToolDefinition[]>

// Execute a tool via proxy
export async function executeTool(
  name: string,
  params: Record<string, unknown>
): Promise<unknown>
```

## AI Integration

### Puter.js Tool Calling Pattern

```typescript
// In AgentChatBubble.tsx
const tools = await fetchTools();

// Convert to Puter.js format
const puterTools = tools.map(tool => ({
  name: tool.name,
  description: tool.description,
  parameters: tool.parameters,
}));

// When user sends message
const response = await puter.ai.chat(messages, {
  model: MODEL,
  tools: puterTools,
  stream: true,
});

// Handle streaming response with potential tool calls
for await (const chunk of response) {
  if (chunk.tool_calls) {
    // Execute each tool call via proxy
    for (const call of chunk.tool_calls) {
      const result = await executeTool(call.name, call.arguments);
      // Add tool result to conversation
      messages.push({ role: "tool", content: result });
    }
    // Continue conversation with tool results
  }
  // Display chunk to user
}
```

### System Prompt

```
You are a trading assistant with access to market data and analysis tools.

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

The tool list is dynamically generated from the backend API schema.
```

## Implementation Steps

### Phase 1: Backend (FastAPI)
1. Create `/api/chat/tools` endpoint that auto-generates tool definitions
2. Create `/api/chat/proxy` endpoint for generic request forwarding
3. Add OpenAPI schema introspection utilities

### Phase 2: Frontend Core
1. Create `agentTools.ts` for tool fetching and proxy execution
2. Create `useChatStore.ts` with Zustand
3. Create `AgentChatBubble.tsx` component

### Phase 3: Integration
1. Update `TickerChatBar.tsx` to use agent capabilities
2. Add floating chat bubble to app layout
3. Test tool calling and streaming

### Phase 4: Polish
1. Add loading states and error handling
2. Add tool call visualization
3. Add conversation clear/reset
4. Style and responsive design

## Testing

1. Test tool list generation from existing routes
2. Test proxy endpoint forwarding
3. Test Puter.js tool calling integration
4. Test streaming responses
5. Test conversation history persistence
6. Test ticker-specific context in TickerChatBar

## Future Enhancements

1. Conversation persistence (localStorage/backend)
2. Multi-session support
3. Custom tool definitions
4. Tool usage analytics
5. Voice input/output
