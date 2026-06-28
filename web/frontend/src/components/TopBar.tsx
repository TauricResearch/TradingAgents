import { LogOut, Settings, Download, Bot, History, Menu, X } from "lucide-react";
import { useAuthStore } from "../stores/authStore";
import { useUi } from "../store/ui";
import { Button } from "../ui";
import { VERSION } from "../version";

interface TopBarProps {
  currentModelSummary: string | null;
  onOpenSettings: () => void;
  onOpenBatchDownload: () => void;
}

export function TopBar({ currentModelSummary, onOpenSettings, onOpenBatchDownload }: TopBarProps) {
  const setBackgroundRunsOpen = useUi((s) => s.setBackgroundRunsOpen);
  const setTickerAgentDrawerOpen = useUi((s) => s.setTickerAgentDrawerOpen);
  const mobileSidebarOpen = useUi((s) => s.mobileSidebarOpen);
  const setMobileSidebarOpen = useUi((s) => s.setMobileSidebarOpen);
  const sidebarCollapsed = useUi((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useUi((s) => s.setSidebarCollapsed);

  return (
    <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-900/80 backdrop-blur-md">
      <div className="flex items-center justify-between px-3 md:px-5 h-12">
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="md:hidden btn-secondary text-xs shrink-0"
            aria-label="Open watchlist"
          >
            <Menu className="w-4 h-4" />
          </button>
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="hidden md:inline-flex btn-secondary text-xs shrink-0"
            aria-label={sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
          >
            <Menu className="w-3.5 h-3.5" />
          </button>
          <h1 className="text-sm md:text-base font-display font-semibold text-slate-100 tracking-tight flex items-center gap-2">
            TradingAgents
            <span className="hidden sm:inline-flex px-2 py-0.5 text-[8px] font-mono font-semibold rounded-md bg-gradient-to-r from-sky-500/20 via-slate-900/80 to-emerald-500/20 text-slate-100 border border-slate-700/70 shadow-[0_0_12px_rgba(56,189,248,0.15)]">
              v{VERSION}
            </span>
          </h1>
          {currentModelSummary && (
            <span className="hidden lg:inline-flex items-center gap-1 px-2 py-0.5 text-[9px] font-mono font-semibold uppercase tracking-widest bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-md">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 shadow-[0_0_4px_rgba(56,189,248,0.5)]" />
              {currentModelSummary}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Button variant="ghost" size="xs" onClick={() => setBackgroundRunsOpen(true)} icon={<History className="w-3.5 h-3.5" />}>
            <span className="hidden sm:inline">Past Runs</span>
          </Button>
          <Button variant="ghost" size="xs" onClick={() => setTickerAgentDrawerOpen(true)} icon={<Bot className="w-3.5 h-3.5" />}>
            <span className="hidden sm:inline">Agent</span>
          </Button>
          <Button variant="ghost" size="xs" onClick={onOpenBatchDownload} icon={<Download className="w-3.5 h-3.5" />} aria-label="Download ticker data" />
          <Button variant="ghost" size="xs" onClick={onOpenSettings} icon={<Settings className="w-3.5 h-3.5" />} aria-label="Settings" />
          <Button
            variant="ghost"
            size="xs"
            onClick={() => useAuthStore.getState().logout()}
            icon={<LogOut className="w-3.5 h-3.5" />}
            className="text-red-400 hover:text-red-300"
            aria-label="Sign out"
          />
        </div>
      </div>
    </header>
  );
}
