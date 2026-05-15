import React, { useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, Handle, Position } from 'reactflow';
import 'reactflow/dist/style.css';

const AgentNode = ({ data }) => {
  const isSelected = data.isSelected;
  const isActive = data.isActive;
  const isComplete = data.isComplete;
  const [showTooltip, setShowTooltip] = useState(false);

  const getBgColor = () => {
    if (isSelected) return '#1d4ed8';
    if (isActive) return '#eab308';
    if (isComplete) return '#10b981';
    return '#1e293b';
  };

  const getBorderColor = () => {
    if (isSelected) return '#93c5fd';
    if (isActive) return '#fde047';
    if (isComplete) return '#34d399';
    return '#475569';
  };

  return (
    <div
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      style={{
        padding: '12px',
        borderRadius: '12px',
        background: getBgColor(),
        color: 'white',
        border: `2px solid ${getBorderColor()}`,
        width: '190px',
        fontSize: '12px',
        boxShadow: isSelected
          ? '0 0 24px rgba(59, 130, 246, 0.45)'
          : isActive
            ? '0 0 20px rgba(234, 179, 8, 0.35)'
            : isComplete
              ? '0 0 10px rgba(16, 185, 129, 0.2)'
              : 'none',
        transition: 'all 0.3s ease',
        cursor: 'pointer',
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#94a3b8' }} />
      <div style={{ fontWeight: 700, marginBottom: '6px' }}>{data.label}</div>
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '10px',
          opacity: 0.95,
          fontWeight: 700,
          padding: '4px 8px',
          borderRadius: '999px',
          background: 'rgba(15, 23, 42, 0.28)',
          marginBottom: '8px',
        }}
      >
        <span>●</span>
        {data.status || 'Waiting'}
      </div>
      <div style={{ fontSize: '10px', lineHeight: 1.4, opacity: 0.9 }}>{data.shortDescription}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#94a3b8' }} />

      {showTooltip && (
        <div
          style={{
            position: 'absolute',
            bottom: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            marginBottom: '10px',
            padding: '10px',
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '8px',
            width: '220px',
            zIndex: 1000,
            pointerEvents: 'none',
            boxShadow: '0 8px 24px rgba(15, 23, 42, 0.45)',
          }}
        >
          <div style={{ fontWeight: 700, fontSize: '11px', marginBottom: '6px', color: '#60a5fa', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Purpose
          </div>
          <div style={{ fontSize: '11px', lineHeight: 1.5 }}>{data.description}</div>
        </div>
      )}
    </div>
  );
};

const nodeTypes = {
  agent: AgentNode,
};

const FlowGraph = ({ runData, activeStatus, onNodeClick, selectedAgentId }) => {
  const { nodes, edges } = useMemo(() => {
    const isLive = !!activeStatus;
    const isCompleted = activeStatus?.status === 'completed';
    const activeNode = (activeStatus?.active_node || '').toLowerCase();
    const completedNodes = (activeStatus?.completed_nodes || []).map((node) => node.toLowerCase());
    const isAnalystBootstrapping = activeNode.includes('launching analyst branches');

    const descriptions = {
      market: 'Analyzes price action, technical indicators, and volume patterns to identify trends.',
      sentiment: 'Monitors market mood by analyzing news sentiment and social signals.',
      news: 'Synthesizes macro headlines and tracks insider transactions.',
      fundamentals: 'Evaluates financial health using statements, ratios, and business quality.',
      bull: "Constructs the strongest possible 'buy' case by identifying positive catalysts.",
      bear: "Challenges the idea by identifying risks and potential 'sell' catalysts.",
      manager: 'Synthesizes competing researcher views into one balanced investment plan.',
      trader: 'Calculates entry, exit, and stop-loss levels for execution.',
      pm: 'Makes the final capital allocation decision and issues the official rating.',
    };

    const shortDescriptions = {
      market: 'Trend and technical view',
      sentiment: 'Market mood and signals',
      news: 'News and insider context',
      fundamentals: 'Financial quality check',
      bull: 'Upside case',
      bear: 'Risk case',
      manager: 'Thesis synthesis',
      trader: 'Execution levels',
      pm: 'Final decision',
    };

    const order = ['market', 'sentiment', 'news', 'fundamentals', 'synchronizer', 'bull', 'bear', 'manager', 'trader', 'pm', 'end'];

    const getIsPast = (targetNode) => {
      if (isCompleted) return true;
      const targetIndex = order.indexOf(targetNode);
      if (targetIndex === -1) return false;

      return order.slice(targetIndex + 1).some(
        (name) => activeNode.includes(name) || completedNodes.some((completedNode) => completedNode.includes(name))
      );
    };

    const areAnalystsDone = isCompleted || getIsPast('fundamentals') || completedNodes.some((node) => node.includes('synchronizer'));

    const isDone = (id) => {
      if (isCompleted) return true;

      if (['market', 'sentiment', 'news', 'fundamentals'].includes(id)) {
        return completedNodes.some((node) => node.includes(id)) || areAnalystsDone;
      }

      return getIsPast(id) || completedNodes.some((node) => node.includes(id));
    };

    const isCurrentlyActive = (targetNode) => {
      if (isCompleted || isDone(targetNode)) return false;
      if (isAnalystBootstrapping && ['market', 'sentiment', 'social', 'news', 'fundamentals'].includes(targetNode)) {
        return true;
      }
      return activeNode.includes(targetNode);
    };

    const getStatus = (id, doneLabel = 'Complete') => {
      if (isCurrentlyActive(id)) return 'Active';
      if (isDone(id)) return doneLabel;
      return 'Pending';
    };

    const createAgentData = (id, label, description, status, isComplete, isActive) => ({
      id,
      label,
      description,
      shortDescription: shortDescriptions[id],
      status,
      isComplete,
      isActive,
      isSelected: selectedAgentId === id,
    });

    const rawNodes = [
      {
        id: 'start',
        type: 'input',
        data: { label: 'Start' },
        position: { x: 450, y: 0 },
        style: {
          background: '#111c31',
          color: 'white',
          border: '1px solid #334155',
          borderRadius: '10px',
          padding: '10px 14px',
          fontWeight: 700,
          width: '180px',
          textAlign: 'center',
        },
      },
      {
        id: 'market',
        type: 'agent',
        data: createAgentData('market', 'Market Analyst', descriptions.market, getStatus('market'), isDone('market'), isCurrentlyActive('market')),
        position: { x: 0, y: 150 },
      },
      {
        id: 'sentiment',
        type: 'agent',
        data: createAgentData(
          'sentiment',
          'Sentiment Analyst',
          descriptions.sentiment,
          isCurrentlyActive('sentiment') || isCurrentlyActive('social') ? 'Active' : isDone('sentiment') || isDone('social') ? 'Complete' : 'Pending',
          isDone('sentiment') || isDone('social'),
          isCurrentlyActive('sentiment') || isCurrentlyActive('social')
        ),
        position: { x: 300, y: 150 },
      },
      {
        id: 'news',
        type: 'agent',
        data: createAgentData('news', 'News Analyst', descriptions.news, getStatus('news'), isDone('news'), isCurrentlyActive('news')),
        position: { x: 600, y: 150 },
      },
      {
        id: 'fundamentals',
        type: 'agent',
        data: createAgentData(
          'fundamentals',
          'Fundamentals Analyst',
          descriptions.fundamentals,
          getStatus('fundamentals'),
          isDone('fundamentals'),
          isCurrentlyActive('fundamentals')
        ),
        position: { x: 900, y: 150 },
      },
      {
        id: 'sync',
        data: {
          label: 'Analyst Synchronizer',
        },
        position: { x: 450, y: 300 },
        style: {
          background: selectedAgentId === 'sync' ? '#1d4ed8' : isCurrentlyActive('synchronizer') ? '#eab308' : isDone('synchronizer') ? '#10b981' : '#1e293b',
          color: 'white',
          border: `2px solid ${selectedAgentId === 'sync' ? '#93c5fd' : isDone('synchronizer') ? '#34d399' : '#475569'}`,
          borderRadius: '12px',
          padding: '12px',
          width: '190px',
          textAlign: 'center',
          fontWeight: 700,
        },
      },
      {
        id: 'bull',
        type: 'agent',
        data: createAgentData('bull', 'Bull Researcher', descriptions.bull, getStatus('bull'), isDone('bull'), isCurrentlyActive('bull')),
        position: { x: 300, y: 450 },
      },
      {
        id: 'bear',
        type: 'agent',
        data: createAgentData('bear', 'Bear Researcher', descriptions.bear, getStatus('bear'), isDone('bear'), isCurrentlyActive('bear')),
        position: { x: 600, y: 450 },
      },
      {
        id: 'manager',
        type: 'agent',
        data: createAgentData(
          'manager',
          'Research Manager',
          descriptions.manager,
          isCurrentlyActive('manager') ? 'Synthesizing' : isDone('manager') ? 'Complete' : 'Waiting',
          isDone('manager'),
          isCurrentlyActive('manager')
        ),
        position: { x: 450, y: 600 },
      },
      {
        id: 'trader',
        type: 'agent',
        data: createAgentData(
          'trader',
          'Trader',
          descriptions.trader,
          isCurrentlyActive('trader') ? 'Calculating' : isDone('trader') ? 'Proposed' : 'Waiting',
          isDone('trader'),
          isCurrentlyActive('trader')
        ),
        position: { x: 450, y: 750 },
      },
      {
        id: 'pm',
        type: 'agent',
        data: createAgentData(
          'pm',
          'Portfolio Manager',
          descriptions.pm,
          isCurrentlyActive('risk') || isCurrentlyActive('portfolio') ? 'Reviewing' : isDone('pm') ? 'Final decision' : 'Waiting',
          isDone('pm'),
          isCurrentlyActive('risk') || isCurrentlyActive('portfolio')
        ),
        position: { x: 450, y: 900 },
      },
      {
        id: 'end',
        type: 'output',
        data: { label: 'Decision Reached' },
        position: { x: 450, y: 1050 },
        style: {
          background: isCompleted ? '#10b981' : '#111c31',
          color: 'white',
          border: `2px solid ${isCompleted ? '#34d399' : '#475569'}`,
          borderRadius: '12px',
          padding: '12px',
          fontWeight: 700,
          width: '190px',
          textAlign: 'center',
        },
      },
    ];

    const rawEdges = [
      { id: 'start-market', source: 'start', target: 'market', animated: isLive && !isDone('market') },
      { id: 'start-sentiment', source: 'start', target: 'sentiment', animated: isLive && !isDone('sentiment') },
      { id: 'start-news', source: 'start', target: 'news', animated: isLive && !isDone('news') },
      { id: 'start-fundamentals', source: 'start', target: 'fundamentals', animated: isLive && !isDone('fundamentals') },
      { id: 'market-sync', source: 'market', target: 'sync', animated: isLive && isCurrentlyActive('market') },
      { id: 'sentiment-sync', source: 'sentiment', target: 'sync', animated: isLive && (isCurrentlyActive('social') || isCurrentlyActive('sentiment')) },
      { id: 'news-sync', source: 'news', target: 'sync', animated: isLive && isCurrentlyActive('news') },
      { id: 'fundamentals-sync', source: 'fundamentals', target: 'sync', animated: isLive && isCurrentlyActive('fundamentals') },
      { id: 'sync-bull', source: 'sync', target: 'bull', animated: isLive && isCurrentlyActive('synchronizer') },
      { id: 'sync-bear', source: 'sync', target: 'bear', animated: isLive && isCurrentlyActive('synchronizer') },
      { id: 'bull-manager', source: 'bull', target: 'manager', animated: isLive && isCurrentlyActive('bull') },
      { id: 'bear-manager', source: 'bear', target: 'manager', animated: isLive && isCurrentlyActive('bear') },
      { id: 'manager-trader', source: 'manager', target: 'trader', animated: isLive && isCurrentlyActive('manager') },
      { id: 'trader-pm', source: 'trader', target: 'pm', animated: isLive && isCurrentlyActive('trader') },
      { id: 'pm-end', source: 'pm', target: 'end' },
    ].map((edge) => ({
      ...edge,
      style: { stroke: '#475569', strokeWidth: 1.6 },
    }));

    return { nodes: rawNodes, edges: rawEdges };
  }, [activeStatus, selectedAgentId]);

  const handleNodeClick = (_, node) => {
    if (!onNodeClick) return;

    if (node.id === 'sync') {
      onNodeClick({
        id: 'sync',
        label: 'Analyst Synchronizer',
        status: activeStatus?.active_node?.toLowerCase().includes('synchronizer') ? 'Active' : 'Waiting',
        description: 'Combines the parallel analyst outputs before the bullish and bearish researchers take over.',
      });
      return;
    }

    onNodeClick(node.data);
  };

  return (
    <div style={{ width: '100%', height: '640px', background: '#0f172a', position: 'relative', borderRadius: '14px', overflow: 'hidden' }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={handleNodeClick} fitView fitViewOptions={{ padding: 0.12 }}>
        <Background color="#334155" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
};

export default FlowGraph;
