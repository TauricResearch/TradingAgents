import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Activity, 
  Users, 
  FileText, 
  Settings, 
  TrendingUp, 
  MessageSquare,
  Shield,
  Briefcase,
  BarChart3,
  Clock,
  CheckCircle
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';

// Import dashboard components
import Overview from './dashboard/Overview';
import AgentMonitor from './dashboard/AgentMonitor';
import TradeHistory from './dashboard/TradeHistory';
import LogConsole from './dashboard/LogConsole';
import Analytics from './dashboard/Analytics';
import Reports from './dashboard/Reports';
import Prompts from './dashboard/Prompts';

// Sidebar Navigation Component
function Sidebar() {
  const location = useLocation();
  
  const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Overview' },
    { path: '/agents', icon: Users, label: 'Agent Monitor' },
    { path: '/trades', icon: Briefcase, label: 'Trade History' },
    { path: '/reports', icon: FileText, label: 'Intelligence Reports' },
    { path: '/logs', icon: Clock, label: 'Logs' },
    { path: '/analytics', icon: BarChart3, label: 'Analytics' },
    { path: '/prompts', icon: MessageSquare, label: 'Prompts' },
  ];

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <TrendingUp size={28} />
          <span>TradingAgents</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          return (
            <Link 
              key={item.path} 
              to={item.path} 
              className={`nav-item ${isActive ? 'active' : ''}`}
            >
              <Icon size={20} className="nav-icon" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

// Main App Component
function App() {
  return (
    <Router>
      <div style={{ display: 'flex' }}>
        <Sidebar />
        <div className="main-content">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/agents" element={<AgentMonitor />} />
            <Route path="/trades" element={<TradeHistory />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/logs" element={<LogConsole />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/prompts" element={<Prompts />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}

export default App;
