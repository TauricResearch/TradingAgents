import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Navbar } from './components/Navbar';
import { JobSidebar } from './components/JobSidebar';
import { LiveAgentArena } from './components/LiveAgentArena';
import { ReportViewer } from './components/ReportViewer';
import { MemoryExplorer } from './components/MemoryExplorer';
import { NewAnalysisModal } from './components/NewAnalysisModal';
import { SettingsModal } from './components/SettingsModal';
import { Job, JobEvent, JobReport, ConfigOptions, JobCreatePayload } from './types';
import { playChime, notifyJobCompleted } from './services/notification';
import { 
  fetchJobs, 
  fetchJob, 
  createJob, 
  cancelJob, 
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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


  // Global hotkeys (N for New Analysis, Escape to close modal)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
        if (e.key === 'Escape') setIsNewModalOpen(false);
        return;
      }
      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        setIsNewModalOpen(true);
      } else if (e.key === 'Escape') {
        setIsNewModalOpen(false);
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
          } else if (incomingEvent.event_type === 'job_failed') {
            playChime('alert');
          }

          setJobEvents((prev) => {
            // Avoid duplicate by event id or stage duplicate
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
  const handleToggleSidebar = useCallback(() => setSidebarCollapsed((prev) => !prev), []);
  const handleViewReport = useCallback(() => setActiveTab('report'), []);
  const handleBackToArena = useCallback(() => setActiveTab('arena'), []);

  const handleCreateJob = useCallback(async (payload: JobCreatePayload) => {
    const created = await createJob(payload);
    setJobs((prev) => [created, ...prev]);
    setSelectedJobId(created.id);
    setActiveTab('arena');
  }, []);

  const handleCancelJob = useCallback(async (jobId: string) => {
    await cancelJob(jobId);
    loadJobsList();
  }, [loadJobsList]);

  const selectedJob = useMemo(() => jobs.find((j) => j.id === selectedJobId) || null, [jobs, selectedJobId]);
  const runningJobsCount = useMemo(() => jobs.filter((j) => j.status === 'running').length, [jobs]);

  return (
    <div className="flex flex-col h-full w-full bg-dark-950 text-slate-100 overflow-hidden select-none">
      {/* Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenNewModal={handleOpenNewModal}
        onOpenSettings={handleOpenSettings}
        runningJobsCount={runningJobsCount}
        backendOnline={backendOnline}
      />

      {/* Main Container */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <JobSidebar
          jobs={jobs}
          selectedJobId={selectedJobId}
          isCollapsed={sidebarCollapsed}
          onToggleCollapse={handleToggleSidebar}
          onSelectJob={handleSelectJob}
          onCancelJob={handleCancelJob}
          onRefreshJobs={loadJobsList}
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
    </div>
  );
};

