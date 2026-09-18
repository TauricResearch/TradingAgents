import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Navbar } from './components/Navbar';
import { JobSidebar } from './components/JobSidebar';
import { LiveAgentArena } from './components/LiveAgentArena';
import { ReportViewer } from './components/ReportViewer';
import { MemoryExplorer } from './components/MemoryExplorer';
import { NewAnalysisModal } from './components/NewAnalysisModal';
import { SettingsModal } from './components/SettingsModal';
import { ShortcutsModal } from './components/ShortcutsModal';
import { ToastContainer, toast } from './components/Toast';
import { Job, JobEvent, JobReport, ConfigOptions, JobCreatePayload } from './types';
import { playChime, notifyJobCompleted } from './services/notification';
import { 
  fetchJobs, 
  fetchJob, 
  createJob, 
  cancelJob, 
  deleteJob,
  batchDeleteJobs,
  clearJobsHistory,
  fetchReport, 
  fetchJobHistory, 
  fetchConfigOptions, 
  subscribeToJobEvents 
} from './services/api';

export const App: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'arena' | 'report' | 'memory'>('arena');
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [isMobileDrawerOpen, setIsMobileDrawerOpen] = useState(false);
  const [configOptions, setConfigOptions] = useState<ConfigOptions | null>(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [jobEvents, setJobEvents] = useState<JobEvent[]>([]);
  const [activeReport, setActiveReport] = useState<JobReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  // 1. Initial configuration and heartbeat
  useEffect(() => {
    const initApp = async () => {
      try {
        const conf = await fetchConfigOptions();
        setConfigOptions(conf);
        setBackendOnline(true);
      } catch (err) {
        console.warn('Backend currently unreachable:', err);
        setBackendOnline(false);
      }
    };
    initApp();
  }, []);

  // 2. Periodic jobs polling with deep identity check
  const loadJobsList = useCallback(async () => {
    try {
      const data = await fetchJobs();
      const newJobs = data.jobs || [];
      setJobs((prev) => {
        if (prev.length !== newJobs.length) return newJobs;
        const changed = newJobs.some((nj, idx) => {
          const pj = prev[idx];
          return (
            !pj ||
            pj.id !== nj.id ||
            pj.status !== nj.status ||
            pj.progress !== nj.progress ||
            pj.current_stage !== nj.current_stage
          );
        });
        return changed ? newJobs : prev;
      });
      setBackendOnline((prev) => (prev ? prev : true));
      setSelectedJobId((currentId) => {
        if (!currentId && newJobs.length > 0) return newJobs[0].id;
        if (currentId && !newJobs.some((j) => j.id === currentId)) {
          return newJobs.length > 0 ? newJobs[0].id : null;
        }
        return currentId;
      });
    } catch (err) {
      setBackendOnline((prev) => (prev ? false : prev));
    }
  }, []);

  useEffect(() => {
    loadJobsList();
    const interval = setInterval(loadJobsList, 3000);
    return () => clearInterval(interval);
  }, [loadJobsList]);

  // Global hotkeys (1, 2, 3, N, ?, S, /, Escape)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      const isInput = activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select';

      if (e.key === 'Escape') {
        setIsNewModalOpen(false);
        setIsSettingsOpen(false);
        setIsShortcutsOpen(false);
        setIsMobileDrawerOpen(false);
        return;
      }

      if (isInput) return;

      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        setIsNewModalOpen(true);
      } else if (e.key === '1') {
        e.preventDefault();
        setActiveTab('arena');
      } else if (e.key === '2') {
        e.preventDefault();
        setActiveTab('report');
      } else if (e.key === '3') {
        e.preventDefault();
        setActiveTab('memory');
      } else if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setIsShortcutsOpen((prev) => !prev);
      } else if (e.key === 's' || e.key === 'S' || e.key === ',') {
        e.preventDefault();
        setIsSettingsOpen(true);
      } else if (e.key === '/') {
        e.preventDefault();
        const searchInput = document.getElementById('job-search-input');
        if (searchInput) searchInput.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // 3. Load historical events and subscribe to live SSE stream for selected job
  useEffect(() => {
    if (!selectedJobId) {
      setJobEvents([]);
      return;
    }

    let isMounted = true;

    // Load initial events from DB
    fetchJobHistory(selectedJobId)
      .then((history) => {
        if (isMounted) setJobEvents(history);
      })
      .catch((err) => console.error('Failed to load history:', err));

    // Connect SSE listener
    const unsubscribe = subscribeToJobEvents(
      selectedJobId,
      (incomingEvent) => {
        if (isMounted) {
          if (incomingEvent.event_type === 'job_completed') {
            playChime('success');
            const data = incomingEvent.data || {};
            notifyJobCompleted(data.ticker || 'Asset', data.signal || data.decision_signal);
            toast.success(`Analysis completed for ${data.ticker || 'Asset'}!`);
          } else if (incomingEvent.event_type === 'job_failed') {
            playChime('alert');
            toast.error(`Analysis failed for job ${selectedJobId.slice(0, 8)}`);
          }

          setJobEvents((prev) => {
            const exists = prev.some((e) => e.id === incomingEvent.id);
            return exists ? prev : [...prev, incomingEvent];
          });
        }
      },
      (err) => {
        console.warn('SSE stream notice:', err);
      }
    );

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, [selectedJobId]);

  // 4. Load report when switching to report tab
  useEffect(() => {
    if (activeTab === 'report' && selectedJobId) {
      setLoadingReport(true);
      fetchReport(selectedJobId)
        .then((rep) => setActiveReport(rep))
        .catch(() => setActiveReport(null))
        .finally(() => setLoadingReport(false));
    }
  }, [activeTab, selectedJobId]);

  // Handlers
  const handleSelectJob = useCallback((jobId: string) => {
    setSelectedJobId(jobId);
  }, []);

  const handleOpenNewModal = useCallback(() => setIsNewModalOpen(true), []);
  const handleCloseNewModal = useCallback(() => setIsNewModalOpen(false), []);
  const handleOpenSettings = useCallback(() => setIsSettingsOpen(true), []);
  const handleCloseSettings = useCallback(() => setIsSettingsOpen(false), []);
  const handleOpenShortcuts = useCallback(() => setIsShortcutsOpen(true), []);
  const handleCloseShortcuts = useCallback(() => setIsShortcutsOpen(false), []);
  const handleToggleSidebar = useCallback(() => setSidebarCollapsed((prev) => !prev), []);
  const handleToggleMobileDrawer = useCallback(() => setIsMobileDrawerOpen((prev) => !prev), []);
  const handleCloseMobileDrawer = useCallback(() => setIsMobileDrawerOpen(false), []);
  const handleViewReport = useCallback(() => setActiveTab('report'), []);
  const handleBackToArena = useCallback(() => setActiveTab('arena'), []);

  const handleCreateJob = useCallback(async (payload: JobCreatePayload) => {
    const created = await createJob(payload);
    setJobs((prev) => [created, ...prev]);
    setSelectedJobId(created.id);
    setActiveTab('arena');
  }, []);

  const handleCancelJob = useCallback(async (jobId: string) => {
    try {
      await cancelJob(jobId);
      toast.info('Job cancellation requested');
      loadJobsList();
    } catch (err: any) {
      toast.error(err.message || 'Failed to cancel job');
    }
  }, [loadJobsList]);

  const handleDeleteJob = useCallback(async (jobId: string, force: boolean = false) => {
    try {
      await deleteJob(jobId, force);
      setJobs((prev) => {
        const updated = prev.filter((j) => j.id !== jobId);
        if (selectedJobId === jobId) {
          setSelectedJobId(updated.length > 0 ? updated[0].id : null);
        }
        return updated;
      });
      toast.success('Analysis run deleted');
    } catch (err: any) {
      console.error('Failed to delete job:', err);
      toast.error(err.message || 'Failed to delete job');
    }
  }, [selectedJobId]);

  const handleBatchDeleteJobs = useCallback(async (jobIds: string[], force: boolean = false) => {
    try {
      const res = await batchDeleteJobs(jobIds, force);
      const deletedSet = new Set(res.job_ids);
      setJobs((prev) => {
        const updated = prev.filter((j) => !deletedSet.has(j.id));
        if (selectedJobId && deletedSet.has(selectedJobId)) {
          setSelectedJobId(updated.length > 0 ? updated[0].id : null);
        }
        return updated;
      });
      toast.success(`Batch deleted ${res.deleted_count} job(s)`);
    } catch (err: any) {
      console.error('Failed to batch delete jobs:', err);
      toast.error(err.message || 'Failed to batch delete jobs');
    }
  }, [selectedJobId]);

  const handleClearJobsHistory = useCallback(async (statusFilter?: string, allFinished: boolean = false) => {
    try {
      const res = await clearJobsHistory(statusFilter, allFinished);
      await loadJobsList();
      toast.success(`Cleared ${res.deleted_count} finished job(s) from history`);
    } catch (err: any) {
      console.error('Failed to clear jobs history:', err);
      toast.error(err.message || 'Failed to clear jobs history');
    }
  }, [loadJobsList]);

  const selectedJob = useMemo(() => jobs.find((j) => j.id === selectedJobId) || null, [jobs, selectedJobId]);
  const runningJobsCount = useMemo(() => jobs.filter((j) => j.status === 'running').length, [jobs]);

  return (
    <div className="flex flex-col h-full w-full bg-dark-950 text-slate-100 overflow-hidden select-none font-sans">
      {/* Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenNewModal={handleOpenNewModal}
        onOpenSettings={handleOpenSettings}
        onOpenShortcuts={handleOpenShortcuts}
        onToggleMobileSidebar={handleToggleMobileDrawer}
        runningJobsCount={runningJobsCount}
        backendOnline={backendOnline}
      />

      {/* Main Container */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Sidebar */}
        <JobSidebar
          jobs={jobs}
          selectedJobId={selectedJobId}
          isCollapsed={sidebarCollapsed}
          onToggleCollapse={handleToggleSidebar}
          onSelectJob={handleSelectJob}
          onCancelJob={handleCancelJob}
          onDeleteJob={handleDeleteJob}
          onBatchDeleteJobs={handleBatchDeleteJobs}
          onClearJobsHistory={handleClearJobsHistory}
          onRefreshJobs={loadJobsList}
          isMobileOpen={isMobileDrawerOpen}
          onCloseMobile={handleCloseMobileDrawer}
        />

        {/* Dynamic Workspace */}
        {activeTab === 'arena' && (
          <LiveAgentArena
            job={selectedJob}
            events={jobEvents}
            onViewReport={handleViewReport}
          />
        )}

        {activeTab === 'report' && (
          <ReportViewer
            report={activeReport}
            loading={loadingReport}
            onBackToArena={handleBackToArena}
          />
        )}

        {activeTab === 'memory' && <MemoryExplorer />}
      </div>

      {/* Modal for New Analysis */}
      <NewAnalysisModal
        isOpen={isNewModalOpen}
        onClose={handleCloseNewModal}
        onSubmit={handleCreateJob}
        configOptions={configOptions}
      />

      {/* Modal for Terminal Settings & API Keys */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={handleCloseSettings}
      />

      {/* Modal for Keyboard Shortcuts Help */}
      <ShortcutsModal
        isOpen={isShortcutsOpen}
        onClose={handleCloseShortcuts}
      />

      {/* Global In-App Toast Container */}
      <ToastContainer />
    </div>
  );
};
