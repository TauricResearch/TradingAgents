import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { X, Terminal, Trash2, Download, Pause, Play, ChevronDown, Plus, Minus } from 'lucide-react';

interface LogEntry {
  timestamp: string;
  type: 'info' | 'success' | 'error' | 'warning' | 'llm' | 'agent' | 'data';
  source: string;
  message: string;
}

interface TerminalModalProps {
  isOpen: boolean;
  onClose: () => void;
  isAnalyzing: boolean;
}

export default function TerminalModal({ isOpen, onClose, isAnalyzing }: TerminalModalProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'error'>('connecting');
  const [fontSize, setFontSize] = useState(12); // Font size in px
  const terminalRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const isPausedRef = useRef(isPaused);
  const firstLogTimeRef = useRef<number | null>(null);

  // Keep isPausedRef in sync with isPaused state
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // Connect to SSE stream when modal opens
  useEffect(() => {
    if (!isOpen) return;

    setConnectionStatus('connecting');

    // Connect to the backend SSE endpoint
    const connectToStream = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      // Use the same hostname as the current page, but with the backend port
      const backendHost = window.location.hostname;
      const sseUrl = `http://${backendHost}:8001/stream/logs`;
      console.log('[Terminal] Connecting to SSE stream at:', sseUrl);
      const eventSource = new EventSource(sseUrl);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log('[Terminal] SSE connection opened');
        setConnectionStatus('connected');
      };

      eventSource.onmessage = (event) => {
        if (isPausedRef.current) return;

        try {
          const data = JSON.parse(event.data);

          if (data.type === 'heartbeat') return; // Ignore heartbeats

          // Skip the initial "Connected to log stream" message - it's not a real log
          if (data.message === 'Connected to log stream') return;

          const logEntry: LogEntry = {
            timestamp: data.timestamp || new Date().toISOString(),
            type: data.type || 'info',
            source: data.source || 'system',
            message: data.message || ''
          };

          // Update the earliest timestamp reference for elapsed time
          const logTime = new Date(logEntry.timestamp).getTime();
          if (firstLogTimeRef.current === null || logTime < firstLogTimeRef.current) {
            firstLogTimeRef.current = logTime;
          }

          setLogs(prev => [...prev.slice(-500), logEntry]); // Keep last 500 logs
        } catch (e) {
          // Handle non-JSON messages
          console.log('[Terminal] Non-JSON message:', event.data);
          setLogs(prev => [...prev.slice(-500), {
            timestamp: new Date().toISOString(),
            type: 'info',
            source: 'stream',
            message: event.data
          }]);
        }
      };

      eventSource.onerror = (err) => {
        console.error('[Terminal] SSE connection error:', err);
        setConnectionStatus('error');
        // Reconnect after a delay
        setTimeout(() => {
          if (isOpen && eventSourceRef.current === eventSource) {
            console.log('[Terminal] Attempting to reconnect...');
            connectToStream();
          }
        }, 3000);
      };
    };

    connectToStream();

    return () => {
      console.log('[Terminal] Closing SSE connection');
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [isOpen]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Handle scroll to detect manual scrolling
  const handleScroll = useCallback(() => {
    if (!terminalRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = terminalRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  }, []);

  const clearLogs = () => {
    setLogs([]);
    firstLogTimeRef.current = null;
  };

  const downloadLogs = () => {
    const content = logs.map(log => {
      const d = new Date(log.timestamp);
      const dateStr = formatDate(d);
      const timeStr = formatTime(d);
      return `[${dateStr} ${timeStr}] [${log.type.toUpperCase()}] [${log.source}] ${log.message}`;
    }).join('\n');

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `analysis-logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const scrollToBottom = () => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
      setAutoScroll(true);
    }
  };

  // Format date as DD/MM/YYYY
  const formatDate = (d: Date) => {
    const day = d.getDate().toString().padStart(2, '0');
    const month = (d.getMonth() + 1).toString().padStart(2, '0');
    const year = d.getFullYear();
    return `${day}/${month}/${year}`;
  };

  // Format time as HH:MM:SS
  const formatTime = (d: Date) => {
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  // Calculate elapsed time from first log
  const getElapsed = (timestamp: string) => {
    if (!firstLogTimeRef.current) return '';
    const logTime = new Date(timestamp).getTime();
    const elapsed = Math.max(0, (logTime - firstLogTimeRef.current) / 1000);
    if (elapsed < 60) return `+${elapsed.toFixed(0)}s`;
    const mins = Math.floor(elapsed / 60);
    const secs = Math.floor(elapsed % 60);
    return `+${mins}m${secs.toString().padStart(2, '0')}s`;
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'success': return 'text-green-400';
      case 'error': return 'text-red-400';
      case 'warning': return 'text-yellow-400';
      case 'llm': return 'text-purple-400';
      case 'agent': return 'text-cyan-400';
      case 'data': return 'text-blue-400';
      default: return 'text-gray-300';
    }
  };

  const getSourceBadge = (source: string) => {
    const colors: Record<string, string> = {
      'bull_researcher': 'bg-green-900/50 text-green-400 border-green-700',
      'bear_researcher': 'bg-red-900/50 text-red-400 border-red-700',
      'market_analyst': 'bg-blue-900/50 text-blue-400 border-blue-700',
      'news_analyst': 'bg-teal-900/50 text-teal-400 border-teal-700',
      'social_analyst': 'bg-pink-900/50 text-pink-400 border-pink-700',
      'fundamentals': 'bg-emerald-900/50 text-emerald-400 border-emerald-700',
      'risk_manager': 'bg-amber-900/50 text-amber-400 border-amber-700',
      'research_mgr': 'bg-violet-900/50 text-violet-400 border-violet-700',
      'trader': 'bg-purple-900/50 text-purple-400 border-purple-700',
      'aggressive': 'bg-orange-900/50 text-orange-400 border-orange-700',
      'conservative': 'bg-sky-900/50 text-sky-400 border-sky-700',
      'neutral': 'bg-gray-700/50 text-gray-300 border-gray-500',
      'debate': 'bg-cyan-900/50 text-cyan-400 border-cyan-700',
      'data_fetch': 'bg-indigo-900/50 text-indigo-400 border-indigo-700',
      'system': 'bg-gray-800/50 text-gray-400 border-gray-600',
    };

    return colors[source] || 'bg-gray-800/50 text-gray-400 border-gray-600';
  };

  const filteredLogs = filter === 'all'
    ? logs
    : logs.filter(log => log.type === filter || log.source === filter);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full sm:max-w-5xl h-[85vh] sm:h-[80vh] bg-slate-900 rounded-t-xl sm:rounded-xl shadow-2xl border border-slate-700 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between px-3 sm:px-4 py-2 sm:py-3 bg-slate-800 border-b border-slate-700 gap-2">
          {/* Title row */}
          <div className="flex items-center justify-between sm:justify-start gap-2 sm:gap-3">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 sm:w-5 sm:h-5 text-green-400" />
              <h2 className="font-mono font-semibold text-white text-sm sm:text-base">Terminal</h2>
            </div>
            {isAnalyzing && (
              <span className="flex items-center gap-1 sm:gap-1.5 px-1.5 sm:px-2 py-0.5 bg-green-900/50 text-green-400 text-xs font-mono rounded border border-green-700">
                <span className="w-1.5 h-1.5 sm:w-2 sm:h-2 bg-green-400 rounded-full animate-pulse" />
                LIVE
              </span>
            )}
            {/* Close button - visible on mobile in title row */}
            <button
              onClick={onClose}
              className="sm:hidden p-1.5 bg-slate-700 text-gray-400 hover:text-white hover:bg-red-600 rounded transition-colors"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Controls row */}
          <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto pb-1 sm:pb-0 -mx-1 px-1 sm:mx-0 sm:px-0">
            {/* Filter dropdown */}
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="px-1.5 sm:px-2 py-1 bg-slate-700 text-gray-300 text-xs font-mono rounded border border-slate-600 focus:outline-none focus:border-slate-500 min-w-0 flex-shrink-0"
            >
              <option value="all">All</option>
              <option value="llm">LLM</option>
              <option value="agent">Agent</option>
              <option value="data">Data</option>
              <option value="error">Errors</option>
              <option value="success">Success</option>
            </select>

            {/* Font size controls */}
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <button
                onClick={() => setFontSize(s => Math.max(8, s - 1))}
                className="p-1.5 bg-slate-700 text-gray-400 hover:text-white hover:bg-slate-600 rounded transition-colors"
                title="Decrease font size"
              >
                <Minus className="w-3 h-3" />
              </button>
              <span className="text-gray-500 text-xs font-mono w-6 text-center">{fontSize}</span>
              <button
                onClick={() => setFontSize(s => Math.min(20, s + 1))}
                className="p-1.5 bg-slate-700 text-gray-400 hover:text-white hover:bg-slate-600 rounded transition-colors"
                title="Increase font size"
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>

            {/* Pause/Resume */}
            <button
              onClick={() => setIsPaused(!isPaused)}
              className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                isPaused
                  ? 'bg-amber-900/50 text-amber-400 hover:bg-amber-900'
                  : 'bg-slate-700 text-gray-400 hover:text-white hover:bg-slate-600'
              }`}
              title={isPaused ? 'Resume' : 'Pause'}
            >
              {isPaused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
            </button>

            {/* Download */}
            <button
              onClick={downloadLogs}
              className="p-1.5 bg-slate-700 text-gray-400 hover:text-white hover:bg-slate-600 rounded transition-colors flex-shrink-0"
              title="Download logs"
            >
              <Download className="w-4 h-4" />
            </button>

            {/* Clear */}
            <button
              onClick={clearLogs}
              className="p-1.5 bg-slate-700 text-gray-400 hover:text-white hover:bg-slate-600 rounded transition-colors flex-shrink-0"
              title="Clear logs"
            >
              <Trash2 className="w-4 h-4" />
            </button>

            {/* Close - hidden on mobile, shown on desktop */}
            <button
              onClick={onClose}
              className="hidden sm:block p-1.5 bg-slate-700 text-gray-400 hover:text-white hover:bg-red-600 rounded transition-colors flex-shrink-0"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Terminal Content */}
        <div
          ref={terminalRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-2 sm:p-4 font-mono bg-slate-950 scrollbar-thin scrollbar-track-slate-900 scrollbar-thumb-slate-700"
          style={{ fontSize: `${fontSize}px`, lineHeight: '1.5' }}
        >
          {filteredLogs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500 px-4">
              <Terminal className="w-10 h-10 sm:w-12 sm:h-12 mb-3 opacity-50" />
              <p className="text-xs sm:text-sm text-center">
                {connectionStatus === 'connecting' && 'Connecting to log stream...'}
                {connectionStatus === 'error' && 'Connection error. Retrying...'}
                {connectionStatus === 'connected' && (isAnalyzing
                  ? 'Waiting for analysis logs...'
                  : 'Start an analysis to see live updates here')}
              </p>
              <p className="text-xs mt-1 text-gray-600 text-center">
                {connectionStatus === 'connected'
                  ? 'Logs will appear in real-time as the AI analyzes stocks'
                  : 'Establishing connection to backend...'}
              </p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {filteredLogs.map((log, index) => {
                const d = new Date(log.timestamp);
                const dateStr = formatDate(d);
                const timeStr = formatTime(d);
                const elapsed = getElapsed(log.timestamp);
                return (
                  <div key={index} className="flex flex-wrap sm:flex-nowrap items-start gap-1 sm:gap-2 hover:bg-slate-900/50 px-1 py-0.5 rounded">
                    {/* Date + Time */}
                    <span className="text-gray-600 whitespace-nowrap" style={{ fontSize: `${Math.max(fontSize - 1, 8)}px` }}>
                      {dateStr} {timeStr}
                    </span>
                    {/* Elapsed time */}
                    <span className="text-yellow-600/70 whitespace-nowrap font-semibold" style={{ fontSize: `${Math.max(fontSize - 1, 8)}px`, minWidth: '50px' }}>
                      {elapsed}
                    </span>
                    {/* Source badge */}
                    <span className={`px-1 sm:px-1.5 py-0.5 rounded border flex-shrink-0 ${getSourceBadge(log.source)}`} style={{ fontSize: `${Math.max(fontSize - 2, 7)}px` }}>
                      {log.source.length > 14 ? log.source.slice(0, 12) + '..' : log.source}
                    </span>
                    {/* Message */}
                    <span className={`w-full sm:w-auto sm:flex-1 ${getTypeColor(log.type)} break-words`}>
                      {log.message}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer with scroll indicator */}
        {!autoScroll && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-14 sm:bottom-16 right-3 sm:right-6 flex items-center gap-1 px-2 sm:px-3 py-1 sm:py-1.5 bg-slate-700 text-gray-300 text-xs font-mono rounded-full shadow-lg hover:bg-slate-600 transition-colors"
          >
            <ChevronDown className="w-3 h-3" />
            <span className="hidden sm:inline">Scroll to bottom</span>
            <span className="sm:hidden">Bottom</span>
          </button>
        )}

        {/* Status Bar */}
        <div className="px-3 sm:px-4 py-2 bg-slate-800 border-t border-slate-700 flex items-center justify-between text-xs font-mono text-gray-500 gap-2">
          <span className="truncate">{filteredLogs.length} logs | Font: {fontSize}px</span>
          <span className="flex-shrink-0">
            {isPaused ? 'PAUSED' : autoScroll ? 'AUTO' : 'MANUAL'}
          </span>
        </div>
      </div>
    </div>,
    document.body
  );
}
