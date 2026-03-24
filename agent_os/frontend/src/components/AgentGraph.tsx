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
import { Box, Text, Flex, Icon, Badge, IconButton, Tooltip } from '@chakra-ui/react';
import { Cpu, Settings, Database, TrendingUp, Clock, RefreshCw } from 'lucide-react';
import { AgentEvent } from '../hooks/useAgentStream';

// ─── Layout constants ─────────────────────────────────────────────────────────
const COL_WIDTH      = 230;   // horizontal space per ticker column / scan slot
const ROW_HEIGHT     = 148;   // vertical space per agent row within a column
const SCAN_TOP_Y     = 40;    // y offset for the first scan row
const SCAN_ROW_H     = 148;   // vertical gap between scan rows
// Phase-1 scanners align with the first 3 ticker columns (x = 0, COL_WIDTH, COL_WIDTH*2)
const SCAN_CENTER_X  = COL_WIDTH;  // x for phase-2/3 scan nodes (centre of 3)
const TICKER_GAP     = 80;    // vertical gap between scan phase and ticker headers
const TICKER_HDR_H   = 108;   // height reserved for the ticker header card

// ─── Node classification ──────────────────────────────────────────────────────
const SCAN_PHASE1 = ['geopolitical_scanner', 'market_movers_scanner', 'sector_scanner'];
const SCAN_PHASE2 = new Set(['industry_deep_dive']);
const SCAN_PHASE3 = new Set(['macro_synthesis']);
const SCAN_ALL    = new Set([...SCAN_PHASE1, ...SCAN_PHASE2, ...SCAN_PHASE3]);

type NodeKind = 'scan' | 'ticker' | 'portfolio' | 'skip';

function classifyNode(nodeId: string, identifier: string): NodeKind {
  if (nodeId.startsWith('tool_'))                                        return 'skip';
  if (identifier === 'MARKET' || SCAN_ALL.has(nodeId))                  return 'scan';
  if (identifier === 'PORTFOLIO' || nodeId === 'portfolio_manager' ||
      nodeId === 'make_pm_decision')                                     return 'portfolio';
  if (identifier)                                                        return 'ticker';
  return 'skip';
}

// ─── Colour helpers ───────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  running:   '#4fd1c5',
  completed: '#68d391',
  error:     '#fc8181',
};
const DEFAULT_COLOR = 'rgba(255,255,255,0.25)';

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? DEFAULT_COLOR;
}

const ID_PALETTE = [
  '#63b3ed', '#9f7aea', '#f6ad55', '#4fd1c5',
  '#f687b3', '#f6e05e', '#68d391', '#fc8181',
];
function identifierColor(id: string): string {
  if (!id || id === 'MARKET')    return '#4fd1c5';
  if (id === 'PORTFOLIO')        return '#9f7aea';
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xffff;
  return ID_PALETTE[h % ID_PALETTE.length];
}

function toLabel(nodeId: string): string {
  return nodeId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Agent Node ───────────────────────────────────────────────────────────────
const AgentNode = ({ data }: NodeProps) => {
  const getIcon = (agent = '') => {
    const a = agent.toUpperCase();
    if (a.includes('ANALYST') || a.includes('SCANNER')) return Cpu;
    if (a.includes('RESEARCHER') || a.includes('MANAGER') || a.includes('SYNTHESIS') || a.includes('DIVE')) return Database;
    if (a.includes('TRADER') || a.includes('RISK') || a.includes('JUDGE')) return TrendingUp;
    return Settings;
  };

  const sc       = statusColor(data.status);
  const canRerun = data.status === 'completed' || data.status === 'error';
  const totalTok = (data.metrics?.tokens_in ?? 0) + (data.metrics?.tokens_out ?? 0);

  return (
    <Box
      bg="#0f172a"
      border="1px solid"
      borderColor={sc}
      p={3}
      borderRadius="lg"
      w="200px"
      boxShadow={`0 0 12px ${sc}35`}
      cursor="pointer"
      _hover={{ borderColor: '#67e8f9', boxShadow: '0 0 18px #67e8f940' }}
    >
      <Handle type="target" position={Position.Top} style={{ borderColor: sc }} />

      <Flex direction="column" gap={1.5}>
        {/* Header row */}
        <Flex align="center" gap={1.5}>
          <Icon as={getIcon(data.agent)} color={sc} boxSize={3.5} />
          <Text fontSize="xs" fontWeight="bold" color="white" flex={1} noOfLines={1}>
            {data.label}
          </Text>
          {data.status === 'completed' && <Badge colorScheme="green"  fontSize="2xs">✓</Badge>}
          {data.status === 'error'     && <Badge colorScheme="red"    fontSize="2xs">✗</Badge>}
        </Flex>

        <Box h="1px" bg="rgba(255,255,255,0.08)" />

        {/* Metrics row */}
        <Flex justify="space-between" align="center">
          <Flex align="center" gap={1}>
            <Icon as={Clock} boxSize={2.5} color="rgba(255,255,255,0.35)" />
            <Text fontSize="2xs" color="rgba(255,255,255,0.45)">
              {data.metrics?.latency_ms ? `${data.metrics.latency_ms}ms` : '—'}
            </Text>
          </Flex>
          {totalTok > 0 && (
            <Text fontSize="2xs" color="rgba(255,255,255,0.35)">
              {totalTok.toLocaleString()} tok
            </Text>
          )}
        </Flex>

        {data.metrics?.model && data.metrics.model !== 'unknown' && (
          <Tooltip label={data.metrics.model} placement="top" hasArrow openDelay={300}>
            <Badge
              variant="outline" fontSize="2xs" colorScheme="blue"
              display="block" maxW="100%"
              overflow="hidden" textOverflow="ellipsis" whiteSpace="nowrap"
            >
              {data.metrics.model}
            </Badge>
          </Tooltip>
        )}

        {/* Running shimmer */}
        {data.status === 'running' && (
          <Box w="100%" h="2px" bg="rgba(79,209,197,0.25)" borderRadius="full" overflow="hidden">
            <Box
              as="div" w="40%" h="100%" bg="#4fd1c5"
              sx={{
                animation: 'shimmer 1.5s infinite linear',
                '@keyframes shimmer': {
                  '0%':   { transform: 'translateX(-100%)' },
                  '100%': { transform: 'translateX(300%)'  },
                },
              }}
            />
          </Box>
        )}

        {/* Re-run */}
        {canRerun && data.onRerun && (
          <Tooltip label="Re-run" placement="bottom" hasArrow>
            <IconButton
              aria-label="Re-run"
              icon={<RefreshCw size={11} />}
              size="xs" variant="ghost" colorScheme="cyan" alignSelf="flex-end"
              onClick={(e) => { e.stopPropagation(); data.onRerun(); }}
            />
          </Tooltip>
        )}
      </Flex>

      <Handle type="source" position={Position.Bottom} style={{ borderColor: sc }} />
    </Box>
  );
};

// ─── Ticker Header Node ───────────────────────────────────────────────────────
const TickerHeaderNode = ({ data }: NodeProps) => {
  const color = identifierColor(data.ticker);
  const sc    = statusColor(data.status ?? 'running');
  const done  = data.completedCount ?? 0;
  const total = data.agentCount ?? 0;

  return (
    <Box
      bg="#1e293b"
      border="2px solid"
      borderColor={color}
      p={3}
      borderRadius="xl"
      w="200px"
      boxShadow={`0 0 22px ${color}28`}
      cursor="pointer"
      _hover={{ boxShadow: `0 0 30px ${color}45` }}
    >
      <Handle type="target" position={Position.Top} style={{ borderColor: color }} />

      <Flex direction="column" gap={1.5}>
        <Flex align="center" justify="space-between">
          <Text fontSize="xl" fontWeight="black" color={color} letterSpacing="widest">
            {data.ticker}
          </Text>
          {/* Status pulse dot */}
          <Box
            w={2.5} h={2.5} borderRadius="full" bg={sc}
            boxShadow={data.status === 'running' ? `0 0 6px ${sc}` : 'none'}
            sx={data.status === 'running' ? {
              animation: 'hdpulse 1.5s ease-in-out infinite',
              '@keyframes hdpulse': {
                '0%,100%': { opacity: 1 },
                '50%':     { opacity: 0.35 },
              },
            } : {}}
          />
        </Flex>

        <Box h="1px" bg={`${color}28`} />

        <Flex align="center" justify="space-between">
          <Badge fontSize="2xs" colorScheme="whiteAlpha" variant="subtle">Pipeline</Badge>
          {total > 0 && (
            <Text fontSize="2xs" color="rgba(255,255,255,0.4)">
              {done}/{total} done
            </Text>
          )}
        </Flex>
      </Flex>

      <Handle type="source" position={Position.Bottom} style={{ borderColor: color }} />
    </Box>
  );
};

const nodeTypes = { agentNode: AgentNode, tickerHeader: TickerHeaderNode };

// ─── Layout state ─────────────────────────────────────────────────────────────
interface LayoutState {
  // Scan phase
  scanPhase1Count: number;
  scanLastY:       number;
  hasScan:         boolean;
  lastScanNodeId:  string | null;
  // Ticker columns
  identifierToCol:       Map<string, number>;
  identifierLastNode:    Map<string, string>;
  identifierAgentRow:    Map<string, number>;
  identifierAgentCount:  Map<string, number>;
  identifierDoneCount:   Map<string, number>;
  colCount:     number;
  tickerStartY: number;
  maxTickerY:   number;
  // Tracking
  seenNodeIds:    Set<string>;
  seenEdgeIds:    Set<string>;
  processedCount: number;
}

function freshLayout(): LayoutState {
  return {
    scanPhase1Count: 0,
    scanLastY:       0,
    hasScan:         false,
    lastScanNodeId:  null,
    identifierToCol:      new Map(),
    identifierLastNode:   new Map(),
    identifierAgentRow:   new Map(),
    identifierAgentCount: new Map(),
    identifierDoneCount:  new Map(),
    colCount:     0,
    tickerStartY: 0,
    maxTickerY:   0,
    seenNodeIds:    new Set(),
    seenEdgeIds:    new Set(),
    processedCount: 0,
  };
}

// ─── Props ────────────────────────────────────────────────────────────────────
interface AgentGraphProps {
  events:        AgentEvent[];
  onNodeClick?:  (nodeId: string, identifier?: string) => void;
  onNodeRerun?:  (identifier: string, nodeId: string) => void;
}

// ─── Component ────────────────────────────────────────────────────────────────
export const AgentGraph: React.FC<AgentGraphProps> = ({ events, onNodeClick, onNodeRerun }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const ls = useRef<LayoutState>(freshLayout());

  useEffect(() => {
    const newEvents = events.slice(ls.current.processedCount);
    if (newEvents.length === 0) return;
    ls.current.processedCount = events.length;

    const addedNodes:   Node[]                      = [];
    const addedEdges:   Edge[]                      = [];
    const patchMap: Map<string, Partial<Node['data']>> = new Map();

    for (const evt of newEvents) {
      const nodeId     = evt.node_id;
      if (!nodeId || nodeId === '__system__') continue;

      const identifier = evt.identifier ?? '';
      const kind       = classifyNode(nodeId, identifier);
      if (kind === 'skip') continue;

      const scopedId = identifier ? `${nodeId}:${identifier}` : nodeId;
      const isResult = evt.type === 'result';

      // ── Update path (node already exists) ──────────────────────────────────
      if (ls.current.seenNodeIds.has(scopedId)) {
        if (isResult && kind === 'ticker') {
          const done  = (ls.current.identifierDoneCount.get(identifier) ?? 0) + 1;
          const total = ls.current.identifierAgentCount.get(identifier) ?? 0;
          ls.current.identifierDoneCount.set(identifier, done);
          patchMap.set(`header:${identifier}`, {
            completedCount: done,
            agentCount:     total,
            status: done >= total && total > 0 ? 'completed' : 'running',
          });
        }
        const prev = patchMap.get(scopedId);
        const wasDone = prev?.status === 'completed';
        patchMap.set(scopedId, {
          ...prev,
          status:  wasDone || isResult ? 'completed' : 'running',
          metrics: evt.metrics ?? prev?.metrics,
        });
        continue;
      }

      // ── Create path (new node) ─────────────────────────────────────────────
      ls.current.seenNodeIds.add(scopedId);
      let x = 0, y = 0;
      let parentScopedId: string | null = null;

      if (kind === 'scan') {
        if (SCAN_PHASE1.includes(nodeId)) {
          x = ls.current.scanPhase1Count * COL_WIDTH;
          y = SCAN_TOP_Y;
          ls.current.scanPhase1Count++;
        } else {
          const phaseRow = SCAN_PHASE2.has(nodeId) ? 1 : 2;
          x = SCAN_CENTER_X;
          y = SCAN_TOP_Y + phaseRow * SCAN_ROW_H;
          if (evt.parent_node_id && evt.parent_node_id !== 'start') {
            const pid = evt.parent_node_id;
            parentScopedId = identifier ? `${pid}:${identifier}` : pid;
          }
        }
        ls.current.hasScan      = true;
        ls.current.scanLastY    = Math.max(ls.current.scanLastY, y);
        ls.current.lastScanNodeId = scopedId;

      } else if (kind === 'ticker') {
        // Create ticker header column if this is the first agent for this identifier
        if (!ls.current.identifierToCol.has(identifier)) {
          const col = ls.current.colCount++;
          ls.current.identifierToCol.set(identifier, col);
          ls.current.identifierAgentRow.set(identifier, 0);
          ls.current.identifierAgentCount.set(identifier, 0);
          ls.current.identifierDoneCount.set(identifier, 0);

          if (!ls.current.tickerStartY) {
            ls.current.tickerStartY = ls.current.hasScan
              ? ls.current.scanLastY + SCAN_ROW_H + TICKER_GAP
              : SCAN_TOP_Y;
          }

          const hx = col * COL_WIDTH;
          const hy = ls.current.tickerStartY;
          const hid = `header:${identifier}`;

          addedNodes.push({
            id: hid, type: 'tickerHeader',
            position: { x: hx, y: hy },
            data: { ticker: identifier, status: 'running', agentCount: 0, completedCount: 0,
                    node_id: 'header', identifier },
          });
          ls.current.seenNodeIds.add(hid);

          // Fan-out edge: last scan node → this ticker header
          const lastScan = ls.current.lastScanNodeId;
          if (lastScan) {
            const eid = `e-${lastScan}-${hid}`;
            if (!ls.current.seenEdgeIds.has(eid)) {
              ls.current.seenEdgeIds.add(eid);
              addedEdges.push({
                id: eid, source: lastScan, target: hid, animated: true,
                style: { stroke: '#4fd1c5', strokeDasharray: '5 5' },
              });
            }
          }
        }

        const col      = ls.current.identifierToCol.get(identifier)!;
        const agentRow = ls.current.identifierAgentRow.get(identifier)!;
        ls.current.identifierAgentRow.set(identifier, agentRow + 1);
        const newCount = (ls.current.identifierAgentCount.get(identifier) ?? 0) + 1;
        ls.current.identifierAgentCount.set(identifier, newCount);

        x = col * COL_WIDTH;
        y = ls.current.tickerStartY + TICKER_HDR_H + agentRow * ROW_HEIGHT;
        ls.current.maxTickerY = Math.max(ls.current.maxTickerY, y);

        // Parent: previous node in same column (header → agent0 → agent1 → …)
        parentScopedId = ls.current.identifierLastNode.get(identifier) ?? `header:${identifier}`;
        ls.current.identifierLastNode.set(identifier, scopedId);

        // Update header agent count
        patchMap.set(`header:${identifier}`, {
          ...(patchMap.get(`header:${identifier}`) ?? {}),
          agentCount: newCount,
        });

      } else {
        // portfolio
        const totalW = ls.current.colCount * COL_WIDTH;
        x = totalW > 0 ? totalW / 2 - 100 : SCAN_CENTER_X;
        y = ls.current.maxTickerY + ROW_HEIGHT + TICKER_GAP;
      }

      addedNodes.push({
        id: scopedId, type: 'agentNode',
        position: { x, y },
        data: {
          agent:      evt.agent,
          label:      toLabel(nodeId),
          identifier,
          node_id:    nodeId,
          status:     isResult ? 'completed' : 'running',
          metrics:    evt.metrics,
          onRerun:    onNodeRerun ? () => onNodeRerun(identifier, nodeId) : undefined,
        },
      });

      // Edge to parent
      if (parentScopedId) {
        const eid = `e-${parentScopedId}-${scopedId}`;
        if (!ls.current.seenEdgeIds.has(eid)) {
          ls.current.seenEdgeIds.add(eid);
          addedEdges.push({
            id: eid, source: parentScopedId, target: scopedId, animated: true,
            style: { stroke: '#4fd1c5' },
          });
        }
      }
    }

    if (addedNodes.length > 0)   setNodes(prev => [...prev, ...addedNodes]);
    if (addedEdges.length > 0)   setEdges(prev => [...prev, ...addedEdges]);
    if (patchMap.size > 0) {
      setNodes(prev => prev.map(n => {
        const patch = patchMap.get(n.id);
        if (!patch) return n;
        const finalStatus = n.data.status === 'completed' ? 'completed' : (patch.status ?? n.data.status);
        return { ...n, data: { ...n.data, ...patch, status: finalStatus } };
      }));
    }
  }, [events, setNodes, setEdges, onNodeRerun]);

  // Reset on new run (events cleared)
  useEffect(() => {
    if (events.length === 0) {
      ls.current = freshLayout();
      setNodes([]);
      setEdges([]);
    }
  }, [events.length, setNodes, setEdges]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    onNodeClick?.(node.data.node_id as string, node.data.identifier as string);
  }, [onNodeClick]);

  return (
    <Box h="100%" w="100%" bg="#020617">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
      >
        <Background color="#1e293b" gap={20} />
        <Controls />
      </ReactFlow>
    </Box>
  );
};
