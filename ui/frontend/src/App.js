import React, { useState, useEffect } from 'react';
import FlowGraph from './components/FlowGraph';
import { LineChart, Layout, History, Activity, ShieldCheck, ChevronRight } from 'lucide-react';

const App = () => {
  const [runs, setRuns] = useState([]);
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
            <h2 style={{ margin: 0, fontSize: '20px' }}>{selectedRun ? `${selectedRun.ticker} Analysis` : 'Select a run'}</h2>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>Trade Date: {selectedRun?.date}</div>
          </div>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '10px', color: '#64748b' }}>STATUS</div>
              <div style={{ color: '#10b981', fontSize: '14px', fontWeight: 'bold' }}>COMPLETED</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '10px', color: '#64748b' }}>DECISION</div>
              <div style={{ color: '#3b82f6', fontSize: '14px', fontWeight: 'bold' }}>{runDetail?.final_trade_decision?.split('\n')[0] || '---'}</div>
            </div>
          </div>
        </header>

        {/* Workspace */}
        <main style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          <div style={{ marginBottom: '20px', borderRadius: '12px', overflow: 'hidden', border: '1px solid #1e293b' }}>
            <div style={{ padding: '12px', background: '#0f172a', borderBottom: '1px solid #1e293b', fontSize: '12px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layout size={14} /> AGENTIC FLOW VISUALIZATION
            </div>
            <FlowGraph runData={runDetail} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <section style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px' }}>
              <h3 style={{ marginTop: 0, fontSize: '14px', color: '#3b82f6', borderBottom: '1px solid #1e293b', paddingBottom: '10px' }}>FINAL DECISION</h3>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: '12px', lineHeight: '1.6', color: '#cbd5e1' }}>
                {runDetail?.final_trade_decision}
              </pre>
            </section>
            
            <section style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px' }}>
              <h3 style={{ marginTop: 0, fontSize: '14px', color: '#eab308', borderBottom: '1px solid #1e293b', paddingBottom: '10px' }}>INVESTMENT PLAN</h3>
              <div style={{ fontSize: '12px', lineHeight: '1.6', color: '#cbd5e1' }}>
                {runDetail?.investment_plan}
              </div>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
};

export default App;
