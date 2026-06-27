interface TraceTabsProps {
  value: "events" | "llm" | "observatory";
  onChange: (view: "events" | "llm" | "observatory") => void;
}

export function TraceTabs({ value, onChange }: TraceTabsProps) {
  const tabs: Array<{ key: typeof value; label: string; shortLabel: string }> = [
    { key: "events", label: "Event Stream", shortLabel: "Events" },
    { key: "observatory", label: "🔭 Observatory", shortLabel: "🔭 Obs" },
    { key: "llm", label: "LLM Trace", shortLabel: "LLM" },
  ];

  return (
    <div className="flex items-center gap-0 mb-4">
      {tabs.map((tab, i) => {
        const isFirst = i === 0;
        const isLast = i === tabs.length - 1;
        const isActive = value === tab.key;
        const accentColor = tab.key === "llm" ? "emerald" : "sky";
        return (
          <button
            key={tab.key}
            onClick={() => onChange(tab.key)}
            className={`px-3 py-1.5 text-xs font-semibold border transition-all ${
              isFirst ? "rounded-l-lg" : "border-l-0"
            } ${isLast ? "rounded-r-lg" : ""} ${
              isActive
                ? `bg-${accentColor}-500/15 text-${accentColor}-300 border-${accentColor}-500/30 z-10`
                : "text-slate-500 border-slate-700/50 hover:text-slate-300"
            }`}
          >
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isActive ? `bg-${accentColor}-400 shadow-[0_0_4px_rgba(56,189,248,0.5)]` : "bg-slate-600"}`} />
              <span className="hidden sm:inline">{tab.label}</span>
              <span className="sm:hidden">{tab.shortLabel}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
