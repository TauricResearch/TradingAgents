import React, { useEffect, useState } from 'react';
import { MemoryEntry } from '../types';
import { fetchMemoryLog } from '../services/api';
import { Database, Search, Award, RefreshCw, BookOpen } from 'lucide-react';

const MemoryExplorerComponent: React.FC = () => {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [tickerFilter, setTickerFilter] = useState('');

  const loadMemory = async () => {
    setLoading(true);
    try {
      const data = await fetchMemoryLog(tickerFilter.trim() || undefined);
      setEntries(data.entries || []);
    } catch (err) {
      console.error('Failed to load memory log:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMemory();
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full bg-dark-950 overflow-hidden">
      {/* Header */}
      <div className="p-3 sm:p-6 border-b border-dark-700/60 bg-dark-900 flex flex-col md:flex-row md:items-center justify-between gap-3 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-brand-amber/10 border border-brand-amber/30 flex items-center justify-center text-brand-amber shrink-0">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm sm:text-base font-bold text-slate-100">Trading Memory & Reflection Log</h2>
            <p className="text-[11px] sm:text-xs text-slate-400">
              Cross-run knowledge base: past decisions, market outcomes, and lessons
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 sm:space-x-3">
          <div className="relative flex-1 sm:flex-initial">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Search ticker..."
              value={tickerFilter}
              onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && loadMemory()}
              className="w-full sm:w-48 bg-dark-850 border border-dark-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-amber"
            />
          </div>

          <button
            onClick={loadMemory}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-750 border border-dark-700 text-xs font-mono text-slate-300 shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Reload</span>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-6 space-y-4 font-sans">
        {loading ? (
          <div className="text-center py-20 text-xs font-mono text-slate-500">
            Reading memory store...
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-20 text-xs font-mono text-slate-500 flex flex-col items-center">
            <BookOpen className="w-8 h-8 text-slate-600 mb-2" />
            <span>No memory log entries found. Complete an analysis run to generate memories!</span>
          </div>
        ) : (
          entries.map((entry, idx) => (
            <div
              key={idx}
              className="glass-panel p-5 rounded-xl border border-dark-700/80 space-y-3"
            >
              <div className="flex items-center justify-between border-b border-dark-700/60 pb-2.5">
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-sm font-mono text-slate-100">
                    {entry.ticker || 'UNKNOWN'}
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    Trade Date: {entry.trade_date || 'N/A'}
                  </span>
                </div>

                <div className="flex items-center space-x-2">
                  {entry.rating && (
                    <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-dark-800 border border-dark-700 text-brand-amber">
                      {entry.rating}
                    </span>
                  )}
                  {entry.pending ? (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-brand-cyan/10 text-brand-cyan border border-brand-cyan/30">
                      OUTCOME PENDING
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-brand-emerald/10 text-brand-emerald border border-brand-emerald/30">
                      RESOLVED
                    </span>
                  )}
                </div>
              </div>

              {entry.decision && (
                <div>
                  <h4 className="text-[11px] font-mono font-bold text-slate-400 uppercase mb-1">
                    Recorded Decision:
                  </h4>
                  <div className="text-xs text-slate-300 font-mono bg-dark-900/60 p-3 rounded-lg border border-dark-700/40 whitespace-pre-line">
                    {entry.decision}
                  </div>
                </div>
              )}

              {entry.reflection && (
                <div>
                  <h4 className="text-[11px] font-mono font-bold text-brand-amber uppercase mb-1 flex items-center space-x-1">
                    <Award className="w-3.5 h-3.5" />
                    <span>Reflection & Lessons Learned (Point-in-Time Verified):</span>
                  </h4>
                  <div className="text-xs text-slate-200 bg-brand-amber/5 p-3 rounded-lg border border-brand-amber/20 whitespace-pre-line leading-relaxed">
                    {entry.reflection}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export const MemoryExplorer = React.memo(MemoryExplorerComponent);
