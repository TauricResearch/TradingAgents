import { Telescope } from "lucide-react";

interface TraceTabsProps {
  value: "events" | "llm" | "observatory";
  onChange: (view: "events" | "llm" | "observatory") => void;
}

type TabKey = "events" | "llm" | "observatory";

const ACCENT_MAP: Record<TabKey, { activeClass: string; dotClass: string }> = {
  events: {
    activeClass: "bg-sky-500/15 text-sky-300 border-sky-500/30 z-10",
    dotClass: "bg-sky-400 shadow-[0_0_4px_rgba(56,189,248,0.5)]",
  },
  llm: {
    activeClass: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30 z-10",
    dotClass: "bg-emerald-400 shadow-[0_0_4px_rgba(52,211,153,0.5)]",
  },
  observatory: {
    activeClass: "bg-violet-500/15 text-violet-300 border-violet-500/30 z-10",
    dotClass: "bg-violet-400 shadow-[0_0_4px_rgba(167,139,250,0.5)]",
  },
};

export function TraceTabs({ value, onChange }: TraceTabsProps) {
  const tabs: Array<{ key: TabKey; label: string; shortLabel: string; icon?: JSX.Element }> = [
    { key: "events", label: "Event Stream", shortLabel: "Events" },
    { key: "observatory", label: "Observatory", shortLabel: "Obs", icon: <Telescope className="w-3.5 h-3.5" /> },
    { key: "llm", label: "LLM Trace", shortLabel: "LLM" },
  ];

  return (
    <div className="flex items-center gap-0 mb-4">
      {tabs.map((tab, i) => {
        const isFirst = i === 0;
        const isLast = i === tabs.length - 1;
        const isActive = value === tab.key;
        const accent = ACCENT_MAP[tab.key];
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`px-3 py-1.5 text-xs font-semibold border transition-all ${
              isFirst ? "rounded-l-lg" : "border-l-0"
            } ${isLast ? "rounded-r-lg" : ""} ${
              isActive
                ? accent.activeClass
                : "text-slate-500 border-slate-700/50 hover:text-slate-300 hover:bg-slate-800/40"
            }`}
          >
            <span className="flex items-center gap-1.5">
              {tab.icon ? (
                tab.icon
              ) : (
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? accent.dotClass : "bg-slate-600"}`} />
              )}
              <span className="hidden sm:inline">{tab.label}</span>
              <span className="sm:hidden">{tab.shortLabel}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
