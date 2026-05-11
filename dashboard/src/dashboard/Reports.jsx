import React, { useState, useEffect } from 'react';
import { FileText, Download, Filter, Search, Calendar, ChevronRight } from 'lucide-react';
import reportsData from '../data/reports.json';

function Reports() {
  const [reports, setReports] = useState(reportsData);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedReport, setSelectedReport] = useState(null);

  useEffect(() => {
    setReports(reportsData);
  }, []);

  const filteredReports = reports.filter(report => 
    report.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    report.author.toLowerCase().includes(searchTerm.toLowerCase()) ||
    report.summary.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (selectedReport) {
    return (
      <div className="fade-in">
        <div className="dashboard-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <button 
              onClick={() => setSelectedReport(null)}
              className="btn btn-secondary" 
              style={{ marginBottom: 15, display: 'flex', alignItems: 'center', gap: 5 }}
            >
              <ChevronRight size={16} style={{ transform: 'rotate(180deg)' }} />
              Back to Reports
            </button>
            <h1 className="dashboard-title">{selectedReport.title}</h1>
            <p className="dashboard-subtitle">{selectedReport.date} • By {selectedReport.author} • Rating: <span style={{ color: selectedReport.rating === 'Sell' ? '#f56565' : selectedReport.rating === 'Buy' ? '#48bb78' : '#ed8936' }}>{selectedReport.rating}</span></p>
          </div>
          <button className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Download size={18} />
            Export PDF
          </button>
        </div>

        <div className="card report-content" style={{ padding: '40px', lineHeight: 1.6 }}>
          <pre style={{ 
            whiteSpace: 'pre-wrap', 
            fontFamily: 'inherit', 
            color: '#e2e8f0',
            fontSize: '1rem',
            background: 'transparent',
            border: 'none',
            padding: 0
          }}>
            {selectedReport.content}
          </pre>
        </div>
      </div>
    );
  }

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Intelligence Reports</h1>
        <p className="dashboard-subtitle">Generated synthesis and analyst reports</p>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, gap: 15 }}>
          <div className="search-bar" style={{ flex: 1, margin: 0 }}>
            <Search size={18} />
            <input 
              type="text" 
              placeholder="Search reports by title, author, or content..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ width: '100%', background: 'transparent', border: 'none', color: 'white', outline: 'none', padding: '5px 10px' }}
            />
          </div>
          <button className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Filter size={18} />
            Filter
          </button>
        </div>

        <div className="reports-list">
          {filteredReports.map((report) => (
            <div key={report.id} className="report-item" style={{ 
              padding: '20px', 
              borderBottom: '1px solid #2d3748', 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              transition: 'background 0.2s'
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                  <span className={`status-badge`} style={{ 
                    background: report.type === 'Flash' ? 'rgba(245, 101, 101, 0.2)' : 'rgba(79, 172, 254, 0.2)',
                    color: report.type === 'Flash' ? '#f56565' : '#4facfe',
                    fontSize: '0.7rem'
                  }}>
                    {report.type}
                  </span>
                  <h4 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>{report.title}</h4>
                </div>
                <p style={{ color: '#a0aec0', fontSize: '0.9rem', marginBottom: 12, lineHeight: 1.5 }}>{report.summary}</p>
                <div style={{ display: 'flex', gap: 20, color: '#718096', fontSize: '0.8rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Calendar size={14} />
                    {report.date}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <FileText size={14} />
                    By {report.author}
                  </span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button className="btn btn-secondary" style={{ padding: '8px 12px' }} title="Download PDF">
                  <Download size={18} />
                </button>
                <button 
                  onClick={() => setSelectedReport(report)}
                  className="btn btn-primary" 
                  style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '8px 16px' }}
                >
                  View Report
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          ))}
          {filteredReports.length === 0 && (
            <div style={{ padding: '40px', textAlign: 'center', color: '#718096' }}>
              No reports found matching your search criteria.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Reports;
