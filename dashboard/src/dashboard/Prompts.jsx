import React, { useState, useEffect } from 'react';
import { Settings, Save, Edit3, Trash2, Plus, Code, Info, History } from 'lucide-react';
import { generateMockData } from '../utils/mockData';

function Prompts() {
  const [prompts, setPrompts] = useState([]);
  const [selectedPrompt, setSelectedPrompt] = useState(null);

  useEffect(() => {
    const data = generateMockData();
    setPrompts(data.prompts);
    if (data.prompts.length > 0) {
      setSelectedPrompt(data.prompts[0]);
    }
  }, []);

  return (
    <div className="fade-in">
      <div className="dashboard-header">
        <h1 className="dashboard-title">Prompt Configuration</h1>
        <p className="dashboard-subtitle">Manage agent system instructions and LLM parameters</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '350px 1fr', gap: '20px' }}>
        {/* Prompt Sidebar */}
        <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
          <div style={{ padding: '15px 20px', borderBottom: '1px solid #2d3748', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Prompts</h3>
            <button className="btn btn-primary" style={{ padding: '5px 10px', fontSize: '0.8rem' }}>
              <Plus size={14} />
            </button>
          </div>
          <div className="prompt-list" style={{ maxHeight: 'calc(100vh - 250px)', overflowY: 'auto' }}>
            {prompts.map((prompt) => (
              <div 
                key={prompt.id} 
                className={`prompt-list-item ${selectedPrompt?.id === prompt.id ? 'active' : ''}`}
                onClick={() => setSelectedPrompt(prompt)}
                style={{ 
                  padding: '15px 20px', 
                  cursor: 'pointer', 
                  borderBottom: '1px solid #2d3748',
                  background: selectedPrompt?.id === prompt.id ? 'rgba(79, 172, 254, 0.1)' : 'transparent',
                  borderLeft: selectedPrompt?.id === prompt.id ? '4px solid #4facfe' : '4px solid transparent'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: '0.7rem', color: '#4facfe', fontWeight: 600 }}>{prompt.category}</span>
                  <span style={{ fontSize: '0.7rem', color: '#718096' }}>v{prompt.version}</span>
                </div>
                <div style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: 5 }}>{prompt.name}</div>
                <div style={{ fontSize: '0.8rem', color: '#a0aec0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {prompt.description}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Prompt Editor (Mockup) */}
        <div className="card">
          {selectedPrompt ? (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                <div>
                  <h2 style={{ margin: '0 0 5px 0' }}>{selectedPrompt.name}</h2>
                  <div style={{ display: 'flex', gap: 15, color: '#a0aec0', fontSize: '0.85rem' }}>
                    <span>Category: <strong>{selectedPrompt.category}</strong></span>
                    <span>Last Updated: <strong>{selectedPrompt.lastUpdated}</strong></span>
                    <span>Version: <strong>{selectedPrompt.version}</strong></span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10 }}>
                  <button className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <History size={18} />
                    History
                  </button>
                  <button className="btn btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Save size={18} />
                    Save Changes
                  </button>
                </div>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', marginBottom: 8, fontSize: '0.9rem', color: '#a0aec0' }}>System Instructions</label>
                <textarea 
                  style={{ 
                    width: '100%', 
                    height: '300px', 
                    background: '#1a1a2e', 
                    border: '1px solid #2d3748', 
                    borderRadius: '8px', 
                    color: '#e2e8f0', 
                    padding: '15px', 
                    fontFamily: 'monospace',
                    fontSize: '0.95rem',
                    lineHeight: '1.6',
                    resize: 'none'
                  }}
                  defaultValue={`You are the ${selectedPrompt.name}. Your objective is to ${selectedPrompt.description.toLowerCase()}.

Guidelines:
1. Always base decisions on verified market data.
2. Maintain a neutral, analytical tone.
3. Quantify risk whenever possible.
4. If data is ambiguous, state your uncertainty level clearly.

Formatting:
All output must be valid JSON in the following format:
{
  "analysis": "...",
  "confidence": 0.0-1.0,
  "reasoning": "..."
}`}
                />
              </div>

              <div className="dashboard-grid" style={{ marginTop: 'auto' }}>
                <div style={{ padding: '15px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid #2d3748' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, color: '#4facfe' }}>
                    <Info size={16} />
                    <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Model Configuration</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '0.85rem' }}>
                    <div style={{ color: '#a0aec0' }}>Model:</div>
                    <div style={{ textAlign: 'right' }}>GPT-4 Turbo</div>
                    <div style={{ color: '#a0aec0' }}>Temperature:</div>
                    <div style={{ textAlign: 'right' }}>0.7</div>
                    <div style={{ color: '#a0aec0' }}>Max Tokens:</div>
                    <div style={{ textAlign: 'right' }}>2048</div>
                  </div>
                </div>
                <div style={{ padding: '15px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid #2d3748' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, color: '#4facfe' }}>
                    <Code size={16} />
                    <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Schema Validation</span>
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#a0aec0' }}>
                    Strict JSON mode is enabled. The output will be validated against the TradingAgents protocol schema.
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ height: '400px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', color: '#718096' }}>
              <Settings size={48} style={{ marginBottom: 15, opacity: 0.5 }} />
              <p>Select a prompt from the list to view and edit</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Prompts;
