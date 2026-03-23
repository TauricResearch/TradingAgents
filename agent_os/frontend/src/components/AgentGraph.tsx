import React, { useEffect, useRef, useCallback } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Node, 
  Edge,
  Handle,
  Position,
  NodeProps,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box, Text, Flex, Icon, Badge } from '@chakra-ui/react';
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
      cursor="pointer"
      _hover={{ borderColor: 'cyan.300', boxShadow: '0 0 20px rgba(79,209,197,0.3)' }}
    >
      <Handle type="target" position={Position.Top} />
      
      <Flex direction="column" gap={2}>
        <Flex align="center" gap={2}>
          <Icon as={getIcon(data.agent)} color={getStatusColor(data.status)} boxSize={4} />
          <Text fontSize="sm" fontWeight="bold" color="white">{data.agent}</Text>
          {data.status === 'completed' && (
            <Badge colorScheme="green" fontSize="2xs" ml="auto">Done</Badge>
          )}
        </Flex>
        
        <Box height="1px" bg="whiteAlpha.200" width="100%" />
        
        <Flex justify="space-between" align="center">
          <Flex align="center" gap={1}>
            <Icon as={Clock} boxSize={3} color="whiteAlpha.500" />
            <Text fontSize="2xs" color="whiteAlpha.600">{data.metrics?.latency_ms || 0}ms</Text>
          </Flex>
          {data.metrics?.model && data.metrics.model !== 'unknown' && (
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
  onNodeClick?: (nodeId: string) => void;
}

export const AgentGraph: React.FC<AgentGraphProps> = ({ events, onNodeClick }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  // Track which node_ids we have already added so we never duplicate
  const seenNodeIds = useRef(new Set<string>());
  const seenEdgeIds = useRef(new Set<string>());
  // Track how many unique nodes exist for vertical layout
  const nodeCount = useRef(0);
  // Track the last processed event index to only process new events
  const processedCount = useRef(0);

  useEffect(() => {
    // Only process newly arrived events
    const newEvents = events.slice(processedCount.current);
    if (newEvents.length === 0) return;
    processedCount.current = events.length;

    const addedNodes: Node[] = [];
    const addedEdges: Edge[] = [];
    const updatedNodeData: Map<string, Partial<Node['data']>> = new Map();

    for (const evt of newEvents) {
      if (!evt.node_id || evt.node_id === '__system__') continue;

      // Determine if this event means the node is completed
      const isCompleted = evt.type === 'result' || evt.type === 'tool_result';

      if (!seenNodeIds.current.has(evt.node_id)) {
        // New node — create it
        seenNodeIds.current.add(evt.node_id);
        nodeCount.current += 1;

        addedNodes.push({
          id: evt.node_id,
          type: 'agentNode',
          position: { x: 250, y: nodeCount.current * 150 + 50 },
          data: {
            agent: evt.agent,
            status: isCompleted ? 'completed' : 'running',
            metrics: evt.metrics,
          },
        });

        // Add edge from parent (if applicable)
        if (evt.parent_node_id && evt.parent_node_id !== 'start') {
          const edgeId = `e-${evt.parent_node_id}-${evt.node_id}`;
          if (!seenEdgeIds.current.has(edgeId)) {
            seenEdgeIds.current.add(edgeId);
            addedEdges.push({
              id: edgeId,
              source: evt.parent_node_id,
              target: evt.node_id,
              animated: true,
              style: { stroke: '#4fd1c5' },
            });
          }
        }
      } else {
        // Existing node — queue a status/metrics update
        // Never revert a completed node back to running
        const prev = updatedNodeData.get(evt.node_id);
        const currentlyCompleted = prev?.status === 'completed';
        updatedNodeData.set(evt.node_id, {
          status: currentlyCompleted || isCompleted ? 'completed' : 'running',
          metrics: evt.metrics,
        });
      }
    }

    // Batch state updates
    if (addedNodes.length > 0) {
      setNodes((prev) => [...prev, ...addedNodes]);
    }
    if (addedEdges.length > 0) {
      setEdges((prev) => [...prev, ...addedEdges]);
    }
    if (updatedNodeData.size > 0) {
      setNodes((prev) =>
        prev.map((n) => {
          const patch = updatedNodeData.get(n.id);
          if (!patch) return n;
          // Never revert a completed node back to running
          const finalStatus = n.data.status === 'completed' ? 'completed' : patch.status;
          return {
            ...n,
            data: { ...n.data, ...patch, status: finalStatus, metrics: patch.metrics ?? n.data.metrics },
          };
        }),
      );
    }
  }, [events, setNodes, setEdges]);

  // Reset tracked state when the events array is cleared (new run)
  useEffect(() => {
    if (events.length === 0) {
      seenNodeIds.current.clear();
      seenEdgeIds.current.clear();
      nodeCount.current = 0;
      processedCount.current = 0;
      setNodes([]);
      setEdges([]);
    }
  }, [events.length, setNodes, setEdges]);

  const handleNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    onNodeClick?.(node.id);
  }, [onNodeClick]);

  return (
    <Box height="100%" width="100%" bg="slate.950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background color="#333" gap={16} />
        <Controls />
      </ReactFlow>
    </Box>
  );
};
