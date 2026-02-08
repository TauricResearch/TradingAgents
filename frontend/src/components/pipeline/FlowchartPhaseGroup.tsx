import { CheckCircle, Loader2, Clock } from 'lucide-react';
import type { FlowchartPhase } from '../../types/pipeline';
import { PHASE_META } from '../../types/pipeline';

interface FlowchartPhaseGroupProps {
  phase: FlowchartPhase;
  totalSteps: number;
  completedSteps: number;
  isActive: boolean;
  children: React.ReactNode;
}

export function FlowchartPhaseGroup({ phase, totalSteps, completedSteps, isActive, children }: FlowchartPhaseGroupProps) {
  const meta = PHASE_META[phase];
  const isComplete = completedSteps === totalSteps && totalSteps > 0;

  return (
    <div className={`rounded-xl border-l-4 ${meta.borderColor} ${meta.bgColor} border border-slate-200/60 dark:border-slate-700/60 overflow-hidden`}>
      {/* Phase header */}
      <div className="flex items-center justify-between px-3 sm:px-4 py-2 bg-white/40 dark:bg-slate-800/40">
        <div className="flex items-center gap-2">
          <span className={`text-[10px] sm:text-xs font-bold px-1.5 py-0.5 rounded ${meta.bgColor} ${meta.textColor}`}>
            Phase {meta.number}
          </span>
          <span className={`text-xs sm:text-sm font-semibold ${meta.textColor}`}>
            {meta.label}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">
            {completedSteps}/{totalSteps}
          </span>
          {isComplete ? (
            <CheckCircle className="w-3.5 h-3.5 text-green-500" />
          ) : isActive ? (
            <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />
          ) : (
            <Clock className="w-3.5 h-3.5 text-slate-400" />
          )}
        </div>
      </div>

      {/* Phase nodes */}
      <div className="px-3 sm:px-4 py-2 space-y-0">
        {children}
      </div>
    </div>
  );
}
