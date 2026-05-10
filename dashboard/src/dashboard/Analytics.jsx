import React, { useState, useEffect } from 'react';
import { BarChart3, TrendingUp } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts';
import { generateMockData } from '../utils/mockData';

const COLORS = ['#4facfe', '#48bb78', '#ffc107', '#f56565', '#a0aec0'];

function Analytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    setData(generateMockData());
  }, []);

  if (!data) return <div>Loading...</div>;

  // Rating distribution for pie chart
  const ratingDistribution = [
    { name: 'Buy', value: data.trades.filter(t => t.rating === 'Buy').length },
    { name: 'Overweight', value: data.trades.filter(t => t.rating === 'Overweight').length },
    { name: 'Hold', value: data.trades.filter(t => t.rating === 'Hold').length },
    { name: 'Sell', value: data.trades.filter(t => t.rating === 'Sell').length },
  ].filter(r => r.value > 0);

  // Agent activity simulation
  const agentActivity = data.agents.map(agent => ({
    name: agent.name.split(' ')[0],
    activity: Math.floor(Math.random() * 100) + 50,
    latency: Math.floor(Math.random() * 50) + 20,
  }));

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Analytics</h1>
        <p className="dashboard-subtitle">Performance metrics and statistical analysis</p>
      </div>

      {/* Charts Grid */}
      <div className="dashboard-grid">
        {/* Rating Distribution */}
        <div className="card">
          <h3 className="card-title">
            <BarChart3 size={20} />
            Rating Distribution
          </h3>
          <div style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={ratingDistribution}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {ratingDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#1e1e2f', 
                    border: '1px solid #2d3748',
                    borderRadius: '8px'
                  }} 
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Agent Activity */}
        <div className="card">
          <h3 className="card-title">
            <Activity size={20} />
            Agent Activity Level
          </h3>
          <div style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={agentActivity}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                <XAxis dataKey="name" stroke="#a0aec0" angle={-45} textAnchor="end" height={60} />
                <YAxis stroke="#a0aec0" />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#1e1e2f', 
                    border: '1px solid #2d3748',
                    borderRadius: '8px'
                  }} 
                />
                <Bar dataKey="activity" fill="#4facfe" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Confidence Analysis */}
      <div className="card" style={{ marginTop: 20 }}>
        <h3 className="card-title">
          <TrendingUp size={20} />
          Confidence Score Analysis by Trade
        </h3>
        <div style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.trades.map((t, i) => ({ ...t, index: i + 1 }))}>
              <defs>
                <linearGradient id="colorConfidence" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#48bb78" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#48bb78" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
              <XAxis dataKey="ticker" stroke="#a0aec0" />
              <YAxis stroke="#a0aec0" domain={[0, 1]} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e1e2f', 
                  border: '1px solid #2d3748',
                  borderRadius: '8px'
                }}
                labelFormatter={(label) => `Ticker: ${label}`}
                formatter={(value) => [`${(value * 100).toFixed(1)}%`, 'Confidence']}
              />
              <Area type="monotone" dataKey="confidence" stroke="#48bb78" fillOpacity={1} fill="url(#colorConfidence)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="dashboard-grid" style={{ marginTop: 30 }}>
        <div className="metric-card">
          <div className="metric-label">Portfolio Return</div>
          <div className="metric-value" style={{ color: '#48bb78' }}>+6.2%</div>
          <div className="metric-change positive">Outperforming benchmark</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Win Rate</div>
          <div className="metric-value" style={{ color: '#4facfe' }}>
            {((data.trades.filter(t => t.confidence > 0.7).length / data.trades.length) * 100).toFixed(1)}%
          </div>
          <div className="metric-change positive">High confidence trades</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Avg Confidence</div>
          <div className="metric-value" style={{ color: '#ffc107' }}>
            {(data.trades.reduce((sum, t) => sum + t.confidence, 0) / data.trades.length * 100).toFixed(1)}%
          </div>
          <div className="metric-change">Across all decisions</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Active Agents</div>
          <div className="metric-value" style={{ color: '#a0aec0' }}>
            {data.agents.filter(a => a.status === 'active' || a.status === 'processing').length}
          </div>
          <div className="metric-change">Currently operational</div>
        </div>
      </div>
    </div>
  );
}

export default Analytics;
