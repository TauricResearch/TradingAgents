import React, { useEffect, useRef, useState, useMemo } from 'react';
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
  Check,
  Copy,
  Filter,
  Layers,
  Cpu
} from 'lucide-react';
import { downloadReportMarkdown } from '../services/api';
import { toast } from './Toast';

interface LiveAgentArenaProps {
  job: Job | null;
  events: JobEvent[];
  onViewReport: () => void;
}

const LiveAgentArenaComponent: React.FC<LiveAgentArenaProps> = ({ job, events, onViewReport }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [downloaded, setDownloaded] = useState(false);
  const [copiedTranscript, setCopiedTranscript] = useState(false);
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [copiedEventId, setCopiedEventId] = useState<string | number | null>(null);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll, stageFilter]);

  // Stage classification logic
  const getStageState = (stageName: string) => {
    if (!job) return 'pending';
    const isCompleted = job.status === 'completed';
    
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
        icon: <TrendingUp className="w-3.5 h-3.5 text-brand-emerald" />,
        glow: 'hover:border-brand-emerald/50'
      };
    }
    if (s.includes('bear')) {
      return {
        badge: 'bg-brand-rose/15 text-brand-rose border-brand-rose/30',
        border: 'border-l-brand-rose',
        icon: <TrendingDown className="w-3.5 h-3.5 text-brand-rose" />,
        glow: 'hover:border-brand-rose/50'
      };
    }
    if (s.includes('aggressive')) {
      return {
        badge: 'bg-brand-amber/15 text-brand-amber border-brand-amber/30',
        border: 'border-l-brand-amber',
        icon: <Sparkles className="w-3.5 h-3.5 text-brand-amber" />,
        glow: 'hover:border-brand-amber/50'
      };
    }
    if (s.includes('conservative')) {
      return {
        badge: 'bg-brand-indigo/15 text-brand-indigo border-brand-indigo/30',
        border: 'border-l-brand-indigo',
        icon: <ShieldAlert className="w-3.5 h-3.5 text-brand-indigo" />,
        glow: 'hover:border-brand-indigo/50'
      };
    }
    return {
      badge: 'bg-brand-cyan/15 text-brand-cyan border-brand-cyan/30',
      border: 'border-l-brand-cyan',
      icon: <Activity className="w-3.5 h-3.5 text-brand-cyan" />,
      glow: 'hover:border-brand-cyan/50'
    };
  };

  // Filter events based on active stage tab
  const filteredEvents = useMemo(() => {
    if (stageFilter === 'all') return events;
    return events.filter((ev) => {
      const et = ev.event_type;
      if (stageFilter === 'analysts') return et === 'agent_completed';
      if (stageFilter === 'research') return et === 'debate_speech' || et === 'research_plan';
      if (stageFilter === 'trader') return et === 'trader_proposal';
      if (stageFilter === 'risk') return et === 'risk_speech';
      if (stageFilter === 'portfolio') return et === 'final_decision';
      return true;
    });
  }, [events, stageFilter]);

  const handleCopyTranscript = () => {
    if (!events || events.length === 0) return;
    const lines = events.map((ev) => {
      const d = ev.data || {};
      const time = ev.timestamp?.split('T')[1]?.slice(0, 8) || '';
      if (ev.event_type === 'stage_change') return `\n### [${time}] STAGE: ${d.stage || d.message}\n`;
      if (ev.event_type === 'agent_completed') return `**[${time}] Analyst (${d.agent}) Completed**\n${d.preview}\n`;
      if (ev.event_type === 'debate_speech') return `**[${time}] ${d.speaker} (Round ${d.round || 1}):**\n${d.content}\n`;
      if (ev.event_type === 'research_plan') return `**[${time}] Research Plan:**\n${d.plan}\n`;
      if (ev.event_type === 'trader_proposal') return `**[${time}] Trader Proposal:**\n${d.proposal}\n`;
      if (ev.event_type === 'risk_speech') return `**[${time}] Risk Debate (${d.speaker}):**\n${d.content}\n`;
      if (ev.event_type === 'final_decision') return `**[${time}] FINAL VERDICT [${d.rating}]:**\n${d.decision}\n`;
      return `[${time}] ${ev.event_type}: ${JSON.stringify(d)}`;
    });

    const header = `# TradingAgents Deliberation Transcript\n**Ticker:** ${job?.ticker || ''} | **Date:** ${job?.trade_date || ''} | **Model:** ${job?.llm_provider || ''}/${job?.deep_think_llm || ''}\n\n---\n\n`;
    navigator.clipboard.writeText(header + lines.join('\n'));
    setCopiedTranscript(true);
    toast.success('Deliberation transcript copied to clipboard!');
    setTimeout(() => setCopiedTranscript(false), 2000);
  };

  const handleCopyEventContent = (id: string | number, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedEventId(id);
    toast.info('Speech excerpt copied to clipboard');
    setTimeout(() => setCopiedEventId(null), 2000);
  };

  if (!job) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-dark-950">
        <div className="w-16 h-16 rounded-2xl bg-dark-850 border border-dark-700 flex items-center justify-center text-slate-500 mb-4 shadow-xl">
          <Terminal className="w-8 h-8 text-brand-cyan/60" />
        </div>
        <h3 className="text-base font-bold text-slate-200">No Active Analysis Selected</h3>
        <p className="text-xs text-slate-400 max-w-sm mt-1">
          Select a running or completed analysis from the sidebar, or launch a new multi-agent session with [N].
        </p>
      </div>
    );
  }

  const pipelineStages = [
    { key: 'analysts', label: '1. Analyst Team', sub: 'Market/News/Fund' },
    { key: 'research', label: '2. Bull vs Bear', sub: 'Debate Arena' },
    { key: 'trader', label: '3. Trader Desk', sub: 'Action & Levels' },
    { key: 'risk', label: '4. Risk Mgmt', sub: '3-Way Scrutiny' },
    { key: 'portfolio', label: '5. Portfolio Decision', sub: 'Final Verdict' },
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-dark-950 overflow-hidden">
      {/* Top Banner: Active Job Context & Actions */}
      <div className="px-3 sm:px-6 py-3 border-b border-dark-700/60 bg-dark-900 flex flex-col md:flex-row md:items-center justify-between gap-3 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="px-3 py-1.5 rounded-lg bg-dark-800 border border-brand-cyan/30 text-base font-mono font-bold text-slate-100 shadow-sm shrink-0">
            {job.ticker}
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span className="text-xs font-semibold text-slate-200">
                Multi-Agent Pipeline
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                Date: {job.trade_date}
              </span>
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-dark-800 text-brand-cyan border border-brand-cyan/20">
                {job.llm_provider} / {job.deep_think_llm}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono mt-0.5 flex items-center space-x-1.5">
              <span>Status:</span>
              <span className="text-brand-cyan font-semibold">{job.current_stage}</span>
              <span className="text-slate-500">({job.progress}%)</span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:space-x-2">
          {events.length > 0 && (
            <button
              onClick={handleCopyTranscript}
              title="Copy entire multi-agent deliberation transcript"
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-750 border border-dark-700 text-slate-300 hover:text-white font-mono text-xs transition-colors active:scale-95 shadow-sm"
            >
              {copiedTranscript ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{copiedTranscript ? 'Copied' : 'Copy Deliberation'}</span>
            </button>
          )}

          {job.status === 'completed' && (
            <>
              <button
                onClick={() => {
                  downloadReportMarkdown(job.id, job.ticker, job.trade_date, 'complete');
                  setDownloaded(true);
                  toast.success('Markdown report downloaded successfully');
                  setTimeout(() => setDownloaded(false), 2000);
                }}
                title="Download Final Markdown (.md) Report"
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-dark-800 hover:bg-dark-750 border border-brand-emerald/40 text-brand-emerald font-mono text-xs transition-colors active:scale-95 shadow-sm"
              >
                {downloaded ? <Check className="w-3.5 h-3.5 text-brand-emerald" /> : <Download className="w-3.5 h-3.5" />}
                <span>{downloaded ? 'Downloaded' : 'Download MD'}</span>
              </button>

              <button
                onClick={onViewReport}
                className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-brand-emerald to-emerald-600 hover:from-emerald-400 hover:to-brand-emerald text-dark-950 font-bold text-xs shadow-md shadow-brand-emerald/20 transition-all active:scale-95"
              >
                <Award className="w-3.5 h-3.5" />
                <span>Inspect Final Report</span>
              </button>
            </>
          )}

          <label className="flex items-center space-x-1.5 text-xs text-slate-400 font-mono cursor-pointer ml-1">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded bg-dark-800 border-dark-700 text-brand-cyan focus:ring-0"
            />
            <span className="hidden sm:inline">Auto-scroll</span>
          </label>
        </div>
      </div>

      {/* Interactive Pipeline Stage Stepper */}
      <div className="px-3 sm:px-6 py-2.5 border-b border-dark-700/40 bg-dark-900/40 overflow-x-auto flex lg:grid lg:grid-cols-5 gap-2 text-xs font-mono no-scrollbar shrink-0">
        {pipelineStages.map((st) => {
          const state = getStageState(st.key);
          const isFilterActive = stageFilter === st.key;

          return (
            <button
              key={st.key}
              onClick={() => setStageFilter(stageFilter === st.key ? 'all' : st.key)}
              title={`Click to ${isFilterActive ? 'show all events' : 'filter transcript to ' + st.label}`}
              className={`p-2 rounded-lg border text-left transition-all min-w-[140px] lg:min-w-0 flex-1 shrink-0 lg:shrink cursor-pointer ${
                isFilterActive
                  ? 'ring-2 ring-brand-cyan bg-brand-cyan/15 border-brand-cyan shadow-md shadow-brand-cyan/20'
                  : state === 'running'
                  ? 'bg-brand-cyan/10 border-brand-cyan/50 text-brand-cyan shadow-sm shadow-brand-cyan/10 animate-pulse'
                  : state === 'completed'
                  ? 'bg-dark-850 border-brand-emerald/40 text-slate-200 hover:border-brand-emerald'
                  : 'bg-dark-900/40 border-dark-800 text-slate-500 hover:border-dark-700'
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
            </button>
          );
        })}
      </div>

      {/* Stage Filter Active Notice */}
      {stageFilter !== 'all' && (
        <div className="px-4 py-1.5 bg-brand-cyan/10 border-b border-brand-cyan/20 flex items-center justify-between text-xs font-mono text-brand-cyan shrink-0">
          <div className="flex items-center space-x-2">
            <Filter className="w-3.5 h-3.5" />
            <span>Filtering by: {pipelineStages.find((s) => s.key === stageFilter)?.label}</span>
          </div>
          <button
            onClick={() => setStageFilter('all')}
            className="text-[11px] underline text-slate-400 hover:text-slate-100"
          >
            Show All Events
          </button>
        </div>
      )}

      {/* Main Stream Transcript & Arena Cards */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 sm:p-6 space-y-4 font-sans">
        {events.length === 0 ? (
          /* Multi-Agent Architecture Topology Display while connecting */
          <div className="py-8 flex flex-col items-center justify-center max-w-2xl mx-auto space-y-6 animate-fadeIn">
            <div className="flex items-center space-x-3 text-xs font-mono text-brand-cyan bg-brand-cyan/10 px-4 py-1.5 rounded-full border border-brand-cyan/30">
              <Activity className="w-4 h-4 animate-spin" />
              <span>Connecting to LangGraph multi-agent deliberation stream...</span>
            </div>

            <div className="w-full glass-panel p-6 rounded-2xl border border-dark-700 space-y-4">
              <div className="flex items-center justify-between border-b border-dark-700/60 pb-3">
                <div className="flex items-center space-x-2">
                  <Cpu className="w-4 h-4 text-brand-emerald" />
                  <span className="text-xs font-bold font-mono uppercase text-slate-200">
                    Active Deliberation Topology
                  </span>
                </div>
                <span className="text-[11px] font-mono text-slate-400">
                  Target: {job.ticker} ({job.trade_date})
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs font-mono">
                <div className="p-3 rounded-xl bg-dark-850/80 border border-dark-700/80 space-y-1">
                  <div className="text-brand-cyan font-bold flex items-center space-x-1.5">
                    <Activity className="w-3.5 h-3.5" />
                    <span>Specialist Analysts (x4)</span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-sans">
                    Ingesting market indicators, financial statements, news, and retail sentiment.
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-dark-850/80 border border-dark-700/80 space-y-1">
                  <div className="text-brand-emerald font-bold flex items-center space-x-1.5">
                    <TrendingUp className="w-3.5 h-3.5" />
                    <span>Adversarial Debate Arena</span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-sans">
                    Bull vs Bear researchers debate secular catalysts versus valuation headwinds.
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-dark-850/80 border border-dark-700/80 space-y-1">
                  <div className="text-brand-amber font-bold flex items-center space-x-1.5">
                    <Terminal className="w-3.5 h-3.5" />
                    <span>Trader Desk Execution</span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-sans">
                    Deriving entry point, stop-loss barrier, price target, and risk/reward ratio.
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-dark-850/80 border border-dark-700/80 space-y-1">
                  <div className="text-brand-indigo font-bold flex items-center space-x-1.5">
                    <Award className="w-3.5 h-3.5" />
                    <span>Risk & Portfolio Decision</span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-sans">
                    3-Way scrutiny with conservative oversight before executive capital allocation.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="text-center py-20 text-xs font-mono text-slate-500">
            No deliberation events found matching this stage filter.
          </div>
        ) : (
          filteredEvents.map((ev, idx) => {
            const data = ev.data || {};
            const eventId = ev.id ?? idx;

            // 1. Stage Change
            if (ev.event_type === 'stage_change') {
              return (
                <div key={eventId} className="flex items-center space-x-3 text-xs font-mono text-slate-400 py-1">
                  <div className="h-px flex-1 bg-dark-700/60" />
                  <span className="px-3 py-1 rounded-full bg-dark-800 border border-dark-700 text-brand-cyan shadow-sm">
                    STAGE: {data.stage || data.message}
                  </span>
                  <div className="h-px flex-1 bg-dark-700/60" />
                </div>
              );
            }

            // 2. Analyst Completed
            if (ev.event_type === 'agent_completed') {
              return (
                <div key={eventId} className="glass-panel p-4 rounded-xl border-l-4 border-l-brand-cyan/80 group relative">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <CheckCircle2 className="w-4 h-4 text-brand-cyan" />
                      <span className="font-bold text-xs text-slate-100">{data.agent} Completed</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleCopyEventContent(eventId, data.preview || '')}
                        title="Copy analyst excerpt"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-opacity"
                      >
                        {copiedEventId === eventId ? <Check className="w-3 h-3 text-brand-emerald" /> : <Copy className="w-3 h-3" />}
                      </button>
                      <span className="text-[10px] font-mono text-slate-500">{ev.timestamp.split('T')[1]?.slice(0, 8)}</span>
                    </div>
                  </div>
                  <p className="text-xs text-slate-300 font-mono leading-relaxed bg-dark-900/60 p-3 rounded-lg border border-dark-700/40">
                    {data.preview}
                  </p>
                </div>
              );
            }

            // 3. Debate Speeches (Bull / Bear / Risk)
            if (ev.event_type === 'debate_speech' || ev.event_type === 'risk_speech') {
              const style = getSpeakerStyle(data.speaker || '');
              return (
                <div key={eventId} className={`glass-panel p-4 sm:p-5 rounded-xl border-l-4 ${style.border} ${style.glow} group relative transition-all`}>
                  <div className="flex items-center justify-between mb-2.5">
                    <div className="flex items-center space-x-2">
                      <span className={`flex items-center space-x-1.5 text-xs font-bold font-mono px-2.5 py-1 rounded-md border ${style.badge}`}>
                        {style.icon}
                        <span>{data.speaker}</span>
                      </span>
                      {data.round && (
                        <span className="text-[10px] font-mono text-slate-400 bg-dark-850 px-2 py-0.5 rounded border border-dark-750">
                          Round {data.round}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleCopyEventContent(eventId, data.content || '')}
                        title="Copy speech text"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-opacity"
                      >
                        {copiedEventId === eventId ? <Check className="w-3 h-3 text-brand-emerald" /> : <Copy className="w-3 h-3" />}
                      </button>
                      <span className="text-[10px] font-mono text-slate-500">{ev.timestamp.split('T')[1]?.slice(0, 8)}</span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-200 leading-relaxed whitespace-pre-line pl-1 font-sans">
                    {data.content}
                  </div>
                </div>
              );
            }

            // 4. Research Plan
            if (ev.event_type === 'research_plan') {
              return (
                <div key={eventId} className="p-4 sm:p-5 rounded-xl bg-dark-850/90 border border-brand-cyan/40 shadow-lg group relative">
                  <div className="flex items-center justify-between mb-2.5">
                    <div className="flex items-center space-x-2 text-brand-cyan text-xs font-bold font-mono">
                      <Briefcase className="w-4 h-4" />
                      <span>RESEARCH MANAGER SYNTHESIS</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleCopyEventContent(eventId, data.plan || '')}
                        title="Copy research synthesis"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-opacity"
                      >
                        {copiedEventId === eventId ? <Check className="w-3 h-3 text-brand-emerald" /> : <Copy className="w-3 h-3" />}
                      </button>
                      <span className="text-[10px] font-mono text-slate-500">{ev.timestamp.split('T')[1]?.slice(0, 8)}</span>
                    </div>
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
                <div key={eventId} className="p-4 sm:p-5 rounded-xl bg-gradient-to-br from-dark-850 to-dark-800 border border-brand-amber/40 shadow-lg group relative">
                  <div className="flex items-center justify-between mb-2.5">
                    <div className="flex items-center space-x-2 text-brand-amber text-xs font-bold font-mono">
                      <Terminal className="w-4 h-4" />
                      <span>TRADER TRANSACTION PROPOSAL</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleCopyEventContent(eventId, data.proposal || '')}
                        title="Copy trade proposal"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-opacity"
                      >
                        {copiedEventId === eventId ? <Check className="w-3 h-3 text-brand-emerald" /> : <Copy className="w-3 h-3" />}
                      </button>
                      <span className="text-[10px] font-mono text-slate-500">{ev.timestamp.split('T')[1]?.slice(0, 8)}</span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-200 whitespace-pre-line leading-relaxed font-mono bg-dark-900/80 p-3.5 rounded-lg border border-dark-700">
                    {data.proposal}
                  </div>
                </div>
              );
            }

            // 6. Final Decision
            if (ev.event_type === 'final_decision') {
              return (
                <div key={eventId} className="p-5 sm:p-6 rounded-2xl bg-gradient-to-tr from-dark-850 to-dark-800 border-2 border-brand-emerald shadow-2xl glow-emerald group relative">
                  <div className="flex items-center justify-between mb-3.5">
                    <div className="flex items-center space-x-2 text-brand-emerald text-sm font-bold font-mono uppercase tracking-wider">
                      <Award className="w-5 h-5" />
                      <span>FINAL PORTFOLIO MANAGER VERDICT</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold font-mono px-3.5 py-1 rounded-full bg-brand-emerald text-dark-950 shadow font-bold">
                        RECOMMENDATION: {data.rating}
                      </span>
                      <button
                        onClick={() => handleCopyEventContent(eventId, data.decision || '')}
                        title="Copy final verdict"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-opacity"
                      >
                        {copiedEventId === eventId ? <Check className="w-3 h-3 text-brand-emerald" /> : <Copy className="w-3 h-3" />}
                      </button>
                    </div>
                  </div>
                  <div className="text-xs text-slate-100 whitespace-pre-line leading-relaxed">
                    {data.decision}
                  </div>
                </div>
              );
            }

            // Fallback generic event
            return (
              <div key={eventId} className="text-[11px] font-mono text-slate-500 py-0.5">
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
