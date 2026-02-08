import { useState, useMemo } from 'react';
import { Layers, Loader2 } from 'lucide-react';
import type { FullPipelineData, FlowchartPhase, FlowchartNodeData } from '../../types/pipeline';
import { mapPipelineToFlowchart } from '../../types/pipeline';
import { FlowchartNode } from './FlowchartNode';
import { FlowchartConnector } from './FlowchartConnector';
import { FlowchartPhaseGroup } from './FlowchartPhaseGroup';
import { NodeDetailDrawer } from './NodeDetailDrawer';

interface PipelineFlowchartProps {
  pipelineData: FullPipelineData | null;
  isAnalyzing: boolean;
  isLoading: boolean;
}

// Group flowchart steps by phase
const PHASE_ORDER: FlowchartPhase[] = ['data_analysis', 'investment_debate', 'trading', 'risk_debate'];

function groupByPhase(nodes: FlowchartNodeData[]): Record<FlowchartPhase, FlowchartNodeData[]> {
  const groups: Record<FlowchartPhase, FlowchartNodeData[]> = {
    data_analysis: [],
    investment_debate: [],
    trading: [],
    risk_debate: [],
  };
  for (const node of nodes) {
    groups[node.phase].push(node);
  }
  return groups;
}

export function PipelineFlowchart({ pipelineData, isAnalyzing, isLoading }: PipelineFlowchartProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const nodes = useMemo(() => mapPipelineToFlowchart(pipelineData), [pipelineData]);
  const groups = useMemo(() => groupByPhase(nodes), [nodes]);

  const completedCount = nodes.filter(n => n.status === 'completed').length;
  const totalSteps = nodes.length;
  const progress = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  const selectedNode = selectedNodeId ? nodes.find(n => n.id === selectedNodeId) : null;

  const handleNodeClick = (nodeId: string) => {
    setSelectedNodeId(prev => prev === nodeId ? null : nodeId);
  };

  if (isLoading) {
    return (
      <div className="card p-12 flex flex-col items-center justify-center text-gray-400 dark:text-gray-500">
        <Loader2 className="w-8 h-8 animate-spin mb-3" />
        <p className="text-sm">Loading pipeline data...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with progress */}
      <div className="card p-3 sm:p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 sm:w-5 sm:h-5 text-nifty-600 dark:text-nifty-400" />
            <h2 className="font-semibold text-sm sm:text-base text-gray-900 dark:text-gray-100">
              Analysis Pipeline
            </h2>
            {isAnalyzing && (
              <span className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-[10px] sm:text-xs font-medium rounded-full">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                LIVE
              </span>
            )}
          </div>
          <span className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            {completedCount}/{totalSteps} steps
          </span>
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                progress === 100
                  ? 'bg-gradient-to-r from-green-500 to-emerald-500'
                  : 'bg-gradient-to-r from-nifty-500 to-blue-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className={`text-xs font-bold min-w-[36px] text-right ${
            progress === 100 ? 'text-green-600 dark:text-green-400' : 'text-gray-600 dark:text-gray-400'
          }`}>
            {progress}%
          </span>
        </div>
      </div>

      {/* Flowchart */}
      <div className="space-y-0">
        {PHASE_ORDER.map((phase, phaseIndex) => {
          const phaseNodes = groups[phase];
          const phaseCompleted = phaseNodes.filter(n => n.status === 'completed').length;
          const phaseActive = phaseNodes.some(n => n.status === 'running');

          return (
            <div key={phase}>
              {/* Phase connector (between phases) */}
              {phaseIndex > 0 && (
                <FlowchartConnector
                  completed={groups[PHASE_ORDER[phaseIndex - 1]].every(n => n.status === 'completed')}
                  isPhase
                />
              )}

              <FlowchartPhaseGroup
                phase={phase}
                totalSteps={phaseNodes.length}
                completedSteps={phaseCompleted}
                isActive={phaseActive}
              >
                {phaseNodes.map((node, nodeIndex) => (
                  <div key={node.id}>
                    {/* Node connector (within phase) */}
                    {nodeIndex > 0 && (
                      <FlowchartConnector
                        completed={phaseNodes[nodeIndex - 1].status === 'completed'}
                      />
                    )}
                    <FlowchartNode
                      node={node}
                      isSelected={selectedNodeId === node.id}
                      onClick={() => handleNodeClick(node.id)}
                    />
                  </div>
                ))}
              </FlowchartPhaseGroup>
            </div>
          );
        })}
      </div>

      {/* Detail drawer */}
      {selectedNode && (
        <NodeDetailDrawer
          node={selectedNode}
          pipelineData={pipelineData}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </div>
  );
}
