import { useChatStore } from "../stores/useChatStore";

const API_BASE = "/api/chat";

interface ChatMessage {
  role: string;
  content: string;
  tool_calls?: Array<{
    id: string;
    type: string;
    function: {
      name: string;
      arguments: string;
    };
  }>;
  tool_call_id?: string;
}

interface ChatResponse {
  id: string;
  choices: Array<{
    message: {
      role: string;
      content: string;
    };
    finish_reason: string;
  }>;
}

export async function sendChatCompletion(
  messages: ChatMessage[],
  tools?: unknown[]
): Promise<string> {
  const response = await fetch(`${API_BASE}/completions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      tools: tools || [],
      stream: false,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Chat completion failed");
  }

  const data: ChatResponse = await response.json();
  return data.choices[0]?.message?.content || "";
}
