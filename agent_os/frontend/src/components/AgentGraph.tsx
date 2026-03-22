import React, { useMemo, useEffect } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Node, 
  Edge,
  Handle,
  Position,
  NodeProps,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box, Text, Flex, Icon, Tooltip, Badge } from '@chakra-ui/react';
import { Cpu, Settings, Database, TrendingUp, Clock } from 'lucide-react';
import { AgentEvent } from '../hooks/useAgentStream';

// --- Custom Agent Node Component ---
const AgentNode = ({ data }: NodeProps) => {
  const getIcon = (agent: string) => {
    switch (agent.toUpperCase()) {
      case 'ANALYST': return Cpu;
      case 'RESEARCHER': return Database;
      case 'TRADER': return TrendingUp;
      default: return Settings;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'cyan.400';
      case 'completed': return 'green.400';
      case 'error': return 'red.400';
      default: return 'whiteAlpha.500';
    }
  };

  return (
    <Box 
      bg="slate.900" 
      border="1px solid" 
      borderColor={getStatusColor(data.status)} 
      p={3} 
      borderRadius="lg" 
      minW="180px"
      boxShadow="0 0 15px rgba(0,0,0,0.5)"
    >
      <Handle type="target" position={Position.Top} />
      
      <Flex direction="column" gap={2}>
        <Flex align="center" gap={2}>
          <Icon as={getIcon(data.agent)} color={getStatusColor(data.status)} boxSize={4} />
          <Text fontSize="sm" fontWeight="bold" color="white">{data.agent}</Text>
        </Flex>
        
        <Box height="1px" bg="whiteAlpha.200" width="100%" />
        
        <Flex justify="space-between" align="center">
          <Flex align="center" gap={1}>
            <Icon as={Clock} boxSize={3} color="whiteAlpha.500" />
            <Text fontSize="2xs" color="whiteAlpha.600">{data.metrics?.latency_ms || 0}ms</Text>
          </Flex>
          {data.metrics?.model && (
            <Badge variant="outline" fontSize="2xs" colorScheme="blue">{data.metrics.model}</Badge>
          )}
        </Flex>
        
        {data.status === 'running' && (
           <Box width="100%" height="2px" bg="cyan.400" borderRadius="full" overflow="hidden">
              <Box 
                as="div" 
                width="40%" 
                height="100%" 
                bg="white" 
                sx={{
                  animation: "shimmer 2s infinite linear",
                  "@keyframes shimmer": {
                    "0%": { transform: "translateX(-100%)" },
                    "100%": { transform: "translateX(300%)" }
                  }
                }}
              />
           </Box>
        )}
      </Flex>

      <Handle type="source" position={Position.Bottom} />
    </Box>
  );
};

const nodeTypes = {
  agentNode: AgentNode,
};

interface AgentGraphProps {
  events: AgentEvent[];
}

export const AgentGraph: React.FC<AgentGraphProps> = ({ events }) => {
  const { nodes, edges } = useMemo(() => {
    const graphNodes: Node[] = [];
    const graphEdges: Edge[] = [];
    const seenNodes = new Set<string>();

    events.forEach((evt) => {
      if (!evt.node_id) return;

      if (!seenNodes.has(evt.node_id)) {
        graphNodes.push({
          id: evt.node_id,
          type: 'agentNode',
          position: { x: 250, y: graphNodes.length * 150 + 50 }, // Simple vertical layout
          data: { 
            agent: evt.agent, 
            status: evt.type === 'result' ? 'completed' : 'running',
            metrics: evt.metrics 
          },
        });
        seenNodes.add(evt.node_id);

        if (evt.parent_node_id && evt.parent_node_id !== 'start') {
          graphEdges.push({
            id: `e-${evt.parent_node_id}-${evt.node_id}`,
            source: evt.parent_node_id,
            target: evt.node_id,
            animated: true,
            style: { stroke: '#4fd1c5' },
          });
        }
      } else {
        // Update existing node status and metrics
        const idx = graphNodes.findIndex(n => n.id === evt.node_id);
        if (idx !== -1) {
          graphNodes[idx].data = {
            ...graphNodes[idx].data,
            status: evt.type === 'result' ? 'completed' : 'running',
            metrics: evt.metrics || graphNodes[idx].data.metrics
          };
        }
      }
    });

    return { nodes: graphNodes, edges: graphEdges };
  }, [events]);

  return (
    <Box height="100%" width="100%" bg="slate.950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background color="#333" gap={16} />
        <Controls />
      </ReactFlow>
    </Box>
  );
};
