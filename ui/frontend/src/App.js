import React, { useState, useEffect, useMemo } from 'react';
import FlowGraph from './components/FlowGraph';
import { LineChart, Layout, History, Activity, ShieldCheck, ChevronRight, Info, Target, AlertTriangle, PanelLeftClose, PanelLeftOpen, Clock } from 'lucide-react';

const MarkdownContent = ({ content }) => {
  if (!content) return <div style={{ color: '#64748b', fontStyle: 'italic', padding: '10px' }}>No data available</div>;

  // 1. Force newlines before any **Header**: that doesn't have one
  const prepared = content.replace(/([^\n])(\*\*.*?\*\*):/g, '$1\n\n$2:');
  
  // 2. Split into sections
  const chunks = prepared.split('\n\n').filter(c => c.trim());

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {chunks.map((chunk, i) => {
        const headerMatch = chunk.match(/^\*\*(.*?)\*\*:\s*(.*)/s);
        
        if (headerMatch) {
          const [_, header, body] = headerMatch;
          const isHighlight = ['Rating', 'Recommendation', 'Action'].some(h => header.includes(h));
          
          // Split body into sentences to create bullet points
          const sentences = body.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 5);
          
          return (
            <div key={i} style={{ 
              background: isHighlight ? '#1e293b' : 'transparent', 
              borderRadius: '8px', 
              padding: isHighlight ? '16px' : '0 4px',
              borderLeft: isHighlight ? `4px solid ${header.includes('Rating') || header.includes('Recommendation') ? '#3b82f6' : '#10b981'}` : 'none',
            }}>
              <div style={{ 
                fontSize: '11px', 
                fontWeight: '800', 
                textTransform: 'uppercase', 
                color: isHighlight ? '#94a3b8' : '#3b82f6',
                letterSpacing: '0.1em',
                marginBottom: '10px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}>
                {header.includes('Rating') && <Target size={14} />}
                {header.includes('Action') && <AlertTriangle size={14} />}
                {header.includes('Rationale') && <Info size={14} />}
                {header}
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {sentences.map((sentence, idx) => (
                  <div key={idx} style={{ 
                    display: 'flex', 
                    gap: '10px', 
                    fontSize: '13px', 
                    lineHeight: '1.6', 
                    color: '#f8fafc',
                    fontWeight: header.includes('Rating') ? 'bold' : '400'
                  }}>
                    <span style={{ color: '#3b82f6', fontSize: '16px', lineHeight: '1.2' }}>•</span>
                    <span>
                      {sentence.split(/(\*\*.*?\*\*)/g).map((part, j) => {
                        if (part.startsWith('**') && part.endsWith('**')) {
                          return <strong key={j} style={{ color: '#60a5fa' }}>{part.slice(2, -2)}</strong>;
                        }
                        return part;
                      })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        }

        // Handle paragraphs that aren't headers
        const pSentences = chunk.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 5);
        return (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '0 4px' }}>
            {pSentences.map((s, idx) => (
              <div key={idx} style={{ display: 'flex', gap: '10px', fontSize: '13px', lineHeight: '1.7', color: '#cbd5e1' }}>
                <span style={{ color: '#64748b' }}>•</span>
                <span>
                  {s.split(/(\*\*.*?\*\*)/g).map((part, j) => {
                    if (part.startsWith('**') && part.endsWith('**')) {
                      return <strong key={j} style={{ color: '#f8fafc' }}>{part.slice(2, -2)}</strong>;
                    }
                    return part;
                  })}
                </span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

const ProgressBar = ({ progress, status }) => {
  const isError = status === 'error';
  const isTriggered = status === 'triggered';
  
  return (
    <div style={{ width: '100%', height: '6px', background: '#1e293b', borderRadius: '3px', overflow: 'hidden', marginTop: '10px', position: 'relative' }}>
      <div 
        style={{ 
          width: `${progress}%`, 
          height: '100%', 
          background: isError ? '#ef4444' : '#3b82f6', 
          transition: 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
          boxShadow: isError ? 'none' : '0 0 15px rgba(59, 130, 246, 0.5)',
          position: 'relative',
          overflow: 'hidden'
        }} 
      >
        {/* Animated pulse effect for 'thinking' state */}
        {!isError && progress < 100 && (
          <div className="progress-pulse" style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)',
            animation: 'pulse-scan 2s infinite'
          }} />
        )}
      </div>
      
      <style>{`
        @keyframes pulse-scan {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
};

const App = () => {
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState(null);
  const [reflections, setReflections] = useState([]);
  const [activeStatus, setActiveStatus] = useState(null);
  const [lastValidProgress, setLastValidProgress] = useState(5);
  const [portfolio, setPortfolio] = useState('');
  const [isSavingPortfolio, setIsSavingPortfolio] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [selectedRun, setSelectedRun] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [elapsed, setElapsed] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let interval;
    
    const updateElapsed = () => {
      const activeStart = activeStatus?.start_time;
      const detailStart = runDetail?.start_time;
      const detailEnd = runDetail?.end_time;

      if (activeStatus && activeStart && activeStatus.status !== 'completed') {
        const start = new Date(activeStart);
        const now = new Date();
        const diff = Math.floor((now - start) / 1000);
        const mins = Math.max(0, Math.floor(diff / 60));
        const secs = Math.max(0, diff % 60);
        setElapsed(`${mins}m ${secs}s`);
      } else if (detailStart && detailEnd) {
        const start = new Date(detailStart);
        const end = new Date(detailEnd);
        const diff = Math.floor((end - start) / 1000);
        if (diff >= 0) {
          const mins = Math.floor(diff / 60);
          const secs = diff % 60;
          setElapsed(`${mins}m ${secs}s`);
        }
      } else {
        setElapsed(null);
      }
    };

    updateElapsed();

    if (activeStatus && activeStatus.status !== 'completed' && activeStatus.status !== 'error') {
      interval = setInterval(updateElapsed, 1000);
    }

    return () => clearInterval(interval);
  }, [activeStatus, runDetail]);

  const commentary = useMemo(() => {
    if (!activeStatus) return null;
    const n = (activeStatus.active_node || '').toLowerCase();
    
    // Prioritize user-facing task descriptions
    if (n.includes('market')) return 'Analyzing market trends and technical indicators...';
    if (n.includes('social') || n.includes('sentiment')) return 'Gauging market sentiment and social signals...';
    if (n.includes('news')) return 'Processing latest news and insider transactions...';
    if (n.includes('fundamental')) return 'Evaluating balance sheets and financial health...';
    if (n.includes('bull')) return 'Constructing bullish growth thesis...';
    if (n.includes('bear')) return 'Identifying potential risks and bearish catalysts...';
    if (n.includes('research_manager') || n.includes('research manager')) return 'Synthesizing research into investment plan...';
    if (n.includes('trader')) return 'Calculating entry, exit, and stop-loss targets...';
    if (n.includes('portfolio_manager') || n.includes('portfolio manager') || n.includes('risk_management')) return 'Final risk assessment and portfolio allocation...';
    if (n.includes('aggressive')) return 'Stress-testing against aggressive risk models...';
    if (n.includes('conservative')) return 'Evaluating conservative capital preservation...';
    if (n.includes('neutral')) return 'Balancing neutral market outlook...';
    
    // Handle startup/K8s phases gracefully
    if (n.includes('triggering') || n.includes('created') || n.includes('initializing')) {
      return 'Preparing agentic workflow environment...';
    }
    
    return 'Processing agentic analysis...';
  }, [activeStatus]);

  const calculateProgress = (node) => {
    const n = (node || '').toLowerCase();
    
    const steps = {
      'preparing': 5,
      'initializing': 10,
      'market': 20,
      'social': 30,
      'sentiment': 30,
      'news': 40,
      'fundamental': 50,
      'bull': 65,
      'bear': 75,
      'research manager': 85,
      'trader': 92,
      'risk': 95,
      'portfolio': 98,
      'completed': 100
    };

    let progress = lastValidProgress;
    for (const [key, value] of Object.entries(steps)) {
      if (n.includes(key)) {
        progress = value;
        break;
      }
    }

    if (progress > lastValidProgress) {
      setLastValidProgress(progress);
    }
    return progress;
  };

  const refreshRuns = (selectNewest = false) => {
    fetch('/api/runs')
      .then(res => res.json())
      .then(data => {
        setRuns(data);
        // If selectNewest is true or nothing was selected before, select the newest run
        if (data.length > 0 && (selectNewest || !selectedRun)) {
          setSelectedRun(data[0]);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error("Error refreshing runs:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    refreshRuns();
    fetch('/api/stats').then(res => res.json()).then(setStats).catch(err => console.error("Error fetching stats:", err));
    fetch('/api/reflections').then(res => res.json()).then(setReflections).catch(err => console.error("Error fetching reflections:", err));
    fetch('/api/config/portfolio').then(res => res.json()).then(data => setPortfolio(data.tickers)).catch(err => console.error("Error fetching portfolio:", err));

    // Poll for active status every 3 seconds
    const statusInterval = setInterval(() => {
      fetch('/api/status')
        .then(res => res.json())
        .then(data => {
          if (data.status === 'in_progress' || data.status === 'triggered' || data.status === 'error' || data.status === 'completed') {
            setActiveStatus(data);
            if (data.status === 'completed') {
               // If completed, refresh runs and clear active status after a delay
               setTimeout(() => {
                 refreshRuns(true);
                 setActiveStatus(null);
               }, 5000);
            }
          } else {
            // If we were just active and now we're not (e.g. backend reset to idle)
            setActiveStatus(null);
          }
        });
    }, 3000);

    return () => clearInterval(statusInterval);
  }, []);

  const savePortfolio = () => {
    setIsSavingPortfolio(true);
    fetch('/api/config/portfolio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers: portfolio })
    })
    .then(res => {
      if (!res.ok) throw new Error('Failed to update portfolio');
      return res.json();
    })
    .then(() => {
      setIsSavingPortfolio(false);
      alert('Ticker list updated! New analysis runs will now use: ' + portfolio);
    })
    .catch(err => {
      console.error("Error updating portfolio:", err);
      setIsSavingPortfolio(false);
      alert(err.message);
    });
  };

  const triggerAnalysis = () => {
    setIsTriggering(true);
    setElapsed("0m 0s");
    setLastValidProgress(5);
    fetch('/api/jobs/trigger', { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers: portfolio })
    })
    .then(res => {
      if (!res.ok) {
        return res.json().then(err => { throw new Error(err.detail || 'Failed to trigger job') });
      }
      return res.json();
    })
    .then(data => {
      setIsTriggering(false);
      // Immediately fetch status to show feedback without waiting for the next 3s poll
      fetch('/api/status')
        .then(res => res.json())
        .then(statusData => {
          if (statusData.status === 'triggered' || statusData.status === 'in_progress') {
            setActiveStatus(statusData);
          }
        });
    })
    .catch(err => {
      console.error("Error triggering job:", err);
      setIsTriggering(false);
      alert(`Trigger Error: ${err.message}`);
    });
  };

  useEffect(() => {
    if (selectedRun) {
      fetch(`/api/runs/${selectedRun.ticker}/${selectedRun.date}`)
        .then(res => res.json())
        .then(data => setRunDetail(data))
        .catch(err => console.error("Error fetching run details:", err));
    }
  }, [selectedRun]);

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#020617', color: '#f8fafc', fontFamily: 'Inter, sans-serif' }}>
      {/* Sidebar */}
      <div style={{ 
        width: isSidebarCollapsed ? '60px' : '300px', 
        borderRight: '1px solid #1e293b', 
        display: 'flex', 
        flexDirection: 'column',
        transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        overflow: 'hidden',
        position: 'relative'
      }}>
        <div style={{ 
          padding: '20px', 
          borderBottom: '1px solid #1e293b', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: isSidebarCollapsed ? 'center' : 'space-between',
          gap: '10px' 
        }}>
          {!isSidebarCollapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Activity color="#3b82f6" />
              <h1 style={{ fontSize: '18px', fontWeight: 'bold', margin: 0 }}>TradingAgents</h1>
            </div>
          )}
          <button 
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            style={{ 
              background: 'none', 
              border: 'none', 
              color: '#64748b', 
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              padding: '4px'
            }}
          >
            {isSidebarCollapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
          </button>
        </div>
        
        {!isSidebarCollapsed && (
          <>
            <div style={{ padding: '15px', borderBottom: '1px solid #1e293b' }}>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '8px' }}>PERFORMANCE</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '13px', color: '#cbd5e1' }}>Total Trades</span>
                <span style={{ fontSize: '13px', fontWeight: 'bold' }}>{stats?.total_trades || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '13px', color: '#cbd5e1' }}>Win Rate</span>
                <span style={{ fontSize: '13px', fontWeight: 'bold', color: stats?.win_rate >= 50 ? '#10b981' : '#ef4444' }}>
                  {stats?.win_rate?.toFixed(1) || 0}%
                </span>
              </div>
            </div>

            <div style={{ padding: '15px', borderBottom: '1px solid #1e293b', background: '#0f172a' }}>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '8px' }}>PORTFOLIO TICKERS</div>
              <textarea 
                value={portfolio}
                onChange={(e) => setPortfolio(e.target.value)}
                placeholder="AAPL,MSFT,NVDA..."
                style={{
                  width: '100%',
                  background: '#020617',
                  border: '1px solid #334155',
                  borderRadius: '4px',
                  color: 'white',
                  fontSize: '12px',
                  padding: '8px',
                  minHeight: '60px',
                  resize: 'none',
                  fontFamily: 'inherit',
                  boxSizing: 'border-box',
                  marginBottom: '8px'
                }}
              />
              <button 
                onClick={savePortfolio}
                disabled={isSavingPortfolio}
                style={{
                  width: '100%',
                  background: '#3b82f6',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '6px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  opacity: isSavingPortfolio ? 0.5 : 1,
                  marginBottom: '8px'
                }}
              >
                {isSavingPortfolio ? 'SAVING...' : 'UPDATE TICKER LIST'}
              </button>

              <button 
                onClick={triggerAnalysis}
                disabled={isTriggering || activeStatus}
                style={{
                  width: '100%',
                  background: activeStatus ? '#1e293b' : '#10b981',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '8px',
                  fontSize: '12px',
                  fontWeight: 'bold',
                  cursor: (isTriggering || activeStatus) ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  opacity: isTriggering ? 0.5 : 1
                }}
              >
                <Activity size={14} />
                {activeStatus ? (
                  activeStatus.status === 'triggered' ? 'JOB STARTING...' : 'ANALYSIS IN PROGRESS...'
                ) : (isTriggering ? 'TRIGGERING...' : 'RUN ANALYSIS NOW')}
              </button>
            </div>
            
            <div style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
              <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 'bold', marginBottom: '10px', paddingLeft: '10px' }}>RECENT RUNS</div>
              {runs.map((run, i) => (
                <div 
                  key={i} 
                  onClick={() => setSelectedRun(run)}
                  style={{
                    padding: '12px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    background: selectedRun === run ? '#1e293b' : 'transparent',
                    marginBottom: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    transition: 'background 0.2s'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 'bold' }}>{run.ticker}</div>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>{run.date}</div>
                  </div>
                  <ChevronRight size={14} color="#475569" />
                </div>
              ))}
            </div>
          </>
        )}
        
        {isSidebarCollapsed && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px', paddingTop: '20px' }}>
            <Activity color="#3b82f6" />
            <div style={{ width: '30px', height: '1px', background: '#1e293b' }} />
            {runs.slice(0, 5).map((run, i) => (
              <div 
                key={i} 
                onClick={() => setSelectedRun(run)}
                title={`${run.ticker} - ${run.date}`}
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '20px',
                  background: selectedRun === run ? '#3b82f6' : '#1e293b',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '10px',
                  fontWeight: 'bold',
                  cursor: 'pointer'
                }}
              >
                {run.ticker.slice(0, 2)}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <header style={{ padding: '20px', borderBottom: '1px solid #1e293b', background: '#020617' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ flex: 1 }}>
              <h2 style={{ margin: 0, fontSize: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                {activeStatus ? (
                  <>
                    <span style={{ color: activeStatus.status === 'error' ? '#ef4444' : '#10b981' }}>●</span>
                    {activeStatus.status === 'error' ? 'ANALYSIS FAILED' : `ANALYZING ${activeStatus.ticker}...`}
                  </>
                ) : (selectedRun ? `${selectedRun.ticker} Analysis` : 'Select a run')}
              </h2>
              <div style={{ fontSize: '12px', color: activeStatus?.status === 'error' ? '#ef4444' : '#94a3b8', marginTop: '4px' }}>
                {activeStatus ? (
                  activeStatus.status === 'error' 
                    ? activeStatus.error 
                    : `Active Node: ${activeStatus.active_node}`
                ) : `Trade Date: ${selectedRun?.date}`}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
              {elapsed && (
                <div style={{ 
                  textAlign: 'right', 
                  background: activeStatus && activeStatus.status !== 'completed' ? 'rgba(234, 179, 8, 0.1)' : 'rgba(30, 41, 59, 0.5)',
                  padding: '4px 12px',
                  borderRadius: '6px',
                  border: `1px solid ${activeStatus && activeStatus.status !== 'completed' ? '#eab308' : '#334155'}`
                }}>
                  <div style={{ fontSize: '10px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px', justifyContent: 'flex-end', marginBottom: '2px' }}>
                    <Clock size={10} /> {activeStatus && activeStatus.status !== 'completed' ? 'ELAPSED' : 'TIME TAKEN'}
                  </div>
                  <div style={{ color: activeStatus && activeStatus.status !== 'completed' ? '#eab308' : '#f8fafc', fontSize: '14px', fontWeight: '800', fontFamily: 'monospace' }}>
                    {elapsed}
                  </div>
                </div>
              )}
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>STATUS</div>
                <div style={{ color: activeStatus ? (activeStatus.status === 'error' ? '#ef4444' : '#3b82f6') : '#10b981', fontSize: '14px', fontWeight: 'bold' }}>
                  {activeStatus ? (activeStatus.status === 'error' ? 'ERROR' : 'IN PROGRESS') : 'COMPLETED'}
                </div>
              </div>
              {!activeStatus && (
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>DECISION</div>
                  <div style={{ color: '#3b82f6', fontSize: '14px', fontWeight: 'bold' }}>{runDetail?.final_trade_decision?.split('\n')[0] || '---'}</div>
                </div>
              )}
            </div>
          </div>
          {activeStatus && activeStatus.status !== 'error' && (
            <>
              <ProgressBar progress={calculateProgress(activeStatus.active_node)} status={activeStatus.status} />
              {commentary && (
                <div style={{ 
                  fontSize: '12px', 
                  color: '#eab308', 
                  marginTop: '8px', 
                  fontWeight: '500',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}>
                  <span style={{ animation: 'pulse 2s infinite' }}>●</span>
                  {commentary}
                </div>
              )}
            </>
          )}
        </header>
        
        <style>{`
          @keyframes pulse {
            0% { opacity: 0.4; transform: scale(0.8); }
            50% { opacity: 1; transform: scale(1.1); }
            100% { opacity: 0.4; transform: scale(0.8); }
          }
        `}</style>

        {/* Workspace */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          <div style={{ marginBottom: '20px', borderRadius: '12px', overflow: 'hidden', border: '1px solid #1e293b' }}>
            <div style={{ padding: '15px', background: '#0f172a', borderBottom: '1px solid #1e293b', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Layout size={18} color="#3b82f6" />
                <span style={{ fontWeight: 'bold', fontSize: '14px' }}>AGENTIC FLOW VISUALIZATION</span>
              </div>
              {selectedAgent && (
                <div style={{ 
                  background: '#1e293b', 
                  padding: '6px 12px', 
                  borderRadius: '6px', 
                  fontSize: '12px', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '10px',
                  border: '1px solid #3b82f6',
                }}>
                  <div style={{ fontWeight: 'bold', color: '#60a5fa' }}>{selectedAgent.label.toUpperCase()}:</div>
                  <div style={{ color: '#94a3b8' }}>{selectedAgent.description}</div>
                  <button 
                    onClick={() => setSelectedAgent(null)}
                    style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: '0 4px', fontSize: '16px' }}
                  >×</button>
                </div>
              )}
            </div>
            <FlowGraph runData={runDetail} activeStatus={activeStatus} onNodeClick={setSelectedAgent} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <section style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px' }}>
              <h3 style={{ marginTop: 0, fontSize: '14px', color: '#3b82f6', borderBottom: '1px solid #1e293b', paddingBottom: '10px' }}>FINAL DECISION</h3>
              <MarkdownContent content={runDetail?.final_trade_decision} />
            </section>
            
            <section style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px' }}>
              <h3 style={{ marginTop: 0, fontSize: '14px', color: '#eab308', borderBottom: '1px solid #1e293b', paddingBottom: '10px' }}>INVESTMENT PLAN</h3>
              <MarkdownContent content={runDetail?.investment_plan} />
            </section>
          </div>

          {/* Reflections Section */}
          {reflections.length > 0 && (
            <div style={{ marginTop: '20px' }}>
              <section style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px' }}>
                <h3 style={{ marginTop: 0, fontSize: '14px', color: '#a855f7', borderBottom: '1px solid #1e293b', paddingBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <History size={16} /> HISTORICAL REFLECTIONS
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {reflections.slice(0, 5).map((ref, idx) => (
                    <div key={idx} style={{ padding: '12px', background: '#1e293b', borderRadius: '8px', borderLeft: '3px solid #a855f7' }}>
                      <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px', fontWeight: 'bold' }}>
                        {ref.ticker} • {ref.date} • {ref.alpha} Alpha • {ref.holding} holding
                      </div>
                      <MarkdownContent content={ref.reflection} />
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default App;
