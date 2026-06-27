interface PipelineStatsProps {
  agentsDone: number;
  agentsTotal: number;
  llmCalls: number;
  toolCalls: number;
  elapsedSec: number;
}

export function PipelineStats({ agentsDone, agentsTotal, llmCalls, toolCalls, elapsedSec }: PipelineStatsProps) {
  const fmt = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  return (
    <div className="flex items-center gap-3 mt-2.5 pt-2 border-t border-slate-700/30 text-[10px] font-mono text-slate-500">
      <span className="flex items-center gap-1">
        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: agentsDone === agentsTotal ? "#34d399" : "#38bdf8" }} />
        <span className="font-semibold tabular-nums" style={{ color: agentsDone === agentsTotal ? "#34d399" : "#94a3b8" }}>
          {agentsDone}
        </span>
        <span className="text-slate-600">/</span>
        <span className="text-slate-400">{agentsTotal}</span>
        <span className="text-slate-600">agents</span>
      </span>
      <span className="w-px h-3 bg-slate-700/40" />
      <span className="text-slate-600">LLM</span>
      <span className="text-sky-400/80 tabular-nums">{llmCalls}</span>
      <span className="w-px h-3 bg-slate-700/40" />
      <span className="text-slate-600">tools</span>
      <span className="text-amber-400/80 tabular-nums">{toolCalls}</span>
      <span className="w-px h-3 bg-slate-700/40" />
      <span className="text-slate-600">elapsed</span>
      <span className="text-slate-300 tabular-nums">{fmt(elapsedSec)}</span>
    </div>
  );
}
