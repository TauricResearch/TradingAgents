/** Ask-the-record (A1): interrogate ONE run's reasoning. The model answers
 * only from that run's evidence/debate/verdict, cites agent ids, and says
 * so when a question is out of scope. Not a general chatbot — a lens on
 * the record already on screen. */
import { useState } from "react";

import { Button } from "./ui/button";
import { ApiError } from "@/lib/api/client";
import { askRun, askRunStream } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "What is the strongest counterargument?",
  "What would invalidate this trade?",
  "Which evidence drove the confidence?",
];

interface Turn {
  q: string;
  answer: string;
  cited: string[];
  answerable: boolean;
  streaming: boolean;
}

/** Split a streamed reply into prose + citation tags at the trailing
 * "SOURCES: id1, id2" line the stream prompt asks for. */
function splitSources(text: string): { prose: string; cited: string[] } {
  const idx = text.lastIndexOf("SOURCES:");
  if (idx === -1) return { prose: text, cited: [] };
  const prose = text.slice(0, idx).trimEnd();
  const rest = text.slice(idx + "SOURCES:".length).trim();
  const cited =
    rest && rest.toLowerCase() !== "none"
      ? rest.split(/[,\s]+/).filter(Boolean)
      : [];
  return { prose, cited };
}

export function EvidenceChat({ runId }: { runId: string | null }) {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);

  if (!runId) return null;

  const ask = async (q: string) => {
    const query = q.trim();
    if (!query || pending) return;
    setPending(true);
    setError(null);
    const index = turns.length;
    setTurns((prev) => [
      ...prev,
      { q: query, answer: "", cited: [], answerable: true, streaming: true },
    ]);
    setQuestion("");

    const patch = (fields: Partial<Turn>) =>
      setTurns((prev) =>
        prev.map((t, i) => (i === index ? { ...t, ...fields } : t)),
      );

    try {
      let raw = "";
      await askRunStream(runId, query, (chunk) => {
        raw += chunk;
        // render prose live, hiding the SOURCES trailer until it completes
        patch({ answer: splitSources(raw).prose });
      });
      const { prose, cited } = splitSources(raw);
      patch({ answer: prose, cited, streaming: false });
    } catch (streamErr) {
      // fall back to the structured endpoint (also handles 503 messaging)
      try {
        const a = await askRun(runId, query);
        patch({
          answer: a.answer,
          cited: a.cited_agent_ids,
          answerable: a.answerable,
          streaming: false,
        });
      } catch (e) {
        setTurns((prev) => prev.filter((_, i) => i !== index));
        setError(
          (streamErr instanceof ApiError && streamErr.status === 503) ||
            (e instanceof ApiError && e.status === 503)
            ? "Ask is unavailable in monitor mode (no model attached)."
            : "The model couldn't answer — try again.",
        );
      }
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
                turn.answerable ? "text-fg-muted" : "text-stale italic",
              )}
            >
              {turn.answer}
              {turn.streaming && (
                <span className="ml-0.5 animate-pulse text-fg-subtle">▍</span>
              )}
            </p>
            {turn.cited.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {turn.cited.map((id) => (
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
