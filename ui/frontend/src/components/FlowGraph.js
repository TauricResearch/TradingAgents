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
  const [showTooltip, setShowTooltip] = React.useState(false);

  return (
    <div 
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      style={{
        padding: '10px',
        borderRadius: '8px',
        background: isSelected ? '#3b82f6' : '#1e293b',
        color: 'white',
        border: `2px solid ${isSelected ? '#60a5fa' : '#475569'}`,
        width: '180px',
        fontSize: '12px',
        boxShadow: isSelected ? '0 0 15px rgba(59, 130, 246, 0.5)' : 'none',
        transition: 'all 0.3s ease',
        cursor: 'pointer',
        position: 'relative'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{data.label}</div>
      <div style={{ fontSize: '10px', opacity: 0.8 }}>{data.status || 'Waiting...'}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
      
      {showTooltip && (
        <div style={{
          position: 'absolute',
          bottom: '100%',
          left: '50%',
          transform: 'translateX(-50%)',
          marginBottom: '10px',
          padding: '8px',
          background: '#0f172a',
          border: '1px solid #334155',
          borderRadius: '4px',
          width: '200px',
          zIndex: 1000,
          pointerEvents: 'none',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
        }}>
          <div style={{ fontWeight: 'bold', fontSize: '11px', marginBottom: '4px', color: '#60a5fa' }}>PURPOSE</div>
          <div style={{ fontSize: '10px', lineHeight: '1.4' }}>{data.description}</div>
        </div>
      )}
    </div>
  );
};

const nodeTypes = {
  agent: AgentNode,
};

const FlowGraph = ({ runData, activeStatus, onNodeClick }) => {
  const { nodes, edges } = useMemo(() => {
    // If we have an active run, we show it, otherwise show historical data
    const isLive = !!activeStatus;
    const currentData = isLive ? {} : (runData || {});
    const activeNode = activeStatus?.active_node;

    const descriptions = {
      market: "Analyzes price action, technical indicators, and volume patterns to identify trends.",
      sentiment: "Monitors market mood by analyzing news sentiment and social signals.",
      news: "Synthesizes global macro headlines and tracks corporate insider transactions.",
      fundamentals: "Evaluates financial health using balance sheets, income statements, and ratios.",
      bull: "Constructs the strongest possible 'Buy' case by identifying positive catalysts.",
      bear: "Challenges the consensus by identifying risks and potential 'Sell' catalysts.",
      manager: "Synthesizes competing researcher views into a single balanced investment plan.",
      trader: "Calculates specific entry, exit, and stop-loss price targets for execution.",
      pm: "Makes the final capital allocation decision and issues the official rating."
    };

    const rawNodes = [
      { id: 'start', type: 'input', data: { label: 'Start' }, position: { x: 250, y: 0 } },
      { 
        id: 'market', 
        type: 'agent', 
        data: { 
            label: 'Market Analyst', 
            description: descriptions.market,
            status: currentData.market_report ? 'Complete' : 'Pending',
            isActive: activeNode === 'market'
        }, 
        position: { x: 250, y: 100 } 
      },
      { 
        id: 'sentiment', 
        type: 'agent', 
        data: { 
            label: 'Sentiment Analyst', 
            description: descriptions.sentiment,
            status: currentData.sentiment_report ? 'Complete' : 'Pending',
            isActive: activeNode === 'social'
        }, 
        position: { x: 250, y: 200 } 
      },
      { 
        id: 'news', 
        type: 'agent', 
        data: { 
            label: 'News Analyst', 
            description: descriptions.news,
            status: currentData.news_report ? 'Complete' : 'Pending',
            isActive: activeNode === 'news'
        }, 
        position: { x: 250, y: 300 } 
      },
      { 
        id: 'fundamentals', 
        type: 'agent', 
        data: { 
            label: 'Fundamentals Analyst', 
            description: descriptions.fundamentals,
            status: currentData.fundamentals_report ? 'Complete' : 'Pending',
            isActive: activeNode === 'fundamentals'
        }, 
        position: { x: 250, y: 400 } 
      },
      { 
        id: 'bull', 
        type: 'agent', 
        data: { 
            label: 'Bull Researcher', 
            description: descriptions.bull,
            status: isLive ? 'Simulating...' : 'Complete',
            isActive: activeNode === 'bull_researcher'
        }, 
        position: { x: 100, y: 500 } 
      },
      { 
        id: 'bear', 
        type: 'agent', 
        data: { 
            label: 'Bear Researcher', 
            description: descriptions.bear,
            status: isLive ? 'Simulating...' : 'Complete',
            isActive: activeNode === 'bear_researcher'
        }, 
        position: { x: 400, y: 500 } 
      },
      { 
        id: 'manager', 
        type: 'agent', 
        data: { 
            label: 'Research Manager', 
            description: descriptions.manager,
            status: currentData.investment_plan ? 'Synthesized' : 'Waiting',
            isActive: activeNode === 'research_manager'
        }, 
        position: { x: 250, y: 600 } 
      },
      { 
        id: 'trader', 
        type: 'agent', 
        data: { 
            label: 'Trader', 
            description: descriptions.trader,
            status: currentData.trader_investment_decision ? 'Proposed' : 'Waiting',
            isActive: activeNode === 'trader'
        }, 
        position: { x: 250, y: 700 } 
      },
      { 
        id: 'pm', 
        type: 'agent', 
        data: { 
            label: 'Portfolio Manager', 
            description: descriptions.pm,
            status: currentData.final_trade_decision ? 'Final Decision' : 'Reviewing',
            isActive: activeNode === 'risk_management'
        }, 
        position: { x: 250, y: 800 } 
      },
      { id: 'end', type: 'output', data: { label: 'Decision Reached' }, position: { x: 250, y: 900 } },
    ];

    const rawEdges = [
      { id: 'e1-2', source: 'start', target: 'market', animated: isLive || !!currentData.market_report },
      { id: 'e2-3', source: 'market', target: 'sentiment', animated: isLive || !!currentData.sentiment_report },
      { id: 'e3-4', source: 'sentiment', target: 'news', animated: isLive || !!currentData.news_report },
      { id: 'e4-5', source: 'news', target: 'fundamentals', animated: isLive || !!currentData.fundamentals_report },
      { id: 'e5-6', source: 'fundamentals', target: 'bull', animated: isLive || !!currentData.investment_plan },
      { id: 'e5-7', source: 'fundamentals', target: 'bear', animated: isLive || !!currentData.investment_plan },
      { id: 'e6-8', source: 'bull', target: 'manager', animated: isLive || !!currentData.investment_plan },
      { id: 'e7-8', source: 'bear', target: 'manager', animated: isLive || !!currentData.investment_plan },
      { id: 'e8-9', source: 'manager', target: 'trader', animated: isLive || !!currentData.trader_investment_decision },
      { id: 'e9-10', source: 'trader', target: 'pm', animated: isLive || !!currentData.final_trade_decision },
      { id: 'e10-11', source: 'pm', target: 'end' },
    ];

    return { nodes: rawNodes, edges: rawEdges };
  }, [runData, activeStatus]);

  return (
    <div style={{ width: '100%', height: '600px', background: '#0f172a' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(event, node) => onNodeClick && onNodeClick(node.data)}
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
