import { useState, useRef, useCallback } from 'react';
import type { AgentState, AgentStatus, ReportSection, Stats, Settings } from '../types';
import ProgressTracker from './ProgressTracker';
import ReportFeed from './ReportFeed';

interface Props {
  settings: Settings;
}

const today = () => new Date().toISOString().slice(0, 10);

export default function AnalysisTab({ settings }: Props) {
  const [ticker, setTicker] = useState('');
  const [date, setDate] = useState(today());
  const [running, setRunning] = useState(false);
  const [agentState, setAgentState] = useState<AgentState>({});
  const [sections, setSections] = useState<ReportSection[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [decision, setDecision] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  const handleEvent = useCallback((ev: Record<string, unknown>) => {
    switch (ev.type) {
      case 'agent_status':
        setAgentState(prev => ({ ...prev, [ev.agent as string]: ev.status as AgentStatus }));
        break;
      case 'report_section':
        setSections(prev => {
          if (prev.find(s => s.section === ev.section)) return prev;
          return [...prev, {
            section: ev.section as string,
            title: ev.title as string,
            content: ev.content as string,
          }];
        });
        break;
      case 'stats':
        setStats(ev as unknown as Stats);
        break;
      case 'complete':
        setDecision(ev.decision as string);
        setRunning(false);
        break;
      case 'error':
        setError(ev.message as string);
        setRunning(false);
        break;
    }
  }, []);

  const handleRun = useCallback(() => {
    if (!ticker.trim()) { setError('Ticker is required'); return; }
    setError(null);
    setAgentState({});
    setSections([]);
    setStats(null);
    setDecision(null);
    setRunning(true);

    fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: ticker.trim().toUpperCase(), date }),
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(res.status === 409 ? 'Analysis already running' : (body.detail ?? 'Failed to start analysis'));
        setRunning(false);
        return;
      }
      const reader = res.body!.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buf = '';

      const pump = async (): Promise<void> => {
        const { done, value } = await reader.read();
        if (done) { setRunning(false); return; }
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try { handleEvent(JSON.parse(line.slice(6))); } catch { /* skip malformed */ }
        }
        return pump();
      };
      pump().catch(err => { setError(String(err)); setRunning(false); });
    }).catch(err => { setError(String(err)); setRunning(false); });
  }, [ticker, date, handleEvent]);

  const handleStop = useCallback(() => {
    readerRef.current?.cancel();
    readerRef.current = null;
    fetch('/api/stop', { method: 'POST' });
    setRunning(false);
  }, []);

  return (
    <div>
      {/* Input row */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 20, flexWrap: 'wrap' }}>
        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 5 }}>
            Ticker
          </label>
          <input
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            placeholder="e.g. NVDA"
            disabled={running}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6,
              padding: '8px 14px', color: 'var(--text-primary)', fontSize: 15, fontWeight: 600, width: 130,
            }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 5 }}>
            Analysis Date
          </label>
          <input
            type="date"
            value={date}
            max={today()}
            onChange={e => setDate(e.target.value)}
            disabled={running}
            style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6,
              padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, width: 160,
            }}
          />
        </div>
        <button
          onClick={running ? handleStop : handleRun}
          style={{
            background: running ? 'var(--red)' : 'var(--accent)',
            color: '#fff', borderRadius: 6, padding: '9px 24px', fontSize: 14, fontWeight: 600, height: 38,
          }}
        >
          {running ? '■ Stop' : '▶ Run Analysis'}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.15)', border: '1px solid var(--red)',
          borderRadius: 6, padding: '10px 16px', color: 'var(--red)', marginBottom: 16, fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Progress tracker — only shown once a run has started */}
      {(running || Object.keys(agentState).length > 0) && (
        <ProgressTracker
          agentState={agentState}
          selectedAnalysts={settings.analysts}
          stats={stats}
        />
      )}

      <ReportFeed sections={sections} decision={decision} />
    </div>
  );
}
