import React, { useState, useMemo } from 'react';
import { Job, JobStatus } from '../types';
import { 
  PlayCircle, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  Search, 
  RefreshCw, 
  Layers, 
  ChevronRight, 
  XSquare,
  PanelLeftClose,
  PanelLeftOpen
} from 'lucide-react';

interface JobSidebarProps {
  jobs: Job[];
  selectedJobId: string | null;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onSelectJob: (jobId: string) => void;
  onCancelJob: (jobId: string) => void;
  onRefreshJobs: () => void;
}

const JobSidebarComponent: React.FC<JobSidebarProps> = ({
  jobs,
  selectedJobId,
  isCollapsed,
  onToggleCollapse,
  onSelectJob,
  onCancelJob,
  onRefreshJobs,
}) => {
  const [filter, setFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const matchesFilter =
        filter === 'all' ? true : job.status === filter;
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

  if (isCollapsed) {
    return (
      <aside className="w-16 border-r border-dark-700/60 bg-dark-900/80 flex flex-col items-center py-3 h-full select-none transition-all duration-300 z-10">
        {/* Expand button */}
        <button
          onClick={onToggleCollapse}
          title="Expand Sidebar"
          className="p-2 rounded-lg bg-dark-800 hover:bg-dark-750 text-slate-400 hover:text-brand-cyan transition-colors mb-2 border border-dark-700/80"
        >
          <PanelLeftOpen className="w-4 h-4" />
        </button>

        {/* Refresh button */}
        <button
          onClick={onRefreshJobs}
          title="Refresh runs"
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-dark-800 transition-colors mb-3"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>

        <div className="w-8 h-px bg-dark-700/80 mb-3" />

        {/* Compact jobs column */}
        <div className="flex-1 w-full overflow-y-auto px-2 space-y-2 flex flex-col items-center">
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
                {/* Status Dot */}
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

  return (
    <aside className="w-80 border-r border-dark-700/60 bg-dark-900/60 flex flex-col h-full transition-all duration-300">
      {/* Search and Header */}
      <div className="p-3 border-b border-dark-700/60 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs font-semibold text-slate-300 tracking-wider uppercase">
            <Layers className="w-4 h-4 text-brand-cyan" />
            <span>Analysis Runs ({jobs.length})</span>
          </div>
          <div className="flex items-center space-x-1">
            <button
              onClick={onRefreshJobs}
              title="Refresh job list"
              className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onToggleCollapse}
              title="Collapse sidebar (64px rail)"
              className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-dark-800 transition-colors"
            >
              <PanelLeftClose className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>


        {/* Search Bar */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Filter by ticker or date..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-dark-850 border border-dark-700/80 rounded-md pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-cyan/60"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center space-x-1">
          {['all', 'running', 'completed', 'failed'].map((st) => (
            <button
              key={st}
              onClick={() => setFilter(st)}
              className={`px-2 py-1 rounded text-[11px] font-medium capitalize transition-colors ${
                filter === st
                  ? 'bg-dark-700 text-slate-100 font-semibold border border-dark-600'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Jobs List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {filteredJobs.length === 0 ? (
          <div className="text-center py-10 text-xs text-slate-500 font-mono">
            No analysis jobs found.
          </div>
        ) : (
          filteredJobs.map((job) => {
            const isSelected = selectedJobId === job.id;
            return (
              <div
                key={job.id}
                onClick={() => onSelectJob(job.id)}
                className={`p-3 rounded-lg border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-dark-800 border-brand-cyan/50 shadow-md shadow-brand-cyan/5'
                    : 'bg-dark-850/60 border-dark-700/60 hover:bg-dark-800/80 hover:border-dark-600'
                }`}
              >
                {/* Top Row: Ticker & Status */}
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm font-mono tracking-wide text-slate-100">
                      {job.ticker}
                    </span>
                    <span className="text-[10px] uppercase font-mono px-1 py-0.2 rounded bg-dark-700 text-slate-400">
                      {job.asset_type}
                    </span>
                  </div>
                  {getStatusBadge(job.status)}
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

                {/* Bottom Row: Signal & Actions */}
                <div className="flex items-center justify-between pt-1 border-t border-dark-700/40">
                  <div>{getSignalBadge(job.decision_signal)}</div>

                  <div className="flex items-center space-x-2">
                    {job.status === 'running' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onCancelJob(job.id);
                        }}
                        className="text-[10px] font-mono text-brand-rose hover:text-rose-400 hover:underline"
                      >
                        Cancel
                      </button>
                    )}
                    <ChevronRight className={`w-3.5 h-3.5 ${isSelected ? 'text-brand-cyan' : 'text-slate-600'}`} />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};

export const JobSidebar = React.memo(JobSidebarComponent);
