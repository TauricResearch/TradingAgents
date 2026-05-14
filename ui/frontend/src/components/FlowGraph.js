import React, { useMemo } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  MiniMap,
  Handle,
  Position
} from 'reactflow';
import 'reactflow/dist/style.css';

// Custom Node component for Agents
const AgentNode = ({ data }) => {
  const isSelected = data.isActive;
  return (
    <div style={{
      padding: '10px',
      borderRadius: '8px',
      background: isSelected ? '#3b82f6' : '#1e293b',
      color: 'white',
      border: `2px solid ${isSelected ? '#60a5fa' : '#475569'}`,
      width: '180px',
      fontSize: '12px',
      boxShadow: isSelected ? '0 0 15px rgba(59, 130, 246, 0.5)' : 'none',
      transition: 'all 0.3s ease'
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{data.label}</div>
      <div style={{ fontSize: '10px', opacity: 0.8 }}>{data.status || 'Waiting...'}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
};

const nodeTypes = {
  agent: AgentNode,
};

const FlowGraph = ({ runData }) => {
  const { nodes, edges } = useMemo(() => {
    if (!runData) return { nodes: [], edges: [] };

    // Define the static structure of the TradingAgents graph
    const rawNodes = [
      { id: 'start', type: 'input', data: { label: 'Start' }, position: { x: 250, y: 0 } },
      { id: 'market', type: 'agent', data: { label: 'Market Analyst', status: runData.market_report ? 'Complete' : 'Pending' }, position: { x: 250, y: 100 } },
      { id: 'sentiment', type: 'agent', data: { label: 'Sentiment Analyst', status: runData.sentiment_report ? 'Complete' : 'Pending' }, position: { x: 250, y: 200 } },
      { id: 'news', type: 'agent', data: { label: 'News Analyst', status: runData.news_report ? 'Complete' : 'Pending' }, position: { x: 250, y: 300 } },
      { id: 'fundamentals', type: 'agent', data: { label: 'Fundamentals Analyst', status: runData.fundamentals_report ? 'Complete' : 'Pending' }, position: { x: 250, y: 400 } },
      { id: 'bull', type: 'agent', data: { label: 'Bull Researcher', status: 'Debating...' }, position: { x: 100, y: 500 } },
      { id: 'bear', type: 'agent', data: { label: 'Bear Researcher', status: 'Debating...' }, position: { x: 400, y: 500 } },
      { id: 'manager', type: 'agent', data: { label: 'Research Manager', status: runData.investment_plan ? 'Synthesized' : 'Waiting' }, position: { x: 250, y: 600 } },
      { id: 'trader', type: 'agent', data: { label: 'Trader', status: runData.trader_investment_decision ? 'Proposed' : 'Waiting' }, position: { x: 250, y: 700 } },
      { id: 'pm', type: 'agent', data: { label: 'Portfolio Manager', status: runData.final_trade_decision ? 'Final Decision' : 'Reviewing' }, position: { x: 250, y: 800 } },
      { id: 'end', type: 'output', data: { label: 'Decision Reached' }, position: { x: 250, y: 900 } },
    ];

    const rawEdges = [
      { id: 'e1-2', source: 'start', target: 'market', animated: true },
      { id: 'e2-3', source: 'market', target: 'sentiment', animated: true },
      { id: 'e3-4', source: 'sentiment', target: 'news', animated: true },
      { id: 'e4-5', source: 'news', target: 'fundamentals', animated: true },
      { id: 'e5-6', source: 'fundamentals', target: 'bull', animated: true },
      { id: 'e5-7', source: 'fundamentals', target: 'bear', animated: true },
      { id: 'e6-8', source: 'bull', target: 'manager', animated: true },
      { id: 'e7-8', source: 'bear', target: 'manager', animated: true },
      { id: 'e8-9', source: 'manager', target: 'trader', animated: true },
      { id: 'e9-10', source: 'trader', target: 'pm', animated: true },
      { id: 'e10-11', source: 'pm', target: 'end' },
    ];

    return { nodes: rawNodes, edges: rawEdges };
  }, [runData]);

  return (
    <div style={{ width: '100%', height: '600px', background: '#0f172a' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background color="#334155" gap={20} />
        <Controls />
        <MiniMap nodeColor={(n) => n.type === 'agent' ? '#3b82f6' : '#94a3b8'} />
      </ReactFlow>
    </div>
  );
};

export default FlowGraph;
