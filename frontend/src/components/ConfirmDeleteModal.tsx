import React, { useEffect } from 'react';
import { AlertTriangle, Trash2, X } from 'lucide-react';
import { Job } from '../types';

export type DeleteTarget = 
  | { type: 'single'; job: Job }
  | { type: 'batch'; jobIds: string[] }
  | { type: 'clear_all'; count: number }
  | { type: 'clear_filtered'; filter: string; count: number };

interface ConfirmDeleteModalProps {
  target: DeleteTarget | null;
  onClose: () => void;
  onConfirm: () => void;
  loading?: boolean;
}

export const ConfirmDeleteModal: React.FC<ConfirmDeleteModalProps> = ({
  target,
  onClose,
  onConfirm,
  loading = false,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && target) {
        onClose();
      } else if (e.key === 'Enter' && target && !loading) {
        onConfirm();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [target, onClose, onConfirm, loading]);

  if (!target) return null;

  let title = 'Delete Analysis Run?';
  let description = 'This action cannot be undone. Associated data and reports will be permanently deleted.';
  let confirmLabel = 'Delete Run';

  if (target.type === 'single') {
    title = `Delete ${target.job.ticker} Analysis?`;
    description = `Permanently delete the analysis run for ${target.job.ticker} (${target.job.trade_date}) along with its generated events and markdown reports.`;
    confirmLabel = 'Delete Run';
  } else if (target.type === 'batch') {
    title = `Delete ${target.jobIds.length} Analysis Runs?`;
    description = `Permanently delete ${target.jobIds.length} selected analysis runs and purge their report files.`;
    confirmLabel = `Delete ${target.jobIds.length} Runs`;
  } else if (target.type === 'clear_all') {
    title = `Clear Finished Analysis History?`;
    description = `Permanently remove all completed and failed analysis runs (${target.count} total). Any active running jobs will NOT be affected.`;
    confirmLabel = `Clear ${target.count} Finished Runs`;
  } else if (target.type === 'clear_filtered') {
    title = `Clear ${target.filter.toUpperCase()} Runs?`;
    description = `Permanently remove all ${target.count} ${target.filter} analysis run(s) from your terminal history.`;
    confirmLabel = `Clear All ${target.filter.charAt(0).toUpperCase() + target.filter.slice(1)}`;
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm animate-fadeIn">
      <div 
        className="w-full max-w-md bg-dark-900 border border-dark-700/90 rounded-2xl shadow-2xl overflow-hidden flex flex-col animate-slide-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 flex items-start space-x-4 border-b border-dark-700/60 bg-dark-850/40">
          <div className="w-10 h-10 rounded-xl bg-brand-rose/15 border border-brand-rose/30 flex items-center justify-center text-brand-rose shrink-0 shadow-lg shadow-brand-rose/10">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-bold text-slate-100 font-mono tracking-tight">
              {title}
            </h3>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              {description}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-colors shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Details Card if single job */}
        {target.type === 'single' && (
          <div className="px-5 py-3 bg-dark-950/60 border-b border-dark-700/40 font-mono text-xs flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="font-bold text-slate-200">{target.job.ticker}</span>
              <span className="text-[10px] text-slate-400 uppercase bg-dark-800 px-1.5 py-0.5 rounded border border-dark-700">
                {target.job.asset_type}
              </span>
            </div>
            <span className="text-slate-400 text-[11px]">{target.job.trade_date}</span>
            <span className="text-[11px] capitalize text-slate-300">
              {target.job.status} ({target.job.progress}%)
            </span>
          </div>
        )}

        {/* Actions Footer */}
        <div className="p-4 bg-dark-950/40 flex items-center justify-end space-x-3">
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="px-4 py-2 rounded-xl border border-dark-700 text-xs font-semibold text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-brand-rose to-rose-600 hover:from-rose-500 hover:to-brand-rose text-white font-bold text-xs shadow-lg shadow-brand-rose/25 transition-all active:scale-95 disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
