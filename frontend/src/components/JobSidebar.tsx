import React, { useState, useMemo } from 'react';
import { Job, JobStatus } from '../types';
import { 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Search, 
  RefreshCw, 
  Layers, 
  ChevronRight, 
  XSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Trash2,
  CheckSquare,
  Square,
  X,
  Inbox
} from 'lucide-react';
import { toast } from './Toast';
import { ConfirmDeleteModal, DeleteTarget } from './ConfirmDeleteModal';

interface JobSidebarProps {
  jobs: Job[];
  selectedJobId: string | null;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onSelectJob: (jobId: string) => void;
  onCancelJob: (jobId: string) => void;
  onDeleteJob?: (jobId: string, force?: boolean) => void;
  onBatchDeleteJobs?: (jobIds: string[], force?: boolean) => void;
  onClearJobsHistory?: (status?: string, allFinished?: boolean) => void;
  onRefreshJobs: () => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

const JobSidebarComponent: React.FC<JobSidebarProps> = ({
  jobs,
  selectedJobId,
  isCollapsed,
  onToggleCollapse,
  onSelectJob,
  onCancelJob,
  onDeleteJob,
  onBatchDeleteJobs,
  onClearJobsHistory,
  onRefreshJobs,
  isMobileOpen = false,
  onCloseMobile,
}) => {
  const [filter, setFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  const finishedJobsCount = useMemo(() => {
    return jobs.filter((j) => j.status === 'completed' || j.status === 'failed' || j.status === 'cancelled').length;
  }, [jobs]);

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const matchesFilter = filter === 'all' ? true : job.status === filter;
      const matchesSearch =
        job.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
        job.trade_date.includes(searchTerm);
      return matchesFilter && matchesSearch;
    });
  }, [jobs, filter, searchTerm]);

  const getStatusBadge = (status: JobStatus) => {
    switch (status) {
      case 'running':
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono text-brand-cyan bg-brand-cyan/10 px-1.5 py-0.5 rounded border border-brand-cyan/30 animate-pulse">
            <RefreshCw className="w-2.5 h-2.5 animate-spin" />
            <span>RUNNING</span>
          </span>
        );
      case 'completed':
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono text-brand-emerald bg-brand-emerald/10 px-1.5 py-0.5 rounded border border-brand-emerald/30">
            <CheckCircle2 className="w-2.5 h-2.5" />
            <span>COMPLETED</span>
          </span>
        );
      case 'failed':
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono text-brand-rose bg-brand-rose/10 px-1.5 py-0.5 rounded border border-brand-rose/30">
            <XCircle className="w-2.5 h-2.5" />
            <span>FAILED</span>
          </span>
        );
      case 'cancelled':
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono text-slate-400 bg-dark-800 px-1.5 py-0.5 rounded border border-dark-700">
            <XSquare className="w-2.5 h-2.5" />
            <span>CANCELLED</span>
          </span>
        );
      default:
        return (
          <span className="flex items-center space-x-1 text-[11px] font-mono text-brand-amber bg-brand-amber/10 px-1.5 py-0.5 rounded border border-brand-amber/30">
            <Clock className="w-2.5 h-2.5" />
            <span>QUEUED</span>
          </span>
        );
    }
  };

  const getSignalBadge = (signal?: string | null) => {
    if (!signal) return null;
    const s = signal.toUpperCase();
    let color = 'bg-dark-700 text-slate-300 border-dark-600';
    if (s.includes('BUY') || s.includes('OVERWEIGHT')) {
      color = 'bg-brand-emerald/20 text-brand-emerald border-brand-emerald/40';
    } else if (s.includes('SELL') || s.includes('UNDERWEIGHT')) {
      color = 'bg-brand-rose/20 text-brand-rose border-brand-rose/40';
    } else if (s.includes('HOLD')) {
      color = 'bg-brand-amber/20 text-brand-amber border-brand-amber/40';
    }

    return (
      <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${color}`}>
        {signal}
      </span>
    );
  };

  const handleToggleBatchItem = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedBatchIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const allFilteredSelected =
    filteredJobs.length > 0 && filteredJobs.every((j) => selectedBatchIds.includes(j.id));

  const handleSelectAllFiltered = () => {
    if (allFilteredSelected) {
      const filteredIdSet = new Set(filteredJobs.map((j) => j.id));
      setSelectedBatchIds((prev) => prev.filter((id) => !filteredIdSet.has(id)));
    } else {
      const currentSet = new Set(selectedBatchIds);
      filteredJobs.forEach((j) => currentSet.add(j.id));
      setSelectedBatchIds(Array.from(currentSet));
    }
  };

  const handleConfirmDelete = () => {
    if (!deleteTarget) return;

    if (deleteTarget.type === 'single') {
      if (onDeleteJob) {
        onDeleteJob(deleteTarget.job.id, deleteTarget.job.status === 'running');
        toast.success(`Deleted ${deleteTarget.job.ticker} analysis`);
      }
    } else if (deleteTarget.type === 'batch') {
      if (onBatchDeleteJobs) {
        onBatchDeleteJobs(deleteTarget.jobIds, false);
        setSelectedBatchIds([]);
        setIsBatchMode(false);
      }
    } else if (deleteTarget.type === 'clear_all') {
      if (onClearJobsHistory) {
        onClearJobsHistory(undefined, true);
      }
    } else if (deleteTarget.type === 'clear_filtered') {
      if (onClearJobsHistory) {
        onClearJobsHistory(deleteTarget.filter, false);
      }
    }

    setDeleteTarget(null);
  };

  const handleJobCardClick = (jobId: string) => {
    onSelectJob(jobId);
    if (onCloseMobile) {
      onCloseMobile();
    }
  };

  // 1. Collapsed Desktop Rail View
  if (isCollapsed) {
    return (
      <aside className="hidden lg:flex w-16 border-r border-dark-700/60 bg-dark-900/90 flex-col items-center py-3 h-full select-none transition-all duration-300 z-10 shrink-0">
        <button
          onClick={onToggleCollapse}
          title="Expand Sidebar"
          className="p-2 rounded-xl bg-dark-800 hover:bg-dark-750 text-slate-400 hover:text-brand-cyan transition-colors mb-2 border border-dark-700/80"
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>

        <button
          onClick={onRefreshJobs}
          title="Refresh runs"
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-dark-800 transition-colors mb-3"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>

        <div className="w-8 h-px bg-dark-700/80 mb-3" />

        <div className="flex-1 w-full overflow-y-auto px-2 space-y-2 flex flex-col items-center no-scrollbar">
          {jobs.slice(0, 30).map((job) => {
            const isSelected = selectedJobId === job.id;
            return (
              <button
                key={job.id}
                onClick={() => onSelectJob(job.id)}
                title={`${job.ticker} (${job.trade_date})\nStatus: ${job.status.toUpperCase()}\nStage: ${job.current_stage}`}
                className={`w-11 h-11 rounded-xl flex flex-col items-center justify-center relative border transition-all text-center ${
                  isSelected
                    ? 'bg-dark-800 border-brand-cyan shadow-md shadow-brand-cyan/20 text-brand-cyan'
                    : 'bg-dark-850/70 border-dark-700 text-slate-300 hover:border-slate-500 hover:bg-dark-800'
                }`}
              >
                <span className="text-[10px] font-bold font-mono tracking-tighter truncate max-w-[36px]">
                  {job.ticker.split('-')[0].slice(0, 4)}
                </span>
                <span
                  className={`w-1.5 h-1.5 rounded-full mt-0.5 ${
                    job.status === 'running'
                      ? 'bg-brand-cyan animate-ping'
                      : job.status === 'completed'
                      ? 'bg-brand-emerald'
                      : job.status === 'failed'
                      ? 'bg-brand-rose'
                      : 'bg-slate-500'
                  }`}
                />
              </button>
            );
          })}
        </div>
      </aside>
    );
  }

  // 2. Full Sidebar View
  return (
    <>
      {/* Mobile Drawer Backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 bg-dark-950/80 backdrop-blur-sm z-40 lg:hidden transition-opacity"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={`${
          isMobileOpen
            ? 'fixed inset-y-0 left-0 z-50 flex shadow-2xl'
            : 'hidden lg:flex'
        } w-80 max-w-[85vw] lg:max-w-none border-r border-dark-700/60 bg-dark-900 flex-col h-full transition-all duration-300 select-none shrink-0`}
      >
        {/* Search and Header */}
        <div className="p-3.5 border-b border-dark-700/60 space-y-2.5 shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300 tracking-wider uppercase font-mono">
              <Layers className="w-4 h-4 text-brand-cyan" />
              <span>Runs ({jobs.length})</span>
            </div>

            <div className="flex items-center space-x-1">
              {/* Batch Mode Toggle */}
              <button
                onClick={() => {
                  setIsBatchMode(!isBatchMode);
                  setSelectedBatchIds([]);
                }}
                title={isBatchMode ? 'Exit Selection Mode' : 'Select Multiple Runs'}
                className={`p-1.5 rounded-lg transition-colors ${
                  isBatchMode
                    ? 'bg-brand-cyan text-dark-950 font-bold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                }`}
              >
                <CheckSquare className="w-3.5 h-3.5" />
              </button>

              {/* Clear All Finished Runs Action in Header Toolbar */}
              {onClearJobsHistory && finishedJobsCount > 0 && (
                <button
                  onClick={() => setDeleteTarget({ type: 'clear_all', count: finishedJobsCount })}
                  title={`Clear finished history (${finishedJobsCount} runs)`}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-brand-rose hover:bg-brand-rose/10 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}

              <button
                onClick={onRefreshJobs}
                title="Refresh job list"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>

              {/* Desktop Collapse Button */}
              <button
                onClick={onToggleCollapse}
                title="Collapse sidebar (64px rail)"
                className="hidden lg:block p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
              >
                <PanelLeftClose className="w-3.5 h-3.5" />
              </button>

              {/* Mobile Close Drawer Button */}
              {onCloseMobile && (
                <button
                  onClick={onCloseMobile}
                  title="Close sidebar drawer"
                  className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* Search Bar with clear button */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              id="job-search-input"
              type="text"
              placeholder="Search ticker or date... (/)"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-dark-850 border border-dark-700/80 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-cyan/60 transition-colors font-mono"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Clean Filter Pills (Pure Filters Only - No destructive button mixed in!) */}
          <div className="flex items-center space-x-1 overflow-x-auto no-scrollbar">
            {['all', 'running', 'completed', 'failed'].map((st) => (
              <button
                key={st}
                onClick={() => setFilter(st)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium capitalize transition-all shrink-0 ${
                  filter === st
                    ? 'bg-dark-700 text-brand-cyan font-semibold border border-dark-600 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Contextual Action Bar when viewing filtered lists or finished items */}
          {onClearJobsHistory && filteredJobs.length > 0 && filter !== 'running' && (
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 px-1 pt-0.5 border-t border-dark-800/80">
              <span>{filteredJobs.length} {filter === 'all' ? 'total' : filter} run(s)</span>
              <button
                onClick={() => {
                  if (filter === 'all') {
                    setDeleteTarget({ type: 'clear_all', count: finishedJobsCount });
                  } else {
                    setDeleteTarget({ type: 'clear_filtered', filter, count: filteredJobs.length });
                  }
                }}
                className="flex items-center space-x-1 text-slate-400 hover:text-brand-rose transition-colors py-0.5 px-1.5 rounded hover:bg-brand-rose/10"
              >
                <Trash2 className="w-3 h-3" />
                <span>Clear {filter === 'all' ? 'Finished' : filter}</span>
              </button>
            </div>
          )}

          {/* Batch Mode Toolbar */}
          {isBatchMode && (
            <div className="p-2.5 rounded-xl bg-dark-850 border border-brand-cyan/40 flex items-center justify-between text-xs font-mono animate-fadeIn">
              <button
                onClick={handleSelectAllFiltered}
                className="flex items-center space-x-1.5 text-slate-300 hover:text-white"
              >
                {allFilteredSelected ? (
                  <CheckSquare className="w-3.5 h-3.5 text-brand-cyan" />
                ) : (
                  <Square className="w-3.5 h-3.5 text-slate-400" />
                )}
                <span>
                  {selectedBatchIds.length}/{filteredJobs.length} selected
                </span>
              </button>

              <div className="flex items-center space-x-1.5">
                <button
                  disabled={selectedBatchIds.length === 0}
                  onClick={() => setDeleteTarget({ type: 'batch', jobIds: selectedBatchIds })}
                  className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-brand-rose/20 text-brand-rose border border-brand-rose/40 hover:bg-brand-rose hover:text-white disabled:opacity-40 transition-colors font-semibold"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>Delete</span>
                </button>
                <button
                  onClick={() => {
                    setIsBatchMode(false);
                    setSelectedBatchIds([]);
                  }}
                  className="p-1 text-slate-400 hover:text-slate-200"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Jobs List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {filteredJobs.length === 0 ? (
            <div className="text-center py-12 px-4 text-xs text-slate-500 font-mono flex flex-col items-center">
              <Inbox className="w-8 h-8 text-slate-600 mb-2" />
              <span>No analysis runs match this criteria.</span>
              {(searchTerm || filter !== 'all') && (
                <button
                  onClick={() => {
                    setSearchTerm('');
                    setFilter('all');
                  }}
                  className="mt-3 text-brand-cyan hover:underline text-[11px]"
                >
                  Reset all filters
                </button>
              )}
            </div>
          ) : (
            filteredJobs.map((job) => {
              const isSelected = selectedJobId === job.id;
              const isBatchChecked = selectedBatchIds.includes(job.id);

              return (
                <div
                  key={job.id}
                  onClick={() => (isBatchMode ? handleToggleBatchItem(job.id, {} as any) : handleJobCardClick(job.id))}
                  className={`p-3 rounded-xl border cursor-pointer transition-all relative ${
                    isSelected && !isBatchMode
                      ? 'bg-dark-800 border-brand-cyan/60 shadow-md shadow-brand-cyan/10 ring-1 ring-brand-cyan/20'
                      : 'bg-dark-850/60 border-dark-700/60 hover:bg-dark-800/80 hover:border-dark-600'
                  } ${isBatchChecked ? 'ring-1 ring-brand-cyan bg-brand-cyan/5' : ''}`}
                >
                  {/* Top Row: Checkbox/Ticker & Status */}
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center space-x-2">
                      {isBatchMode && (
                        <div
                          onClick={(e) => handleToggleBatchItem(job.id, e)}
                          className="p-0.5 rounded hover:bg-dark-700 cursor-pointer"
                        >
                          {isBatchChecked ? (
                            <CheckSquare className="w-4 h-4 text-brand-cyan" />
                          ) : (
                            <Square className="w-4 h-4 text-slate-500" />
                          )}
                        </div>
                      )}
                      <span className="font-bold text-sm font-mono tracking-wide text-slate-100">
                        {job.ticker}
                      </span>
                      <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-dark-700 text-slate-400">
                        {job.asset_type}
                      </span>
                    </div>

                    <div className="flex items-center space-x-1.5">
                      {getStatusBadge(job.status)}
                    </div>
                  </div>

                  {/* Subtitle: Date & Current Stage */}
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono mb-2">
                    <span>{job.trade_date}</span>
                    <span className="truncate max-w-[140px] text-slate-300" title={job.current_stage}>
                      {job.current_stage}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-dark-950 rounded-full h-1.5 overflow-hidden mb-2">
                    <div
                      className={`h-full transition-all duration-500 ${
                        job.status === 'completed'
                          ? 'bg-brand-emerald'
                          : job.status === 'failed'
                          ? 'bg-brand-rose'
                          : 'bg-gradient-to-r from-brand-cyan to-brand-emerald'
                      }`}
                      style={{ width: `${Math.max(job.progress, 5)}%` }}
                    />
                  </div>

                  {/* Bottom Row: Signal & Clean Actions (Zero layout shift!) */}
                  <div className="flex items-center justify-between pt-1.5 border-t border-dark-700/40">
                    <div>{getSignalBadge(job.decision_signal)}</div>

                    <div className="flex items-center space-x-1.5">
                      {/* Cancel action if running */}
                      {job.status === 'running' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onCancelJob(job.id);
                            toast.info(`Cancelling ${job.ticker} analysis...`);
                          }}
                          className="text-[10px] font-mono text-brand-rose hover:text-rose-400 hover:underline px-1 py-0.5"
                        >
                          Cancel
                        </button>
                      )}

                      {/* Clean Single Delete Button -> Triggers ConfirmDeleteModal */}
                      {!isBatchMode && onDeleteJob && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget({ type: 'single', job });
                          }}
                          title={`Delete ${job.ticker} analysis run`}
                          className="p-1 rounded-lg text-slate-500 hover:text-brand-rose hover:bg-brand-rose/10 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}

                      <ChevronRight
                        className={`w-3.5 h-3.5 ${isSelected ? 'text-brand-cyan' : 'text-slate-600'}`}
                      />
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Institutional Destructive Confirmation Modal */}
      <ConfirmDeleteModal
        target={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleConfirmDelete}
      />
    </>
  );
};

export const JobSidebar = React.memo(JobSidebarComponent);
