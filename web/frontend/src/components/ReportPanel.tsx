import { useState } from "react";
import { useFocusedRunEvents } from "../hooks/useFocusedRunEvents";
import { useStageReports } from "./LiveEventStream";

const stageLabels: Record<string, string> = {
  market: "Market Analysis",
  sentiment: "Sentiment Analysis",
  news: "News Analysis",
  fundamentals: "Fundamentals Analysis",
  research: "Research Report",
  trader: "Trader Plan",
  risk: "Risk Assessment",
};

export function ReportPanel() {
  const events = useFocusedRunEvents();
  const reports = useStageReports(events);
  const hasRunFinished = events.some((e) => e.type === "run_finished");
  const [open, setOpen] = useState<string | null>(null);

  if (!hasRunFinished || reports.length === 0) return null;

  return (
    <div className="mt-6">
      <h3 className="text-sm font-semibold text-slate-700 mb-2">Full Reports</h3>
      <div className="space-y-2">
        {reports.map(({ stage, text }) => {
          const isOpen = open === stage;
          return (
            <div key={stage} className="rounded-lg border border-slate-200 overflow-hidden">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : stage)}
                className="w-full text-left px-3 py-2 bg-slate-50 hover:bg-slate-100 text-sm font-medium text-slate-700 flex items-center justify-between"
              >
                <span>{stageLabels[stage] ?? stage}</span>
                <span className="text-slate-400 text-xs">{isOpen ? "▲" : "▼"}</span>
              </button>
              {isOpen && (
                <pre className="text-xs text-slate-800 p-3 whitespace-pre-wrap max-h-96 overflow-y-auto">
                  {text}
                </pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
