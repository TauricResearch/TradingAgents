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
