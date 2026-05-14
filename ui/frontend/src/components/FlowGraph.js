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
    const isCompleted = activeStatus?.status === 'completed';

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

    // Robust 'reached' logic to prevent flickering during live runs
    const isPast = (targetNode) => {
        if (isCompleted) return true;
        if (!activeNode) return false;
        
        const n = activeNode.toLowerCase();
        const t = targetNode.toLowerCase();
        
        // Map of node completion triggers
        const completionMap = {
            'analysts': ['sync', 'bull', 'bear', 'manager', 'trader', 'pm', 'end', 'risk', 'analyst'],
            'sync': ['bull', 'bear', 'manager', 'trader', 'pm', 'end', 'risk', 'analyst'],
            'researchers': ['manager', 'trader', 'pm', 'end', 'risk', 'analyst'],
            'manager': ['trader', 'pm', 'end', 'risk', 'analyst'],
            'trader': ['pm', 'end', 'risk', 'analyst'],
            'pm': ['end']
        };

        const triggers = completionMap[t] || [];
        return triggers.some(trigger => n.includes(targetNode === 'analysts' ? '' : trigger) || n.includes(trigger));
    };

    // Specific check for analysts
    const analystsDone = isCompleted || currentData.market_report || (activeNode && ['sync', 'bull', 'bear', 'manager', 'trader', 'pm', 'end', 'risk', 'analyst'].some(id => activeNode.toLowerCase().includes(id)));
    const researchersDone = isCompleted || currentData.investment_plan || (activeNode && ['manager', 'trader', 'pm', 'end', 'risk', 'analyst'].some(id => activeNode.toLowerCase().includes(id)));
    const managerDone = isCompleted || currentData.investment_plan || (activeNode && ['trader', 'pm', 'end', 'risk', 'analyst'].some(id => activeNode.toLowerCase().includes(id)));
    const traderDone = isCompleted || currentData.trader_investment_decision || (activeNode && ['pm', 'end', 'risk', 'analyst'].some(id => activeNode.toLowerCase().includes(id)));
    const pmDone = isCompleted || currentData.final_trade_decision || (activeNode && ['end'].some(id => activeNode.toLowerCase().includes(id)));

    const rawNodes = [
      { id: 'start', type: 'input', data: { label: 'Start' }, position: { x: 450, y: 0 } },
      { 
        id: 'market', 
        type: 'agent', 
        data: { 
            label: 'Market Analyst', 
            description: descriptions.market,
            status: (activeNode && activeNode.toLowerCase().includes('market')) ? 'Analyzing...' : (analystsDone ? 'Complete' : 'Pending'),
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
            status: (activeNode && (activeNode.toLowerCase().includes('social') || activeNode.toLowerCase().includes('sentiment'))) ? 'Analyzing...' : (analystsDone ? 'Complete' : 'Pending'),
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
            status: (activeNode && activeNode.toLowerCase().includes('news')) ? 'Analyzing...' : (analystsDone ? 'Complete' : 'Pending'),
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
            status: (activeNode && activeNode.toLowerCase().includes('fundamental')) ? 'Analyzing...' : (analystsDone ? 'Complete' : 'Pending'),
            isActive: activeNode && activeNode.toLowerCase().includes('fundamental')
        }, 
        position: { x: 900, y: 150 } 
      },
      {
        id: 'sync',
        data: { label: 'Analyst Synchronizer' },
        position: { x: 450, y: 300 },
        style: {
          background: (activeNode && activeNode.toLowerCase().includes('synchronizer')) ? '#eab308' : (analystsDone ? '#10b981' : '#1e293b'),
          color: 'white',
          border: `2px solid ${analystsDone ? '#34d399' : '#475569'}`,
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
            status: (activeNode && activeNode.toLowerCase().includes('bull')) ? 'Analyzing...' : (researchersDone ? 'Complete' : 'Pending'),
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
            status: (activeNode && activeNode.toLowerCase().includes('bear')) ? 'Analyzing...' : (researchersDone ? 'Complete' : 'Pending'),
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
            status: (activeNode && activeNode.toLowerCase().includes('manager')) ? 'Synthesizing...' : (managerDone ? 'Synthesized' : 'Waiting'),
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
            status: (activeNode && activeNode.toLowerCase().includes('trader')) ? 'Calculating...' : (traderDone ? 'Proposed' : 'Waiting'),
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
            status: (activeNode && (activeNode.toLowerCase().includes('risk') || activeNode.toLowerCase().includes('portfolio'))) ? 'Reviewing...' : (pmDone ? 'Final Decision' : 'Waiting'),
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
          background: (isCompleted || currentData.final_trade_decision) ? '#10b981' : '#1e293b',
          color: 'white',
          border: `2px solid ${(isCompleted || currentData.final_trade_decision) ? '#34d399' : '#475569'}`,
          borderRadius: '8px',
          padding: '10px',
          fontWeight: 'bold',
          width: '180px',
          textAlign: 'center'
        }
      },
    ];

    const rawEdges = [
      { id: 'start-market', source: 'start', target: 'market', animated: isLive && !analystsDone },
      { id: 'start-sentiment', source: 'start', target: 'sentiment', animated: isLive && !analystsDone },
      { id: 'start-news', source: 'start', target: 'news', animated: isLive && !analystsDone },
      { id: 'start-fundamentals', source: 'start', target: 'fundamentals', animated: isLive && !analystsDone },
      
      { id: 'market-sync', source: 'market', target: 'sync', animated: isLive && activeNode?.includes('market') },
      { id: 'sentiment-sync', source: 'sentiment', target: 'sync', animated: isLive && (activeNode?.includes('social') || activeNode?.includes('sentiment')) },
      { id: 'news-sync', source: 'news', target: 'sync', animated: isLive && activeNode?.includes('news') },
      { id: 'fundamentals-sync', source: 'fundamentals', target: 'sync', animated: isLive && activeNode?.includes('fundamental') },

      { id: 'sync-bull', source: 'sync', target: 'bull', animated: isLive && activeNode?.includes('sync') },
      { id: 'sync-bear', source: 'sync', target: 'bear', animated: isLive && activeNode?.includes('sync') },
      
      { id: 'bull-manager', source: 'bull', target: 'manager', animated: isLive && activeNode?.includes('bull') },
      { id: 'bear-manager', source: 'bear', target: 'manager', animated: isLive && activeNode?.includes('bear') },
      
      { id: 'manager-trader', source: 'manager', target: 'trader', animated: isLive && activeNode?.includes('manager') },
      { id: 'trader-pm', source: 'trader', target: 'pm', animated: isLive && activeNode?.includes('trader') },
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
