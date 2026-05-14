import React, { useMemo } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Handle,
  Position
} from 'reactflow';
import 'reactflow/dist/style.css';

// Custom Node component for Agents
const AgentNode = ({ data }) => {
  const isSelected = data.isActive;
  const isComplete = ['Complete', 'Proposed', 'Final', 'Synthesized', 'Reviewing', 'Decision'].some(s => 
    data.status?.includes(s)
  ) && !isSelected;
  
  const [showTooltip, setShowTooltip] = React.useState(false);

  // Status colors: Amber for active, Green for complete, Slate for pending
  const getBgColor = () => {
    if (isSelected) return '#eab308'; // Amber
    if (isComplete) return '#10b981'; // Green
    return '#1e293b'; // Default Slate
  };

  const getBorderColor = () => {
    if (isSelected) return '#fde047';
    if (isComplete) return '#34d399';
    return '#475569';
  };

  return (
    <div 
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      style={{
        padding: '10px',
        borderRadius: '8px',
        background: getBgColor(),
        color: 'white',
        border: `2px solid ${getBorderColor()}`,
        width: '180px',
        fontSize: '12px',
        boxShadow: isSelected ? '0 0 20px rgba(234, 179, 8, 0.4)' : (isComplete ? '0 0 10px rgba(16, 185, 129, 0.2)' : 'none'),
        transition: 'all 0.3s ease',
        cursor: 'pointer',
        position: 'relative'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{data.label}</div>
      <div style={{ fontSize: '10px', opacity: 0.9, fontWeight: (isSelected || isComplete) ? 'bold' : 'normal' }}>
        {data.status || 'Waiting...'}
      </div>
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

    const analystIds = ['market', 'sentiment', 'news', 'fundamentals'];
    const downstreamIds = ['sync', 'bull', 'bear', 'manager', 'trader', 'pm', 'end'];
    
    // Check if the graph has moved past the analyst phase
    const isPastAnalysts = activeNode && downstreamIds.some(id => 
        activeNode.toLowerCase().includes(id.toLowerCase()) || 
        (id === 'pm' && activeNode.toLowerCase().includes('risk'))
    );

    const rawNodes = [
      { id: 'start', type: 'input', data: { label: 'Start' }, position: { x: 450, y: 0 } },
      { 
        id: 'market', 
        type: 'agent', 
        data: { 
            label: 'Market Analyst', 
            description: descriptions.market,
            status: (currentData.market_report || isPastAnalysts || (activeNode && activeNode.toLowerCase().includes('market'))) ? (activeNode && activeNode.toLowerCase().includes('market') ? 'Analyzing...' : 'Complete') : 'Pending',
            isActive: activeNode && activeNode.toLowerCase().includes('market')
        }, 
        position: { x: 0, y: 150 } 
      },
      { 
        id: 'sentiment', 
        type: 'agent', 
        data: { 
            label: 'Sentiment Analyst', 
            description: descriptions.sentiment,
            status: (currentData.sentiment_report || isPastAnalysts || (activeNode && (activeNode.toLowerCase().includes('social') || activeNode.toLowerCase().includes('sentiment')))) ? (activeNode && (activeNode.toLowerCase().includes('social') || activeNode.toLowerCase().includes('sentiment')) ? 'Analyzing...' : 'Complete') : 'Pending',
            isActive: activeNode && (activeNode.toLowerCase().includes('social') || activeNode.toLowerCase().includes('sentiment'))
        }, 
        position: { x: 300, y: 150 } 
      },
      { 
        id: 'news', 
        type: 'agent', 
        data: { 
            label: 'News Analyst', 
            description: descriptions.news,
            status: (currentData.news_report || isPastAnalysts || (activeNode && activeNode.toLowerCase().includes('news'))) ? (activeNode && activeNode.toLowerCase().includes('news') ? 'Analyzing...' : 'Complete') : 'Pending',
            isActive: activeNode && activeNode.toLowerCase().includes('news')
        }, 
        position: { x: 600, y: 150 } 
      },
      { 
        id: 'fundamentals', 
        type: 'agent', 
        data: { 
            label: 'Fundamentals Analyst', 
            description: descriptions.fundamentals,
            status: (currentData.fundamentals_report || isPastAnalysts || (activeNode && activeNode.toLowerCase().includes('fundamental'))) ? (activeNode && activeNode.toLowerCase().includes('fundamental') ? 'Analyzing...' : 'Complete') : 'Pending',
            isActive: activeNode && activeNode.toLowerCase().includes('fundamental')
        }, 
        position: { x: 900, y: 150 } 
      },
      {
        id: 'sync',
        data: { label: 'Analyst Synchronizer' },
        position: { x: 450, y: 300 },
        style: {
          background: (activeNode && activeNode.toLowerCase().includes('synchronizer')) ? '#eab308' : '#1e293b',
          color: 'white',
          border: '2px solid #475569',
          borderRadius: '8px',
          padding: '10px',
          width: '180px',
          textAlign: 'center'
        }
      },
      { 
        id: 'bull', 
        type: 'agent', 
        data: { 
            label: 'Bull Researcher', 
            description: descriptions.bull,
            status: (isLive && activeNode && activeNode.toLowerCase().includes('bull')) ? 'Analyzing...' : (currentData.investment_plan || (isLive && activeNode && ['bear', 'manager', 'trader', 'pm', 'risk'].some(s => activeNode.toLowerCase().includes(s))) ? 'Complete' : 'Pending'),
            isActive: activeNode && activeNode.toLowerCase().includes('bull')
        }, 
        position: { x: 300, y: 450 } 
      },
      { 
        id: 'bear', 
        type: 'agent', 
        data: { 
            label: 'Bear Researcher', 
            description: descriptions.bear,
            status: (isLive && activeNode && activeNode.toLowerCase().includes('bear')) ? 'Analyzing...' : (currentData.investment_plan || (isLive && activeNode && ['manager', 'trader', 'pm', 'risk'].some(s => activeNode.toLowerCase().includes(s))) ? 'Complete' : 'Pending'),
            isActive: activeNode && activeNode.toLowerCase().includes('bear')
        }, 
        position: { x: 600, y: 450 } 
      },
      { 
        id: 'manager', 
        type: 'agent', 
        data: { 
            label: 'Research Manager', 
            description: descriptions.manager,
            status: (currentData.investment_plan || (activeNode && activeNode.toLowerCase().includes('manager'))) ? (activeNode && activeNode.toLowerCase().includes('manager') ? 'Synthesizing...' : 'Synthesized') : 'Waiting',
            isActive: activeNode && activeNode.toLowerCase().includes('manager')
        }, 
        position: { x: 450, y: 600 } 
      },
      { 
        id: 'trader', 
        type: 'agent', 
        data: { 
            label: 'Trader', 
            description: descriptions.trader,
            status: (currentData.trader_investment_decision || (activeNode && activeNode.toLowerCase().includes('trader'))) ? (activeNode && activeNode.toLowerCase().includes('trader') ? 'Calculating...' : 'Proposed') : 'Waiting',
            isActive: activeNode && activeNode.toLowerCase().includes('trader')
        }, 
        position: { x: 450, y: 750 } 
      },
      { 
        id: 'pm', 
        type: 'agent', 
        data: { 
            label: 'Portfolio Manager', 
            description: descriptions.pm,
            status: (currentData.final_trade_decision || (activeNode && (activeNode.toLowerCase().includes('risk') || activeNode.toLowerCase().includes('portfolio')))) ? (activeNode && (activeNode.toLowerCase().includes('risk') || activeNode.toLowerCase().includes('portfolio')) ? 'Reviewing...' : 'Final Decision') : 'Waiting',
            isActive: activeNode && (activeNode.toLowerCase().includes('risk') || activeNode.toLowerCase().includes('portfolio'))
        }, 
        position: { x: 450, y: 900 } 
      },
      { 
        id: 'end', 
        type: 'output', 
        data: { label: 'Decision Reached' }, 
        position: { x: 450, y: 1050 },
        style: {
          background: (currentData.final_trade_decision || (activeStatus?.status === 'completed')) ? '#10b981' : '#1e293b',
          color: 'white',
          border: `2px solid ${(currentData.final_trade_decision || (activeStatus?.status === 'completed')) ? '#34d399' : '#475569'}`,
          borderRadius: '8px',
          padding: '10px',
          fontWeight: 'bold',
          width: '180px',
          textAlign: 'center'
        }
      },
    ];

    const rawEdges = [
      { id: 'start-market', source: 'start', target: 'market', animated: isLive },
      { id: 'start-sentiment', source: 'start', target: 'sentiment', animated: isLive },
      { id: 'start-news', source: 'start', target: 'news', animated: isLive },
      { id: 'start-fundamentals', source: 'start', target: 'fundamentals', animated: isLive },
      
      { id: 'market-sync', source: 'market', target: 'sync', animated: !!currentData.market_report },
      { id: 'sentiment-sync', source: 'sentiment', target: 'sync', animated: !!currentData.sentiment_report },
      { id: 'news-sync', source: 'news', target: 'sync', animated: !!currentData.news_report },
      { id: 'fundamentals-sync', source: 'fundamentals', target: 'sync', animated: !!currentData.fundamentals_report },

      { id: 'sync-bull', source: 'sync', target: 'bull', animated: isLive || !!currentData.investment_plan },
      { id: 'sync-bear', source: 'sync', target: 'bear', animated: isLive || !!currentData.investment_plan },
      
      { id: 'bull-manager', source: 'bull', target: 'manager', animated: isLive || !!currentData.investment_plan },
      { id: 'bear-manager', source: 'bear', target: 'manager', animated: isLive || !!currentData.investment_plan },
      
      { id: 'manager-trader', source: 'manager', target: 'trader', animated: isLive || !!currentData.trader_investment_decision },
      { id: 'trader-pm', source: 'trader', target: 'pm', animated: isLive || !!currentData.final_trade_decision },
      { id: 'pm-end', source: 'pm', target: 'end' },
    ];

    return { nodes: rawNodes, edges: rawEdges };
  }, [runData, activeStatus]);

  return (
    <div style={{ width: '100%', height: '600px', background: '#0f172a', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(event, node) => onNodeClick && onNodeClick(node.data)}
        fitView
      >
        <Background color="#334155" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
};

export default FlowGraph;
