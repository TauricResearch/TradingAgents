import { useRef, useEffect } from "react";
import type { WsEvent } from "../lib/events";

interface ThinkingStreamProps {
  events: WsEvent[];
  agentName: string;
}

export function ThinkingStream({ events, agentName }: ThinkingStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const agentEvents = events.filter(e => {
    if (e.type !== "analyst_thinking") return false;
    return (e.data as any)?.node === agentName;
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentEvents.length]);

  if (agentEvents.length === 0) {
    return <div className="text-xs text-slate-600 italic py-4 text-center">No thinking data yet.</div>;
  }

  return (
    <div className="bg-slate-950/60 rounded-lg border border-slate-800/50 max-h-96 overflow-y-auto font-mono text-xs">
      {agentEvents.map((e, i) => {
        const d = e.data as any;
        const text = d.text_fragment || d.text_preview || "";
        const isPrompt = !!d.text_preview;
        return (
          <div key={i} className="px-3 py-1.5">
            <span className="text-slate-600 mr-2">{new Date(e.ts).toLocaleTimeString()}</span>
            {text}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
