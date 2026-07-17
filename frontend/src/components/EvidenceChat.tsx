/** Ask-the-record (A1): interrogate ONE run's reasoning. The model answers
 * only from that run's evidence/debate/verdict, cites agent ids, and says
 * so when a question is out of scope. Not a general chatbot — a lens on
 * the record already on screen. */
import { useState } from "react";

import { Button } from "./ui/button";
import { ApiError } from "@/lib/api/client";
import { askRun, type EvidenceAnswer } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "What is the strongest counterargument?",
  "What would invalidate this trade?",
  "Which evidence drove the confidence?",
];

export function EvidenceChat({ runId }: { runId: string | null }) {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<
    { q: string; a: EvidenceAnswer }[]
  >([]);

  if (!runId) return null;

  const ask = async (q: string) => {
    const query = q.trim();
    if (!query || pending) return;
    setPending(true);
    setError(null);
    try {
      const a = await askRun(runId, query);
      setTurns((prev) => [...prev, { q: query, a }]);
      setQuestion("");
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 503
          ? "Ask is unavailable in monitor mode (no model attached)."
          : "The model couldn't answer — try again.",
      );
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="evidence-chat">
      <div className="space-y-2">
        {turns.map((turn, i) => (
          <div key={i} className="space-y-1 text-sm">
            <p className="font-semibold text-fg">{turn.q}</p>
            <p
              className={cn(
                turn.a.answerable ? "text-fg-muted" : "text-stale italic",
              )}
            >
              {turn.a.answer}
            </p>
            {turn.a.cited_agent_ids.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {turn.a.cited_agent_ids.map((id) => (
                  <span
                    key={id}
                    className="inline-flex items-center rounded-[6px] bg-surface-2 px-1.5 font-mono text-[10px] text-fg-muted"
                  >
                    {id}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {turns.length === 0 && (
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              disabled={pending}
              onClick={() => void ask(s)}
              className="rounded-full border border-border px-2.5 py-1 text-xs text-fg-subtle hover:text-fg disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(question);
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this decision…"
          maxLength={500}
          className="min-w-0 grow rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm"
          data-testid="evidence-chat-input"
        />
        <Button size="sm" type="submit" disabled={pending || !question.trim()}>
          {pending ? "…" : "Ask"}
        </Button>
      </form>
      {error && <p className="text-xs text-bear">{error}</p>}
      <p className="text-[10px] text-fg-subtle">
        Answers come only from this run's evidence — not live data or advice.
      </p>
    </div>
  );
}
