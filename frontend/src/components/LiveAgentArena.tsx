import React, { useEffect, useRef, useState } from 'react';
import { Job, JobEvent } from '../types';
import { 
  TrendingUp, 
  TrendingDown, 
  ShieldAlert, 
  Briefcase, 
  Award, 
  Activity, 
  Terminal, 
  CheckCircle2, 
  Clock, 
  Sparkles,
  Download,
  Check
} from 'lucide-react';
import { downloadReportMarkdown } from '../services/api';

interface LiveAgentArenaProps {
  job: Job | null;
  events: JobEvent[];
  onViewReport: () => void;
}

const LiveAgentArenaComponent: React.FC<LiveAgentArenaProps> = ({ job, events, onViewReport }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [downloaded, setDownloaded] = useState(false);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  if (!job) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-dark-950">
        <div className="w-16 h-16 rounded-2xl bg-dark-850 border border-dark-700 flex items-center justify-center text-slate-500 mb-4 shadow-xl">
          <Terminal className="w-8 h-8 text-brand-cyan/60" />
        </div>
        <h3 className="text-base font-bold text-slate-200">No Active Analysis Selected</h3>
        <p className="text-xs text-slate-400 max-w-sm mt-1">
          Select a running or completed analysis from the sidebar, or launch a new multi-agent session.
        </p>
      </div>
    );
  }

  // Calculate current active node stages
  const getStageState = (stageName: string) => {
    const isCompleted = job.status === 'completed';
    const current = job.current_stage.toLowerCase();
    
    if (stageName === 'analysts') {
      if (job.progress > 50 || isCompleted) return 'completed';
      if (job.progress >= 10) return 'running';
      return 'pending';
    }
    if (stageName === 'research') {
      if (job.progress > 72 || isCompleted) return 'completed';
      if (job.progress >= 50) return 'running';
      return 'pending';
    }
    if (stageName === 'trader') {
      if (job.progress > 78 || isCompleted) return 'completed';
      if (job.progress >= 72) return 'running';
      return 'pending';
    }
    if (stageName === 'risk') {
      if (job.progress > 92 || isCompleted) return 'completed';
      if (job.progress >= 78) return 'running';
      return 'pending';
    }
    if (stageName === 'portfolio') {
      if (isCompleted) return 'completed';
      if (job.progress >= 92) return 'running';
      return 'pending';
    }
    return 'pending';
  };

  const getSpeakerStyle = (speaker: string) => {
    const s = speaker.toLowerCase();
    if (s.includes('bull')) {
      return {
        badge: 'bg-brand-emerald/15 text-brand-emerald border-brand-emerald/30',
        border: 'border-l-brand-emerald',
        icon: <TrendingUp className="w-3.5 h-3.5 text-brand-emerald" />
      };
    }
    if (s.includes('bear')) {
      return {
        badge: 'bg-brand-rose/15 text-brand-rose border-brand-rose/30',
        border: 'border-l-brand-rose',
        icon: <TrendingDown className="w-3.5 h-3.5 text-brand-rose" />
      };
    }
    if (s.includes('aggressive')) {
      return {
        badge: 'bg-brand-amber/15 text-brand-amber border-brand-amber/30',
        border: 'border-l-brand-amber',
        icon: <Sparkles className="w-3.5 h-3.5 text-brand-amber" />
      };
    }
    if (s.includes('conservative')) {
      return {
        badge: 'bg-brand-indigo/15 text-brand-indigo border-brand-indigo/30',
        border: 'border-l-brand-indigo',
        icon: <ShieldAlert className="w-3.5 h-3.5 text-brand-indigo" />
      };
    }
    return {
      badge: 'bg-brand-cyan/15 text-brand-cyan border-brand-cyan/30',
      border: 'border-l-brand-cyan',
      icon: <Activity className="w-3.5 h-3.5 text-brand-cyan" />
    };
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-dark-950 overflow-hidden">
      {/* Top Banner: Active Job Context */}
      <div className="px-6 py-3.5 border-b border-dark-700/60 bg-dark-900 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="px-2.5 py-1 rounded bg-dark-800 border border-dark-700 text-sm font-mono font-bold text-slate-100">
            {job.ticker}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-200">
                Multi-Agent Pipeline
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                Date: {job.trade_date}
              </span>
              <span className="text-[10px] font-mono uppercase px-1 py-0.5 rounded bg-dark-800 text-brand-cyan border border-brand-cyan/20">
                {job.llm_provider} / {job.deep_think_llm}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono mt-0.5">
              Status: <span className="text-brand-cyan font-semibold">{job.current_stage}</span> ({job.progress}%)
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {job.status === 'completed' && (
            <>
              <button
                onClick={() => {
                  downloadReportMarkdown(job.id, job.ticker, job.trade_date, 'complete');
                  setDownloaded(true);
                  setTimeout(() => setDownloaded(false), 2000);
                }}
                title="Download Final Markdown (.md) Report"
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-700 border border-brand-emerald/40 text-brand-emerald font-mono text-xs transition-colors active:scale-95 shadow-sm"
              >
                {downloaded ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Download className="w-3.5 h-3.5" />}
                <span>{downloaded ? 'Downloaded' : 'Download MD'}</span>
              </button>

              <button
                onClick={onViewReport}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-brand-emerald text-dark-950 font-bold text-xs shadow-md shadow-brand-emerald/20 hover:bg-emerald-400 transition-colors"
              >
                <Award className="w-3.5 h-3.5" />
                <span>Inspect Final Report</span>
              </button>
            </>
          )}

          <label className="flex items-center space-x-1.5 text-xs text-slate-400 font-mono cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded bg-dark-800 border-dark-700 text-brand-cyan focus:ring-0"
            />
            <span>Auto-scroll</span>
          </label>
        </div>
      </div>

      {/* Pipeline Stage Tracker */}
      <div className="px-6 py-3 border-b border-dark-700/40 bg-dark-900/40 grid grid-cols-5 gap-2 text-xs font-mono">
        {[
          { key: 'analysts', label: '1. Analyst Team', sub: 'Market/News/Fund' },
          { key: 'research', label: '2. Bull vs Bear', sub: 'Debate Arena' },
          { key: 'trader', label: '3. Trader Desk', sub: 'Action & Levels' },
          { key: 'risk', label: '4. Risk Mgmt', sub: '3-Way Scrutiny' },
          { key: 'portfolio', label: '5. Portfolio Decision', sub: 'Final Verdict' },
        ].map((st) => {
          const state = getStageState(st.key);
          return (
            <div
              key={st.key}
              className={`p-2 rounded-lg border transition-all ${
                state === 'running'
                  ? 'bg-brand-cyan/10 border-brand-cyan/50 text-brand-cyan shadow-sm shadow-brand-cyan/10 animate-pulse'
                  : state === 'completed'
                  ? 'bg-dark-850 border-brand-emerald/40 text-slate-200'
                  : 'bg-dark-900/40 border-dark-800 text-slate-500'
              }`}
            >
              <div className="flex items-center justify-between mb-0.5">
                <span className="font-bold text-[11px] truncate">{st.label}</span>
                {state === 'completed' ? (
                  <CheckCircle2 className="w-3 h-3 text-brand-emerald shrink-0" />
                ) : state === 'running' ? (
                  <Activity className="w-3 h-3 text-brand-cyan animate-spin shrink-0" />
                ) : (
                  <Clock className="w-3 h-3 text-slate-600 shrink-0" />
                )}
              </div>
              <div className="text-[10px] text-slate-400 truncate">{st.sub}</div>
            </div>
          );
        })}
      </div>

      {/* Main Stream Transcript & Arena Cards */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-4 font-sans">
        {events.length === 0 ? (
          <div className="text-center py-20 text-slate-500 text-xs font-mono flex flex-col items-center">
            <Activity className="w-6 h-6 animate-pulse mb-2 text-brand-cyan" />
            <span>Connecting to agent deliberation stream...</span>
          </div>
        ) : (
          events.map((ev, idx) => {
            const data = ev.data || {};

            // 1. Stage Change
            if (ev.event_type === 'stage_change') {
              return (
                <div key={ev.id ?? idx} className="flex items-center space-x-3 text-xs font-mono text-slate-400 py-1">
                  <div className="h-px flex-1 bg-dark-700/60" />
                  <span className="px-2.5 py-0.5 rounded bg-dark-800 border border-dark-700 text-brand-cyan">
                    STAGE: {data.stage || data.message}
                  </span>
                  <div className="h-px flex-1 bg-dark-700/60" />
                </div>
              );
            }

            // 2. Analyst Completed
            if (ev.event_type === 'agent_completed') {
              return (
                <div key={ev.id ?? idx} className="glass-panel p-3.5 rounded-lg border-l-4 border-l-brand-cyan/80">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center space-x-2">
                      <CheckCircle2 className="w-4 h-4 text-brand-cyan" />
                      <span className="font-bold text-xs text-slate-100">{data.agent} Completed</span>
                    </div>
                    <span className="text-[10px] font-mono text-slate-500">{ev.timestamp.split('T')[1]?.slice(0, 8)}</span>
                  </div>
                  <p className="text-xs text-slate-300 font-mono leading-relaxed bg-dark-900/60 p-2.5 rounded border border-dark-700/40">
                    {data.preview}
                  </p>
                </div>
              );
            }

            // 3. Debate Speeches (Bull / Bear / Risk)
            if (ev.event_type === 'debate_speech' || ev.event_type === 'risk_speech') {
              const style = getSpeakerStyle(data.speaker || '');
              return (
                <div key={ev.id ?? idx} className={`glass-panel p-4 rounded-xl border-l-4 ${style.border}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <span className={`flex items-center space-x-1 text-xs font-bold font-mono px-2 py-0.5 rounded-md border ${style.badge}`}>
                        {style.icon}
                        <span>{data.speaker}</span>
                      </span>
                      {data.round && (
                        <span className="text-[10px] font-mono text-slate-400">
                          (Round {data.round})
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-slate-500">{ev.timestamp.split('T')[1]?.slice(0, 8)}</span>
                  </div>
                  <div className="text-xs text-slate-200 leading-relaxed whitespace-pre-line pl-1">
                    {data.content}
                  </div>
                </div>
              );
            }

            // 4. Research Plan
            if (ev.event_type === 'research_plan') {
              return (
                <div key={ev.id ?? idx} className="p-4 rounded-xl bg-dark-850/90 border border-brand-cyan/40 shadow-lg">
                  <div className="flex items-center space-x-2 mb-2 text-brand-cyan text-xs font-bold font-mono">
                    <Briefcase className="w-4 h-4" />
                    <span>RESEARCH MANAGER SYNTHESIS</span>
                  </div>
                  <div className="text-xs text-slate-200 whitespace-pre-line leading-relaxed">
                    {data.plan}
                  </div>
                </div>
              );
            }

            // 5. Trader Proposal
            if (ev.event_type === 'trader_proposal') {
              return (
                <div key={ev.id ?? idx} className="p-4 rounded-xl bg-gradient-to-br from-dark-850 to-dark-800 border border-brand-amber/40 shadow-lg">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2 text-brand-amber text-xs font-bold font-mono">
                      <Terminal className="w-4 h-4" />
                      <span>TRADER TRANSACTION PROPOSAL</span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-200 whitespace-pre-line leading-relaxed font-mono bg-dark-900/80 p-3 rounded-lg border border-dark-700">
                    {data.proposal}
                  </div>
                </div>
              );
            }

            // 6. Final Decision
            if (ev.event_type === 'final_decision') {
              return (
                <div key={ev.id ?? idx} className="p-5 rounded-2xl bg-gradient-to-tr from-dark-850 to-dark-800 border-2 border-brand-emerald shadow-2xl glow-emerald">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center space-x-2 text-brand-emerald text-sm font-bold font-mono uppercase tracking-wider">
                      <Award className="w-5 h-5" />
                      <span>FINAL PORTFOLIO MANAGER VERDICT</span>
                    </div>
                    <span className="text-xs font-bold font-mono px-3 py-1 rounded-full bg-brand-emerald text-dark-950 shadow">
                      RECOMMENDATION: {data.rating}
                    </span>
                  </div>
                  <div className="text-xs text-slate-100 whitespace-pre-line leading-relaxed">
                    {data.decision}
                  </div>
                </div>
              );
            }

            // Fallback generic event
            return (
              <div key={ev.id ?? idx} className="text-[11px] font-mono text-slate-500 py-0.5">
                [{ev.timestamp.split('T')[1]?.slice(0, 8)}] {ev.event_type}: {JSON.stringify(data)}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export const LiveAgentArena = React.memo(LiveAgentArenaComponent);
