import React, { useState, useEffect } from 'react';
import { Users, Activity } from 'lucide-react';
import { generateMockData } from '../utils/mockData';

function AgentMonitor() {
  const [agents, setAgents] = useState([]);
  const [selectedPhase, setSelectedPhase] = useState('all');

  useEffect(() => {
    const data = generateMockData();
    setAgents(data.agents);
  }, []);

  const phases = ['all', 'Phase 1 - Analysis', 'Phase 2 - Debate', 'Phase 3 - Planning', 'Phase 4 - Risk', 'Phase 5 - Decision'];
  
  const filteredAgents = selectedPhase === 'all' 
    ? agents 
    : agents.filter(a => a.role === selectedPhase);

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Agent Monitor</h1>
        <p className="dashboard-subtitle">Real-time monitoring of all 12 specialized LLM agents</p>
      </div>

      {/* Phase Filter */}
      <div style={{ marginBottom: 20, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {phases.map(phase => (
          <button
            key={phase}
            onClick={() => setSelectedPhase(phase)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: selectedPhase === phase ? '#4facfe' : '#2d3748',
              color: selectedPhase === phase ? '#fff' : '#a0aec0',
              cursor: 'pointer',
              fontWeight: selectedPhase === phase ? 600 : 400,
            }}
          >
            {phase === 'all' ? 'All Agents' : phase.split(' - ')[0]}
          </button>
        ))}
      </div>

      {/* Agent Grid */}
      <div className="dashboard-grid">
        {filteredAgents.map((agent, idx) => (
          <div key={idx} className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 15, marginBottom: 15 }}>
              <div className="agent-icon" style={{ width: 50, height: 50, fontSize: '1.5rem' }}>
                {agent.icon}
              </div>
              <div>
                <h3 style={{ color: '#fff', marginBottom: 4 }}>{agent.name}</h3>
                <p style={{ color: '#a0aec0', fontSize: '0.9rem' }}>{agent.role}</p>
              </div>
            </div>
            
            <div style={{ marginTop: 15 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ color: '#a0aec0', fontSize: '0.85rem' }}>Status</span>
                <span className={`status-badge status-${agent.status}`}>{agent.status}</span>
              </div>
              
              <div style={{ display: 'flex', gap: 8, marginTop: 15 }}>
                <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: '#1a1a2e', borderRadius: '6px' }}>
                  <div style={{ color: '#4facfe', fontSize: '1.2rem', fontWeight: 600 }}>
                    {Math.floor(Math.random() * 50) + 50}ms
                  </div>
                  <div style={{ color: '#a0aec0', fontSize: '0.75rem' }}>Latency</div>
                </div>
                <div style={{ flex: 1, textAlign: 'center', padding: '8px', background: '#1a1a2e', borderRadius: '6px' }}>
                  <div style={{ color: '#48bb78', fontSize: '1.2rem', fontWeight: 600 }}>
                    {Math.floor(Math.random() * 100) + 200}
                  </div>
                  <div style={{ color: '#a0aec0', fontSize: '0.75rem' }}>Tokens</div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Architecture Info */}
      <div className="card" style={{ marginTop: 30 }}>
        <h3 className="card-title">
          <Activity size={20} />
          Multi-Agent Pipeline Architecture
        </h3>
        <div style={{ color: '#a0aec0', lineHeight: 1.8 }}>
          <p><strong style={{ color: '#4facfe' }}>Phase 1:</strong> Four analyst agents (Market, Social Media, News, Fundamentals) gather and analyze data using tool nodes connected to yfinance and Alpha Vantage.</p>
          <p><strong style={{ color: '#4facfe' }}>Phase 2:</strong> Bull and Bear researchers debate investment thesis, synthesized by Research Manager into structured ResearchPlan.</p>
          <p><strong style={{ color: '#4facfe' }}>Phase 3:</strong> Trader agent generates structured TraderProposal with entry price, stop loss, and position sizing.</p>
          <p><strong style={{ color: '#4facfe' }}>Phase 4:</strong> Three risk analysts (Aggressive, Conservative, Neutral) debate risk factors through multiple rounds.</p>
          <p><strong style={{ color: '#4facfe' }}>Phase 5:</strong> Portfolio Manager produces final structured PortfolioDecision with Buy/Overweight/Hold/Underweight/Sell rating.</p>
        </div>
      </div>
    </div>
  );
}

export default AgentMonitor;
