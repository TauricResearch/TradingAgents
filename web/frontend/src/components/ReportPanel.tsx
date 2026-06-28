import { useState } from "react";
import { ChevronDown, FileText } from "lucide-react";
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
      <h3 className="section-header mb-3 flex items-center gap-2">
        <FileText className="w-3 h-3 text-emerald-400" />
        Full Reports
      </h3>
      <div className="space-y-2">
        {reports.map(({ stage, text }) => {
          const isOpen = open === stage;
          return (
            <div key={stage} className="glass-panel overflow-hidden">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : stage)}
                className="w-full text-left px-4 py-2.5 hover:bg-slate-700/30 text-sm font-medium text-slate-300 flex items-center justify-between transition-colors"
                aria-expanded={isOpen}
                aria-controls={`report-${stage}`}
              >
                <span>{stageLabels[stage] ?? stage}</span>
                <ChevronDown
                  className={`w-3.5 h-3.5 text-slate-500 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
                />
              </button>
              {isOpen && (
                <div id={`report-${stage}`} role="region" aria-label={stageLabels[stage] ?? stage}>
                  <pre className="text-xs text-slate-400 p-4 whitespace-pre-wrap max-h-96 overflow-y-auto border-t border-slate-700/50 leading-relaxed">
                    {text}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
