import React, { useState, useEffect } from 'react';
import FlowGraph from './components/FlowGraph';
import { LineChart, Layout, History, Activity, ShieldCheck, ChevronRight, Info, Target, AlertTriangle } from 'lucide-react';

const MarkdownContent = ({ content }) => {
  if (!content) return <div style={{ color: '#64748b', fontStyle: 'italic' }}>No data available</div>;

  // Split by double newlines to handle paragraphs
  const paragraphs = content.split('\n\n');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {paragraphs.map((p, i) => {
        // Check if paragraph starts with a header like **Header**:
        const headerMatch = p.match(/^\*\*(.*?)\*\*:\s*(.*)/s);
        
        if (headerMatch) {
          const [_, header, body] = headerMatch;
          return (
            <div key={i} style={{ 
              background: '#1e293b', 
              borderRadius: '8px', 
              padding: '12px',
              borderLeft: `4px solid ${
                header.includes('Rating') || header.includes('Recommendation') ? '#3b82f6' : 
                header.includes('Summary') || header.includes('Actions') ? '#10b981' : '#64748b'
              }`
            }}>
              <div style={{ 
                fontSize: '11px', 
                fontWeight: 'bold', 
                textTransform: 'uppercase', 
                color: '#94a3b8',
                marginBottom: '4px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                {header.includes('Rating') && <Target size={12} />}
                {header.includes('Action') && <AlertTriangle size={12} />}
                {header.includes('Rationale') && <Info size={12} />}
                {header}
              </div>
              <div style={{ 
                fontSize: '14px', 
                lineHeight: '1.6', 
                color: '#f8fafc',
                fontWeight: header.includes('Rating') ? 'bold' : 'normal'
              }}>
                {body}
              </div>
            </div>
          );
        }

        return (
          <p key={i} style={{ 
            margin: 0, 
            fontSize: '13px', 
            lineHeight: '1.7', 
            color: '#cbd5e1' 
          }}>
            {p.split(/(\*\*.*?\*\*)/g).map((part, j) => {
              if (part.startsWith('**') && part.endsWith('**')) {
                return <strong key={j} style={{ color: '#f8fafc' }}>{part.slice(2, -2)}</strong>;
              }
              return part;
            })}
          </p>
        );
      })}
    </div>
  );
};

const App = () => {
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState(null);
  const [reflections, setReflections] = useState([]);
  const [activeStatus, setActiveStatus] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/runs')
      .then(res => res.json())
      .then(data => {
        setRuns(data);
        if (data.length > 0) {
          setSelectedRun(data[0]);
        }
        setLoading(false);
      })
      .catch(err => console.error("Error fetching runs:", err));
      
    fetch('/api/stats').then(res => res.json()).then(setStats).catch(err => console.error("Error fetching stats:", err));
    fetch('/api/reflections').then(res => res.json()).then(setReflections).catch(err => console.error("Error fetching reflections:", err));

    // Poll for active status every 3 seconds
    const statusInterval = setInterval(() => {
      fetch('/api/status')
        .then(res => res.json())
        .then(data => {
          if (data.status === 'in_progress') {
            setActiveStatus(data);
          } else {
            setActiveStatus(null);
          }
        });
    }, 3000);

    return () => clearInterval(statusInterval);
  }, []);

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
      <div style={{ width: '300px', borderRight: '1px solid #1e293b', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Activity color="#3b82f6" />
          <h1 style={{ fontSize: '18px', fontWeight: 'bold', margin: 0 }}>TradingAgents</h1>
        </div>
        
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
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <header style={{ padding: '20px', borderBottom: '1px solid #1e293b', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '20px' }}>
              {activeStatus ? `🔴 ANALYZING ${activeStatus.ticker}...` : (selectedRun ? `${selectedRun.ticker} Analysis` : 'Select a run')}
            </h2>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              {activeStatus ? `Active Node: ${activeStatus.active_node}` : `Trade Date: ${selectedRun?.date}`}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '10px', color: '#64748b' }}>STATUS</div>
              <div style={{ color: activeStatus ? '#3b82f6' : '#10b981', fontSize: '14px', fontWeight: 'bold' }}>
                {activeStatus ? 'IN PROGRESS' : 'COMPLETED'}
              </div>
            </div>
            {!activeStatus && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '10px', color: '#64748b' }}>DECISION</div>
                <div style={{ color: '#3b82f6', fontSize: '14px', fontWeight: 'bold' }}>{runDetail?.final_trade_decision?.split('\n')[0] || '---'}</div>
              </div>
            )}
          </div>
        </header>

        {/* Workspace */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          <div style={{ marginBottom: '20px', borderRadius: '12px', overflow: 'hidden', border: '1px solid #1e293b' }}>
            <div style={{ padding: '12px', background: '#0f172a', borderBottom: '1px solid #1e293b', fontSize: '12px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layout size={14} /> AGENTIC FLOW VISUALIZATION
            </div>
            <FlowGraph runData={runDetail} activeStatus={activeStatus} />
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
