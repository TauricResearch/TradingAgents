import React from 'react';
import { Activity, Plus, Database, Terminal, FileText, Cpu, Settings, Menu, Keyboard } from 'lucide-react';

interface NavbarProps {
  activeTab: 'arena' | 'report' | 'memory';
  setActiveTab: (tab: 'arena' | 'report' | 'memory') => void;
  onOpenNewModal: () => void;
  onOpenSettings: () => void;
  onOpenShortcuts?: () => void;
  onToggleMobileSidebar?: () => void;
  runningJobsCount: number;
  backendOnline: boolean;
}

const NavbarComponent: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  onOpenNewModal,
  onOpenSettings,
  onOpenShortcuts,
  onToggleMobileSidebar,
  runningJobsCount,
  backendOnline,
}) => {
  return (
    <header className="h-16 border-b border-dark-700/60 bg-dark-900 px-3 sm:px-5 flex items-center justify-between z-30 sticky top-0 shrink-0">
      {/* Brand & Status */}
      <div className="flex items-center space-x-2.5 sm:space-x-4">
        {/* Mobile Hamburger Drawer Trigger */}
        {onToggleMobileSidebar && (
          <button
            onClick={onToggleMobileSidebar}
            title="Open Analysis Runs Drawer"
            className="lg:hidden p-2 rounded-xl bg-dark-800 hover:bg-dark-750 text-slate-300 hover:text-brand-cyan border border-dark-700/80 transition-colors"
          >
            <Menu className="w-4 h-4" />
          </button>
        )}

        <div className="flex items-center space-x-2 sm:space-x-2.5">
          <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-gradient-to-tr from-brand-emerald to-brand-cyan flex items-center justify-center shadow-lg shadow-brand-emerald/20 shrink-0">
            <Cpu className="w-4 h-4 sm:w-5 sm:h-5 text-dark-950 font-bold" />
          </div>
          <div>
            <div className="flex items-center space-x-1.5 sm:space-x-2">
              <span className="font-bold tracking-wider text-sm sm:text-base text-slate-100 uppercase">
                Trading<span className="text-brand-emerald">Agents</span>
              </span>
              <span className="hidden xs:inline-block px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-dark-700 text-brand-cyan border border-brand-cyan/30">
                PRO
              </span>
            </div>
            <p className="hidden md:block text-[10px] text-slate-400 font-mono tracking-tight">
              Multi-Agent Quantitative Intelligence
            </p>
          </div>
        </div>

        <div className="h-6 w-px bg-dark-700/80 mx-1 hidden sm:block" />

        {/* Backend Heartbeat Badge */}
        <div className="hidden xl:flex items-center space-x-2 px-3 py-1 rounded-full bg-dark-850 border border-dark-700/80 text-xs font-mono">
          <span className={`w-2 h-2 rounded-full ${backendOnline ? 'bg-brand-emerald shadow-[0_0_8px_rgba(16,185,129,0.7)]' : 'bg-brand-rose'}`} />
          <span className="text-slate-300">{backendOnline ? 'API CONNECTED' : 'DISCONNECTED'}</span>
        </div>

        {/* Active Jobs Counter */}
        {runningJobsCount > 0 && (
          <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-brand-emerald/10 border border-brand-emerald/30 text-[11px] sm:text-xs font-mono text-brand-emerald shadow-sm">
            <Activity className="w-3 h-3 sm:w-3.5 sm:h-3.5 animate-spin-slow" />
            <span className="hidden sm:inline">{runningJobsCount} RUNNING</span>
            <span className="sm:hidden">{runningJobsCount}</span>
          </div>
        )}
      </div>

      {/* Navigation Tabs */}
      <nav aria-label="Main Navigation" className="flex items-center space-x-1 bg-dark-850/90 p-1 rounded-xl border border-dark-700/60 shadow-inner">
        <button
          onClick={() => setActiveTab('arena')}
          title="Live Arena (Key: 1)"
          className={`flex items-center space-x-1.5 px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            activeTab === 'arena'
              ? 'bg-dark-700 text-brand-cyan shadow-sm border border-brand-cyan/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
          }`}
        >
          <Terminal className="w-3.5 h-3.5 shrink-0" />
          <span className="hidden sm:inline">Live Arena</span>
          <span className="sm:hidden text-[11px]">Arena</span>
          <kbd className="hidden lg:inline text-[9px] font-mono text-slate-500 bg-dark-800 px-1 py-0.2 rounded border border-dark-700 ml-1">1</kbd>
        </button>

        <button
          onClick={() => setActiveTab('report')}
          title="Report Center (Key: 2)"
          className={`flex items-center space-x-1.5 px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            activeTab === 'report'
              ? 'bg-dark-700 text-brand-emerald shadow-sm border border-brand-emerald/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
          }`}
        >
          <FileText className="w-3.5 h-3.5 shrink-0" />
          <span className="hidden sm:inline">Report Center</span>
          <span className="sm:hidden text-[11px]">Report</span>
          <kbd className="hidden lg:inline text-[9px] font-mono text-slate-500 bg-dark-800 px-1 py-0.2 rounded border border-dark-700 ml-1">2</kbd>
        </button>

        <button
          onClick={() => setActiveTab('memory')}
          title="Memory Log & Reflections (Key: 3)"
          className={`flex items-center space-x-1.5 px-2.5 sm:px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            activeTab === 'memory'
              ? 'bg-dark-700 text-brand-amber shadow-sm border border-brand-amber/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
          }`}
        >
          <Database className="w-3.5 h-3.5 shrink-0" />
          <span className="hidden sm:inline">Memory Log</span>
          <span className="sm:hidden text-[11px]">Memory</span>
          <kbd className="hidden lg:inline text-[9px] font-mono text-slate-500 bg-dark-800 px-1 py-0.2 rounded border border-dark-700 ml-1">3</kbd>
        </button>
      </nav>

      {/* Action Buttons */}
      <div className="flex items-center space-x-1.5 sm:space-x-2.5">
        {onOpenShortcuts && (
          <button
            onClick={onOpenShortcuts}
            title="Keyboard Shortcuts Cheat Sheet (?)"
            className="hidden md:flex p-2 rounded-xl bg-dark-800 hover:bg-dark-750 text-slate-400 hover:text-brand-cyan border border-dark-700/80 transition-colors"
          >
            <Keyboard className="w-4 h-4" />
          </button>
        )}

        <button
          onClick={onOpenSettings}
          title="Terminal Settings & API Keys (S)"
          className="p-2 rounded-xl bg-dark-800 hover:bg-dark-750 text-slate-400 hover:text-slate-100 border border-dark-700/80 transition-colors"
        >
          <Settings className="w-4 h-4" />
        </button>

        <button
          onClick={onOpenNewModal}
          title="Launch New Multi-Agent Analysis (N)"
          className="flex items-center space-x-1 sm:space-x-2 px-3 sm:px-4 py-2 rounded-xl bg-gradient-to-r from-brand-emerald to-emerald-600 hover:from-emerald-400 hover:to-brand-emerald text-dark-950 font-bold text-xs transition-all shadow-lg shadow-brand-emerald/20 hover:shadow-brand-emerald/30 active:scale-95"
        >
          <Plus className="w-4 h-4 stroke-[3] shrink-0" />
          <span className="hidden sm:inline">New Analysis</span>
          <span className="sm:hidden">New</span>
          <kbd className="hidden sm:inline text-[9px] font-mono text-dark-900 bg-emerald-300 px-1 py-0.2 rounded font-bold ml-1">N</kbd>
        </button>
      </div>
    </header>
  );
};

export const Navbar = React.memo(NavbarComponent);
