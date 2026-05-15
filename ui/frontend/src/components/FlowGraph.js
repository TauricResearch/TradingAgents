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
  const isComplete = data.isComplete;
  
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
    // Determine data source: historical run log OR live accumulated updates
    const isLive = !!activeStatus;
    const isCompleted = activeStatus?.status === 'completed';
    const activeNode = (activeStatus?.active_node || '').toLowerCase();
    const completedNodes = activeStatus?.completed_nodes || [];
    
    // Merge live updates into currentData if live, otherwise use runData
    const currentData = isLive ? (activeStatus.updates || {}) : (runData || {});

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

    // Robust 'reached' logic to prevent flickering and hallucinations
    // A node is past if any node later in the topological order is active OR completed.
    const order = [
        'market', 'sentiment', 'news', 'fundamentals', 
        'sync', 'bull', 'bear', 'manager', 'trader', 'pm', 'end'
    ];

    const getIsPast = (targetNode) => {
        if (isCompleted) return true;
        
        // Find index of target in topological order
        const targetIdx = order.indexOf(targetNode);
        if (targetIdx === -1) return false;

        // Check if any node AFTER this target is active or in completedNodes
        return order.slice(targetIdx + 1).some(name => 
            activeNode.includes(name) || 
            completedNodes.some(cn => cn.toLowerCase().includes(name))
        );
    };

    const isCurrent = (targetNode) => {
        if (isCompleted) return false;
        return activeNode.includes(targetNode);
    };

    // Status helpers
    const getStatus = (id, label, doneLabel = 'Complete') => {
        if (isCurrent(id)) return 'Analyzing...';
        if (getIsPast(id) || completedNodes.some(cn => cn.toLowerCase().includes(id))) return doneLabel;
        return 'Pending';
    };

    const isDone = (id) => isCompleted || getIsPast(id) || completedNodes.some(cn => cn.toLowerCase().includes(id));

    const rawNodes = [
      { id: 'start', type: 'input', data: { label: 'Start' }, position: { x: 450, y: 0 } },
      { 
        id: 'market', 
        type: 'agent', 
        data: { 
            label: 'Market Analyst', 
            description: descriptions.market,
            status: getStatus('market', 'Market Analyst'),
            isComplete: isDone('market'),
            isActive: isCurrent('market')
        }, 
        position: { x: 0, y: 150 } 
      },
      { 
        id: 'sentiment', 
        type: 'agent', 
        data: { 
            label: 'Sentiment Analyst', 
            description: descriptions.sentiment,
            status: getStatus('sentiment', 'Sentiment Analyst') || getStatus('social', 'Sentiment Analyst'),
            isComplete: isDone('sentiment') || isDone('social'),
            isActive: isCurrent('sentiment') || isCurrent('social')
        }, 
        position: { x: 300, y: 150 } 
      },
      { 
        id: 'news', 
        type: 'agent', 
        data: { 
            label: 'News Analyst', 
            description: descriptions.news,
            status: getStatus('news', 'News Analyst'),
            isComplete: isDone('news'),
            isActive: isCurrent('news')
        }, 
        position: { x: 600, y: 150 } 
      },
      { 
        id: 'fundamentals', 
        type: 'agent', 
        data: { 
            label: 'Fundamentals Analyst', 
            description: descriptions.fundamentals,
            status: getStatus('fundamental', 'Fundamentals Analyst'),
            isComplete: isDone('fundamental'),
            isActive: isCurrent('fundamental')
        }, 
        position: { x: 900, y: 150 } 
      },
      {
        id: 'sync',
        data: { label: 'Analyst Synchronizer' },
        position: { x: 450, y: 300 },
        style: {
          background: isCurrent('synchronizer') ? '#eab308' : (isDone('sync') ? '#10b981' : '#1e293b'),
          color: 'white',
          border: `2px solid ${isDone('sync') ? '#34d399' : '#475569'}`,
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
            status: getStatus('bull', 'Bull Researcher'),
            isComplete: isDone('bull'),
            isActive: isCurrent('bull')
        }, 
        position: { x: 300, y: 450 } 
      },
      { 
        id: 'bear', 
        type: 'agent', 
        data: { 
            label: 'Bear Researcher', 
            description: descriptions.bear,
            status: getStatus('bear', 'Bear Researcher'),
            isComplete: isDone('bear'),
            isActive: isCurrent('bear')
        }, 
        position: { x: 600, y: 450 } 
      },
      { 
        id: 'manager', 
        type: 'agent', 
        data: { 
            label: 'Research Manager', 
            description: descriptions.manager,
            status: isCurrent('manager') ? 'Synthesizing...' : (isDone('manager') ? 'Synthesized' : 'Waiting'),
            isComplete: isDone('manager'),
            isActive: isCurrent('manager')
        }, 
        position: { x: 450, y: 600 } 
      },
      { 
        id: 'trader', 
        type: 'agent', 
        data: { 
            label: 'Trader', 
            description: descriptions.trader,
            status: isCurrent('trader') ? 'Calculating...' : (isDone('trader') ? 'Proposed' : 'Waiting'),
            isComplete: isDone('trader'),
            isActive: isCurrent('trader')
        }, 
        position: { x: 450, y: 750 } 
      },
      { 
        id: 'pm', 
        type: 'agent', 
        data: { 
            label: 'Portfolio Manager', 
            description: descriptions.pm,
            status: (isCurrent('risk') || isCurrent('portfolio')) ? 'Reviewing...' : (isDone('pm') ? 'Final Decision' : 'Waiting'),
            isComplete: isDone('pm'),
            isActive: isCurrent('risk') || isCurrent('portfolio')
        }, 
        position: { x: 450, y: 900 } 
      },
      { 
        id: 'end', 
        type: 'output', 
        data: { label: 'Decision Reached' }, 
        position: { x: 450, y: 1050 },
        style: {
          background: isCompleted ? '#10b981' : '#1e293b',
          color: 'white',
          border: `2px solid ${isCompleted ? '#34d399' : '#475569'}`,
          borderRadius: '8px',
          padding: '10px',
          fontWeight: 'bold',
          width: '180px',
          textAlign: 'center'
        }
      },
    ];

    const rawEdges = [
      { id: 'start-market', source: 'start', target: 'market', animated: isLive && !isDone('market') },
      { id: 'start-sentiment', source: 'start', target: 'sentiment', animated: isLive && !isDone('sentiment') },
      { id: 'start-news', source: 'start', target: 'news', animated: isLive && !isDone('news') },
      { id: 'start-fundamentals', source: 'start', target: 'fundamentals', animated: isLive && !isDone('fundamentals') },
      
      { id: 'market-sync', source: 'market', target: 'sync', animated: isLive && isCurrent('market') },
      { id: 'sentiment-sync', source: 'sentiment', target: 'sync', animated: isLive && (isCurrent('social') || isCurrent('sentiment')) },
      { id: 'news-sync', source: 'news', target: 'sync', animated: isLive && isCurrent('news') },
      { id: 'fundamentals-sync', source: 'fundamentals', target: 'sync', animated: isLive && isCurrent('fundamental') },

      { id: 'sync-bull', source: 'sync', target: 'bull', animated: isLive && isCurrent('synchronizer') },
      { id: 'sync-bear', source: 'sync', target: 'bear', animated: isLive && isCurrent('synchronizer') },
      
      { id: 'bull-manager', source: 'bull', target: 'manager', animated: isLive && isCurrent('bull') },
      { id: 'bear-manager', source: 'bear', target: 'manager', animated: isLive && isCurrent('bear') },
      
      { id: 'manager-trader', source: 'manager', target: 'trader', animated: isLive && isCurrent('manager') },
      { id: 'trader-pm', source: 'trader', target: 'pm', animated: isLive && isCurrent('trader') },
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
