"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Chat } from "@/lib/api";
import { chatStreamUrl } from "@/lib/ws";
import { Markdown } from "./Markdown";

export function ChatPanel({ runId }: { runId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["chat", runId],
    queryFn: () => Chat.list(runId),
    enabled: !!runId,
  });
  const clear = useMutation({
    mutationFn: () => Chat.clear(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["chat", runId] }),
  });

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [pendingText, setPendingText] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Scroll to bottom on new content.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [q.data, pendingText]);

  function send() {
    const question = input.trim();
    if (!question || streaming) return;
    setInput("");
    setStreaming(true);
    setPendingText("");

    const ws = new WebSocket(chatStreamUrl(runId));
    wsRef.current = ws;

    ws.onopen = () => ws.send(JSON.stringify({ question }));
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "delta") {
          setPendingText((t) => t + msg.text);
        } else if (msg.type === "done") {
          setStreaming(false);
          setPendingText("");
          ws.close();
          qc.invalidateQueries({ queryKey: ["chat", runId] });
        } else if (msg.type === "error") {
          setStreaming(false);
          setPendingText(`_(error: ${msg.message})_`);
          ws.close();
        }
      } catch {
        // ignore malformed frames
      }
    };
    ws.onerror = () => {
      setStreaming(false);
      setPendingText("_(websocket error — is the API up?)_");
    };
    ws.onclose = () => setStreaming(false);
  }

  return (
    <div className="card flex flex-col h-[480px]">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="font-semibold">Chat about this run</h3>
          <p className="text-xs text-muted">
            Quick-think model with the full analysis as context. Conversation persists per run.
          </p>
        </div>
        <button
          className="btn text-xs"
          onClick={() => clear.mutate()}
          disabled={clear.isPending || (q.data?.length ?? 0) === 0}
          title="Delete saved conversation"
        >
          🗑 Clear
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-2">
        {(q.data ?? []).map((m) => (
          <div
            key={m.id}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user"
                  ? "bg-accent/15"
                  : "bg-surface border border-border"
              }`}
            >
              <Markdown>{m.content}</Markdown>
            </div>
          </div>
        ))}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-lg px-3 py-2 text-sm bg-surface border border-border">
              {pendingText ? <Markdown>{pendingText}</Markdown> : "…"}
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2 pt-3 border-t border-border mt-3">
        <input
          className="input flex-1"
          placeholder="Ask anything about this analysis…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          disabled={streaming}
        />
        <button
          className="btn btn-primary"
          onClick={send}
          disabled={streaming || !input.trim()}
        >
          {streaming ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}
