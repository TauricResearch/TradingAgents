import React, { useState, useEffect } from 'react';
import { Activity, TrendingUp, Users, CheckCircle, Briefcase } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { generateMockData } from '../utils/mockData';

function Overview() {
  const [data, setData] = useState(null);

  useEffect(() => {
    setData(generateMockData());
  }, []);

  if (!data) return <div>Loading...</div>;

  const activeAgents = data.agents.filter(a => a.status === 'active').length;
  const processingAgents = data.agents.filter(a => a.status === 'processing').length;
  const avgConfidence = (data.trades.reduce((sum, t) => sum + t.confidence, 0) / data.trades.length * 100).toFixed(1);
  const successfulTrades = data.trades.filter(t => t.rating === 'Buy' || t.rating === 'Overweight').length;

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">TradingAgents Overview</h1>
        <p className="dashboard-subtitle">Multi-Agent LLM Financial Trading Framework Dashboard</p>
      </div>

      {/* Metrics Grid */}
      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">Active Agents</div>
          <div className="metric-value">{activeAgents}</div>
          <div className="metric-change positive">
            <Activity size={14} style={{ display: 'inline', marginRight: 4 }} />
            {processingAgents} processing
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Total Trades</div>
          <div className="metric-value">{data.trades.length}</div>
          <div className="metric-change positive">
            <CheckCircle size={14} style={{ display: 'inline', marginRight: 4 }} />
            {successfulTrades} bullish signals
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Avg Confidence</div>
          <div className="metric-value">{avgConfidence}%</div>
          <div className="metric-change positive">
            <TrendingUp size={14} style={{ display: 'inline', marginRight: 4 }} />
            High conviction
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Portfolio Value</div>
          <div className="metric-value">${(data.performanceData[data.performanceData.length - 1].portfolio / 1000).toFixed(1)}K</div>
          <div className="metric-change positive">
            <TrendingUp size={14} style={{ display: 'inline', marginRight: 4 }} />
            +6.2% vs benchmark
          </div>
        </div>
      </div>

      {/* Performance Chart */}
      <div className="card" style={{ marginBottom: 30 }}>
        <h3 className="card-title">
          <TrendingUp size={20} />
          Portfolio Performance vs Benchmark
        </h3>
        <div style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.performanceData}>
              <defs>
                <linearGradient id="colorPortfolio" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4facfe" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#4facfe" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorBenchmark" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a0aec0" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#a0aec0" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis dataKey="date" stroke="#a0aec0" />
              <YAxis stroke="#a0aec0" />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e1e2f', 
                  border: '1px solid #2d3748',
                  borderRadius: '8px'
                }} 
              />
              <Area type="monotone" dataKey="portfolio" stroke="#4facfe" fillOpacity={1} fill="url(#colorPortfolio)" />
              <Area type="monotone" dataKey="benchmark" stroke="#a0aec0" fillOpacity={1} fill="url(#colorBenchmark)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent Trades & Agent Status */}
      <div className="dashboard-grid">
        <div className="card">
          <h3 className="card-title">
            <Users size={20} />
            Agent Status
          </h3>
          <div>
            {data.agents.slice(0, 6).map((agent, idx) => (
              <div key={idx} className="agent-status">
                <div className="agent-info">
                  <div className="agent-icon">{agent.icon}</div>
                  <div>
                    <div className="agent-name">{agent.name}</div>
                    <div className="agent-role">{agent.role}</div>
                  </div>
                </div>
                <span className={`status-badge status-${agent.status}`}>
                  {agent.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">
            <Briefcase size={20} />
            Recent Trades
          </h3>
          <table className="trade-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Date</th>
                <th>Rating</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.slice(0, 5).map((trade) => (
                <tr key={trade.id}>
                  <td style={{ fontWeight: 600 }}>{trade.ticker}</td>
                  <td>{trade.date}</td>
                  <td className={`rating-${trade.rating.toLowerCase()}`}>{trade.rating}</td>
                  <td>{(trade.confidence * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default Overview;
