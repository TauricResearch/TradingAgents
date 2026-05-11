import React, { useState, useEffect } from 'react';
import { FileText, Clock, CheckCircle, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import { generateMockData } from '../utils/mockData';

function LogConsole() {
  const [logs, setLogs] = useState([]);
  const [filterLevel, setFilterLevel] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const data = generateMockData();
    setLogs(data.logs);
  }, []);

  const filteredLogs = logs.filter(log => {
    const matchesLevel = filterLevel === 'all' || log.level === filterLevel;
    const matchesSearch = searchTerm === '' || 
      log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.agent.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesLevel && matchesSearch;
  });

  const getLevelIcon = (level) => {
    switch(level) {
      case 'SUCCESS': return <CheckCircle size={14} />;
      case 'WARNING': return <AlertTriangle size={14} />;
      case 'ERROR': return <AlertCircle size={14} />;
      default: return <Info size={14} />;
    }
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">System Logs</h1>
        <p className="dashboard-subtitle">Real-time logging system with filtering and search capabilities</p>
      </div>

      {/* Controls */}
      <div style={{ marginBottom: 20, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Search logs..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            padding: '10px 15px',
            borderRadius: '8px',
            border: '1px solid #2d3748',
            background: '#1e1e2f',
            color: '#fff',
            flex: 1,
            minWidth: 200,
          }}
        />
        {['all', 'INFO', 'WARNING', 'ERROR', 'SUCCESS'].map(level => (
          <button
            key={level}
            onClick={() => setFilterLevel(level)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: filterLevel === level ? '#4facfe' : '#2d3748',
              color: filterLevel === level ? '#fff' : '#a0aec0',
              cursor: 'pointer',
              fontWeight: filterLevel === level ? 600 : 400,
              textTransform: 'uppercase',
              fontSize: '0.75rem',
            }}
          >
            {level}
          </button>
        ))}
      </div>

      {/* Log Console */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15 }}>
          <h3 className="card-title" style={{ marginBottom: 0 }}>
            <FileText size={20} />
            Live Log Stream ({filteredLogs.length} entries)
          </h3>
          <button 
            onClick={() => setLogs([])}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              background: '#f56565',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '0.85rem',
            }}
          >
            Clear Logs
          </button>
        </div>
        
        <div className="log-console">
          {filteredLogs.length === 0 ? (
            <div style={{ color: '#a0aec0', textAlign: 'center', padding: 20 }}>
              No logs match your filters
            </div>
          ) : (
            filteredLogs.map((log, idx) => (
              <div key={idx} className="log-entry">
                <span className="log-timestamp">{formatTimestamp(log.timestamp)}</span>
                <span className={`log-level ${log.level}`}>
                  {getLevelIcon(log.level)}
                  {log.level}
                </span>
                <span className="log-message">
                  <strong style={{ color: '#4facfe' }}>{log.agent}:</strong> {log.message}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Log Statistics */}
      <div className="dashboard-grid" style={{ marginTop: 30 }}>
        <div className="metric-card">
          <div className="metric-label">Total Logs</div>
          <div className="metric-value">{logs.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Success Messages</div>
          <div className="metric-value" style={{ color: '#48bb78' }}>
            {logs.filter(l => l.level === 'SUCCESS').length}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Warnings</div>
          <div className="metric-value" style={{ color: '#ffc107' }}>
            {logs.filter(l => l.level === 'WARNING').length}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Errors</div>
          <div className="metric-value" style={{ color: '#f56565' }}>
            {logs.filter(l => l.level === 'ERROR').length}
          </div>
        </div>
      </div>
    </div>
  );
}

export default LogConsole;
