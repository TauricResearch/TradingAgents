import React, { useState, useEffect } from 'react';
import { Briefcase, TrendingUp } from 'lucide-react';
import { generateMockData } from '../utils/mockData';

function TradeHistory() {
  const [trades, setTrades] = useState([]);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    const data = generateMockData();
    setTrades(data.trades);
  }, []);

  const filteredTrades = filter === 'all' 
    ? trades 
    : trades.filter(t => t.rating.toLowerCase() === filter);

  const getRatingClass = (rating) => {
    return `rating-${rating.toLowerCase()}`;
  };

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Trade History</h1>
        <p className="dashboard-subtitle">Historical trade decisions with confidence scores and ratings</p>
      </div>

      {/* Filter Buttons */}
      <div style={{ marginBottom: 20, display: 'flex', gap: 10 }}>
        {['all', 'buy', 'overweight', 'hold', 'sell'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: filter === f ? '#4facfe' : '#2d3748',
              color: filter === f ? '#fff' : '#a0aec0',
              cursor: 'pointer',
              textTransform: 'capitalize',
              fontWeight: filter === f ? 600 : 400,
            }}
          >
            {f === 'all' ? 'All Trades' : f}
          </button>
        ))}
      </div>

      {/* Trade Table */}
      <div className="card">
        <table className="trade-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Ticker</th>
              <th>Date</th>
              <th>Price</th>
              <th>Rating</th>
              <th>Confidence</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((trade) => (
              <tr key={trade.id}>
                <td>#{trade.id}</td>
                <td style={{ fontWeight: 600, fontSize: '1.1rem' }}>{trade.ticker}</td>
                <td>{trade.date}</td>
                <td>${trade.price.toFixed(2)}</td>
                <td className={getRatingClass(trade.rating)}>{trade.rating}</td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ flex: 1, height: 6, background: '#2d3748', borderRadius: 3, overflow: 'hidden', width: 80 }}>
                      <div 
                        style={{ 
                          width: `${trade.confidence * 100}%`, 
                          height: '100%', 
                          background: trade.confidence > 0.8 ? '#48bb78' : trade.confidence > 0.6 ? '#ffc107' : '#f56565',
                          borderRadius: 3
                        }} 
                      />
                    </div>
                    <span style={{ minWidth: 45 }}>{(trade.confidence * 100).toFixed(0)}%</span>
                  </div>
                </td>
                <td>
                  <button style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: 'none',
                    background: '#4facfe',
                    color: '#fff',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                  }}>
                    View Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Statistics */}
      <div className="dashboard-grid" style={{ marginTop: 30 }}>
        <div className="metric-card">
          <div className="metric-label">Total Trades</div>
          <div className="metric-value">{trades.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Bullish Signals</div>
          <div className="metric-value" style={{ color: '#48bb78' }}>
            {trades.filter(t => t.rating === 'Buy' || t.rating === 'Overweight').length}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Hold Ratings</div>
          <div className="metric-value" style={{ color: '#ffc107' }}>
            {trades.filter(t => t.rating === 'Hold').length}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Bearish Signals</div>
          <div className="metric-value" style={{ color: '#f56565' }}>
            {trades.filter(t => t.rating === 'Sell' || t.rating === 'Underweight').length}
          </div>
        </div>
      </div>
    </div>
  );
}

export default TradeHistory;
