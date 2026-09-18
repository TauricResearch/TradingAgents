import React from 'react';
import { Activity, Plus, Database, Terminal, FileText, Cpu, Settings } from 'lucide-react';

interface NavbarProps {
  activeTab: 'arena' | 'report' | 'memory';
  setActiveTab: (tab: 'arena' | 'report' | 'memory') => void;
  onOpenNewModal: () => void;
  onOpenSettings: () => void;
  runningJobsCount: number;
  backendOnline: boolean;
}

const NavbarComponent: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  onOpenNewModal,
  onOpenSettings,
  runningJobsCount,
  backendOnline,
}) => {
  return (
    <header className="h-16 border-b border-dark-700/60 bg-dark-900 px-4 flex items-center justify-between z-30 sticky top-0">
      {/* Brand & Status */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2.5">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-brand-emerald to-brand-cyan flex items-center justify-center shadow-lg shadow-brand-emerald/20">
            <Cpu className="w-5 h-5 text-dark-950 font-bold" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold tracking-wider text-base text-slate-100 uppercase">
                Trading<span className="text-brand-emerald">Agents</span>
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-dark-700 text-brand-cyan border border-brand-cyan/30">
                PRO v1.0
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono tracking-tight">
              Multi-Agent Quantitative Intelligence
            </p>
          </div>
        </div>

        <div className="h-6 w-px bg-dark-700 mx-2 hidden sm:block" />

        {/* Backend Heartbeat Badge */}
        <div className="hidden sm:flex items-center space-x-2 px-2.5 py-1 rounded-full bg-dark-850 border border-dark-700/80 text-xs font-mono">
          <span className={`w-2 h-2 rounded-full ${backendOnline ? 'bg-brand-emerald shadow-[0_0_8px_rgba(16,185,129,0.7)]' : 'bg-brand-rose'}`} />
          <span className="text-slate-300">{backendOnline ? 'API CONNECTED' : 'DISCONNECTED'}</span>
        </div>

        {/* Active Jobs Counter */}
        {runningJobsCount > 0 && (
          <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-brand-emerald/10 border border-brand-emerald/30 text-xs font-mono text-brand-emerald">
            <Activity className="w-3.5 h-3.5 animate-spin-slow" />
            <span>{runningJobsCount} RUNNING</span>
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center space-x-1 bg-dark-850/90 p-1 rounded-lg border border-dark-700/60">
        <button
          onClick={() => setActiveTab('arena')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            activeTab === 'arena'
              ? 'bg-dark-700 text-brand-cyan shadow-sm border border-brand-cyan/20'
              : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
          }`}
        >
          <Terminal className="w-3.5 h-3.5" />
          <span>Live Arena</span>
        </button>

        <button
          onClick={() => setActiveTab('report')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            activeTab === 'report'
              ? 'bg-dark-700 text-brand-emerald shadow-sm border border-brand-emerald/20'
              : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Report Center</span>
        </button>

        <button
          onClick={() => setActiveTab('memory')}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            activeTab === 'memory'
              ? 'bg-dark-700 text-brand-amber shadow-sm border border-brand-amber/20'
              : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
          }`}
        >
          <Database className="w-3.5 h-3.5" />
          <span>Memory Log</span>
        </button>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center space-x-2.5">
        <button
          onClick={onOpenSettings}
          title="Terminal Settings & API Keys"
          className="p-2 rounded-lg bg-dark-800 hover:bg-dark-750 text-slate-400 hover:text-slate-100 border border-dark-700/80 transition-colors"
        >
          <Settings className="w-4 h-4" />
        </button>

        <button
          onClick={onOpenNewModal}
          className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-gradient-to-r from-brand-emerald to-emerald-600 hover:from-emerald-400 hover:to-brand-emerald text-dark-950 font-semibold text-xs transition-all shadow-lg shadow-brand-emerald/20 hover:shadow-brand-emerald/30 active:scale-95"
        >
          <Plus className="w-4 h-4 stroke-[3]" />
          <span>New Analysis</span>
        </button>
      </div>
    </header>
  );
};

export const Navbar = React.memo(NavbarComponent);

