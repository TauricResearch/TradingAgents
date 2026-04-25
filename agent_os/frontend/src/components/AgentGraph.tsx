import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  applyNodeChanges,
  Background,
  Controls,
  Edge,
  Handle,
  MarkerType,
  Node,
  NodeChange,
  NodeProps,
  Panel,
  Position,
  ReactFlowInstance,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box, Text, Flex, Icon, Badge, IconButton, Tooltip } from '@chakra-ui/react';
import { Cpu, Settings, Database, TrendingUp, Clock, RefreshCw } from 'lucide-react';
import { AgentEvent } from '../hooks/useAgentStream';

const COL_WIDTH = 230;
const ROW_HEIGHT = 148;
const TOP_PADDING = 40;
const TICKER_GAP = 80;
const TICKER_HDR_H = 108;
const TICKER_HDR_TO_NODE_GAP = 24;
const NODE_WIDTH = 200;

const SCAN_LEVELS: Record<string, number> = {
  gatekeeper_scanner: 0,
  geopolitical_scanner: 0,
  market_movers_scanner: 0,
  sector_scanner: 0,
  factor_alignment_scanner: 1,
  smart_money_scanner: 1,
  drift_scanner: 1,
  industry_deep_dive: 2,
  macro_synthesis: 3,
};

const SCAN_ORDER: Record<string, number> = {
  gatekeeper_scanner: 0,
  geopolitical_scanner: 1,
  market_movers_scanner: 2,
  sector_scanner: 3,
  factor_alignment_scanner: 4,
  smart_money_scanner: 5,
  drift_scanner: 6,
  industry_deep_dive: 7,
  macro_synthesis: 8,
};

const SCAN_PREDECESSORS: Record<string, string[]> = {
  factor_alignment_scanner: ['sector_scanner'],
  smart_money_scanner: ['sector_scanner'],
  drift_scanner: ['sector_scanner', 'market_movers_scanner', 'gatekeeper_scanner'],
  industry_deep_dive: [
    'gatekeeper_scanner',
    'geopolitical_scanner',
    'market_movers_scanner',
    'factor_alignment_scanner',
    'smart_money_scanner',
    'drift_scanner',
  ],
  macro_synthesis: ['industry_deep_dive'],
};

const PORTFOLIO_LEVELS: Record<string, number> = {
  load_portfolio: 0,
  compute_risk: 1,
  review_holdings: 2,
  prioritize_candidates: 3,
  macro_summary: 4,
  micro_summary: 4,
  make_pm_decision: 5,
  cash_sweep: 6,
  execute_trades: 7,
};

const PORTFOLIO_ORDER: Record<string, number> = {
  load_portfolio: 0,
  compute_risk: 1,
  review_holdings: 2,
  prioritize_candidates: 3,
  macro_summary: 4,
  micro_summary: 5,
  make_pm_decision: 6,
  cash_sweep: 7,
  execute_trades: 8,
};

const PORTFOLIO_PREDECESSORS: Record<string, string[]> = {
  compute_risk: ['load_portfolio'],
  review_holdings: ['compute_risk'],
  prioritize_candidates: ['review_holdings'],
  macro_summary: ['prioritize_candidates'],
  micro_summary: ['prioritize_candidates'],
  make_pm_decision: ['macro_summary', 'micro_summary'],
  cash_sweep: ['make_pm_decision'],
  execute_trades: ['cash_sweep'],
};

const ANALYST_IDS = new Set([
  'market_analyst',
  'social_analyst',
  'news_analyst',
  'news_fact_checker',
  'fundamentals_analyst',
]);

const TICKER_FIXED_ORDER: Record<string, number> = {
  bull_researcher: 100,
  bear_researcher: 110,
  research_manager: 120,
  trader: 130,
  risk_manager: 135,
  aggressive_analyst: 140,
  conservative_analyst: 150,
  neutral_analyst: 160,
  portfolio_manager: 170,
};

const PIPELINE_RERUNNABLE = new Set([
  'market_analyst',
  'social_analyst',
  'news_analyst',
  'news_fact_checker',
  'fundamentals_analyst',
  'bull_researcher',
  'bear_researcher',
  'research_manager',
  'trader',
  'aggressive_analyst',
  'conservative_analyst',
  'neutral_analyst',
  'portfolio_manager',
]);

type NodeKind = 'scan' | 'ticker' | 'portfolio' | 'skip';

interface GraphRecord {
  id: string;
  identifier: string;
  normalizedId: string;
  rawNodeId: string;
  label: string;
  kind: Exclude<NodeKind, 'skip'>;
  firstSeen: number;
  rerunSeq: number;
  stale: boolean;
  status: 'running' | 'completed' | 'error';
  metrics?: AgentEvent['metrics'];
}

interface GraphBuild {
  nodes: Node[];
  edges: Edge[];
}

function normalizeNodeId(nodeId: string): string {
  const base = nodeId
    .trim()
    .replace(/\s+/g, '_')
    .replace(/-/g, '_')
    .replace(/[^\w]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();

  if (base === 'social_media_analyst') return 'social_analyst';
  return base;
}

function toLabel(nodeId: string): string {
  if (/[A-Z]/.test(nodeId) && nodeId.includes(' ')) return nodeId;
  return nodeId
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function scopeId(normalizedId: string, identifier: string): string {
  return identifier ? `${normalizedId}:${identifier}` : normalizedId;
}

function classifyNode(normalizedId: string, identifier: string): NodeKind {
  if (normalizedId.startsWith('tool_')) return 'skip';
  if (identifier === 'MARKET' || normalizedId in SCAN_LEVELS) return 'scan';
  if (identifier === 'PORTFOLIO' || normalizedId in PORTFOLIO_LEVELS) return 'portfolio';
  if (identifier) return 'ticker';
  return 'skip';
}

function canRerunNode(normalizedId: string, identifier: string): boolean {
  if (identifier === 'MARKET') return true;
  return PIPELINE_RERUNNABLE.has(normalizedId);
}

function getEventRerunSeq(event: AgentEvent): number {
  return typeof event.rerun_seq === 'number' ? event.rerun_seq : 0;
}

const PIPELINE_PHASE_ORDER: Record<string, number> = {
  market_analyst: 0,
  social_analyst: 1,
  news_analyst: 2,
  news_fact_checker: 3,
  fundamentals_analyst: 4,
  bull_researcher: 5,
  bear_researcher: 6,
  research_manager: 7,
  trader: 8,
  aggressive_analyst: 9,
  conservative_analyst: 10,
  neutral_analyst: 11,
  portfolio_manager: 12,
};

function getNodeOrder(kind: Exclude<NodeKind, 'skip'>, normalizedId: string): number {
  if (kind === 'scan') return SCAN_ORDER[normalizedId] ?? 999;
  if (kind === 'portfolio') return PORTFOLIO_ORDER[normalizedId] ?? 999;
  return PIPELINE_PHASE_ORDER[normalizedId] ?? 999;
}

const STATUS_COLORS: Record<string, string> = {
  running: '#4fd1c5',
  completed: '#68d391',
  error: '#fc8181',
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
  if (!id || id === 'MARKET') return '#4fd1c5';
  if (id === 'PORTFOLIO') return '#9f7aea';
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xffff;
  return ID_PALETTE[h % ID_PALETTE.length];
}

const AgentNode = ({ data }: NodeProps) => {
  const getIcon = (agent = '') => {
    const a = agent.toUpperCase();
    if (a.includes('ANALYST') || a.includes('SCANNER')) return Cpu;
    if (a.includes('RESEARCHER') || a.includes('MANAGER') || a.includes('SYNTHESIS') || a.includes('DIVE')) return Database;
    if (a.includes('TRADER') || a.includes('RISK') || a.includes('JUDGE')) return TrendingUp;
    return Settings;
  };

  const sc = statusColor(data.status);
  const canRerun = data.status === 'completed' || data.status === 'error';
  const totalTok = (data.metrics?.tokens_in ?? 0) + (data.metrics?.tokens_out ?? 0);
  const isStale = Boolean(data.stale);

  return (
    <Box
      bg="#0f172a"
      border="1px solid"
      borderColor={sc}
      borderStyle={isStale ? 'dashed' : 'solid'}
      p={3}
      borderRadius="lg"
      w="200px"
      boxShadow={`0 0 12px ${sc}35`}
      cursor="pointer"
      opacity={isStale ? 0.6 : 1}
      _hover={{ borderColor: '#67e8f9', boxShadow: '0 0 18px #67e8f940' }}
    >
      <Handle type="target" position={data.layoutDir === 'LR' ? Position.Left : Position.Top} style={{ borderColor: sc }} />

      <Flex direction="column" gap={1.5}>
        <Flex align="center" gap={1.5}>
          <Icon as={getIcon(data.agent)} color={sc} boxSize={3.5} />
          <Text fontSize="xs" fontWeight="bold" color="white" flex={1} noOfLines={1}>
            {data.label}
          </Text>
          {typeof data.rerunSeq === 'number' && data.rerunSeq > 0 && (
            <Badge colorScheme="cyan" fontSize="2xs">{`R${data.rerunSeq}`}</Badge>
          )}
          {isStale && <Badge colorScheme="orange" fontSize="2xs">STALE</Badge>}
          {data.status === 'completed' && <Badge colorScheme="green" fontSize="2xs">✓</Badge>}
          {data.status === 'error' && <Badge colorScheme="red" fontSize="2xs">✗</Badge>}
        </Flex>

        <Box h="1px" bg="rgba(255,255,255,0.08)" />

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

        {data.metrics?.model && data.metrics.model.toLowerCase() !== 'unknown' && data.metrics.model.toLowerCase() !== 'langgraph_node' && (
          <Tooltip label={data.metrics.model} placement="top" hasArrow openDelay={300}>
            <Badge
              variant="outline"
              fontSize="2xs"
              colorScheme="blue"
              display="block"
              maxW="100%"
              overflow="hidden"
              textOverflow="ellipsis"
              whiteSpace="nowrap"
            >
              {data.metrics.model}
            </Badge>
          </Tooltip>
        )}

        {data.status === 'running' && (
          <Box w="100%" h="2px" bg="rgba(79,209,197,0.25)" borderRadius="full" overflow="hidden">
            <Box
              as="div"
              w="40%"
              h="100%"
              bg="#4fd1c5"
              sx={{
                animation: 'shimmer 1.5s infinite linear',
                '@keyframes shimmer': {
                  '0%': { transform: 'translateX(-100%)' },
                  '100%': { transform: 'translateX(300%)' },
                },
              }}
            />
          </Box>
        )}

        {canRerun && data.onRerun && (
          <Tooltip label="Re-run" placement="bottom" hasArrow>
            <IconButton
              aria-label="Re-run"
              icon={<RefreshCw size={11} />}
              size="xs"
              variant="ghost"
              colorScheme="cyan"
              alignSelf="flex-end"
              onClick={(e) => { e.stopPropagation(); data.onRerun(); }}
            />
          </Tooltip>
        )}
      </Flex>

      <Handle type="source" position={data.layoutDir === 'LR' ? Position.Right : Position.Bottom} style={{ borderColor: sc }} />
    </Box>
  );
};

const TickerHeaderNode = ({ data }: NodeProps) => {
  const color = identifierColor(data.ticker);
  const sc = statusColor(data.status ?? 'running');
  const done = data.completedCount ?? 0;
  const total = data.agentCount ?? 0;
  const stale = data.staleCount ?? 0;

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
      <Handle type="target" position={data.layoutDir === 'LR' ? Position.Left : Position.Top} style={{ borderColor: color }} />

      <Flex direction="column" gap={1.5}>
        <Flex align="center" justify="space-between">
          <Text fontSize="xl" fontWeight="black" color={color} letterSpacing="widest">
            {data.ticker}
          </Text>
          <Box
            w={2.5}
            h={2.5}
            borderRadius="full"
            bg={sc}
            boxShadow={data.status === 'running' ? `0 0 6px ${sc}` : 'none'}
            sx={data.status === 'running' ? {
              animation: 'hdpulse 1.5s ease-in-out infinite',
              '@keyframes hdpulse': {
                '0%,100%': { opacity: 1 },
                '50%': { opacity: 0.35 },
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
        {stale > 0 && (
          <Badge alignSelf="flex-start" colorScheme="orange" variant="subtle" fontSize="2xs">
            {stale} stale
          </Badge>
        )}
      </Flex>

      <Handle type="source" position={data.layoutDir === 'LR' ? Position.Right : Position.Bottom} style={{ borderColor: color }} />
    </Box>
  );
};

const nodeTypes = { agentNode: AgentNode, tickerHeader: TickerHeaderNode };

interface AgentGraphProps {
  events: AgentEvent[];
  allEvents?: AgentEvent[];
  runStatus?: 'idle' | 'connecting' | 'streaming' | 'completed' | 'paused' | 'error';
  onNodeClick?: (nodeId: string, identifier?: string) => void;
  onNodeRerun?: (identifier: string, nodeId: string) => void;
}

type PositionOverrides = Record<string, { x: number; y: number }>;

function centeredX(index: number, count: number, maxColumns: number): number {
  const offset = ((maxColumns - count) * COL_WIDTH) / 2;
  return offset + index * COL_WIDTH;
}

function centeredY(index: number, count: number, maxRows: number): number {
  const offset = ((maxRows - count) * ROW_HEIGHT) / 2;
  return offset + index * ROW_HEIGHT;
}

function buildGraph(
  events: AgentEvent[],
  allEvents: AgentEvent[],
  runStatus?: AgentGraphProps['runStatus'],
  onNodeRerun?: AgentGraphProps['onNodeRerun'],
  layoutDir: 'TB' | 'LR' = 'TB',
): GraphBuild {
  const records = new Map<string, GraphRecord>();
  const edgeKeys = new Set<string>();
  const edges: Edge[] = [];
  const deferredEdges: Array<{ source: string; target: string }> = [];
  const tickerHeaders = new Map<string, { firstSeen: number; agentCount: number; completedCount: number; staleCount: number; status: 'running' | 'completed' | 'error' }>();
  const latestSeqByIdentifier = new Map<string, number>();
  const latestSeqStartOrderByIdentifier = new Map<string, number>();

  allEvents.forEach((evt) => {
    const rawNodeId = evt.node_id;
    if (!rawNodeId || rawNodeId === '__system__') return;
    const identifier = evt.identifier ?? '';
    const normalizedId = normalizeNodeId(rawNodeId);
    const kind = classifyNode(normalizedId, identifier);
    if (kind === 'skip') return;
    const rerunSeq = getEventRerunSeq(evt);
    const current = latestSeqByIdentifier.get(identifier) ?? 0;
    if (rerunSeq > current) latestSeqByIdentifier.set(identifier, rerunSeq);
  });

  allEvents.forEach((evt) => {
    const rawNodeId = evt.node_id;
    if (!rawNodeId || rawNodeId === '__system__') return;
    const identifier = evt.identifier ?? '';
    const normalizedId = normalizeNodeId(rawNodeId);
    const kind = classifyNode(normalizedId, identifier);
    if (kind === 'skip') return;
    const rerunSeq = getEventRerunSeq(evt);
    if (rerunSeq !== (latestSeqByIdentifier.get(identifier) ?? 0)) return;
    const order = getNodeOrder(kind, normalizedId);
    const currentOrder = latestSeqStartOrderByIdentifier.get(identifier);
    if (currentOrder === undefined || order < currentOrder) {
      latestSeqStartOrderByIdentifier.set(identifier, order);
    }
  });

  const pushEdge = (source: string, target: string, color = '#4fd1c5', dashed = false) => {
    if (source === target) return;
    const key = `${source}->${target}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    edges.push({
      id: `e-${source}-${target}`,
      source,
      target,
      type: 'smoothstep',
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color },
      style: {
        stroke: color,
        strokeWidth: 1.5,
        ...(dashed ? { strokeDasharray: '5 5' } : {}),
      },
    });
  };

  const lastTickerNodeByIdentifier = new Map<string, string>();

  events.forEach((evt, index) => {
    const rawNodeId = evt.node_id;
    if (!rawNodeId || rawNodeId === '__system__') return;

    const identifier = evt.identifier ?? '';
    const normalizedId = normalizeNodeId(rawNodeId);
    const kind = classifyNode(normalizedId, identifier);
    if (kind === 'skip') return;

    const recordId = scopeId(normalizedId, identifier);
    const existing = records.get(recordId);
    const rerunSeq = getEventRerunSeq(evt);
    const completed = evt.type === 'result' || evt.status === 'success' || evt.status === 'graceful_skip';
    const wasCompleted = existing?.status === 'completed';
    const nextStatus: GraphRecord['status'] =
      evt.status === 'error'
        ? 'error'
        : completed
          ? 'completed'
          : 'running';

    if (!existing) {
      records.set(recordId, {
        id: recordId,
        identifier,
        normalizedId,
        rawNodeId,
        label: toLabel(rawNodeId),
        kind,
        firstSeen: index,
        rerunSeq,
        stale: false,
        status: nextStatus,
        metrics: evt.metrics,
      });
    } else {
      if (rerunSeq >= existing.rerunSeq) {
        existing.rerunSeq = rerunSeq;
        existing.rawNodeId = rawNodeId;
        existing.label = toLabel(rawNodeId);
        if (evt.metrics && Object.keys(evt.metrics).length > 0) {
          existing.metrics = evt.metrics;
        }
      }
      existing.status = existing.status === 'error' || nextStatus === 'error'
        ? 'error'
        : existing.status === 'completed' || nextStatus === 'completed'
          ? 'completed'
          : 'running';
    }

    if (kind === 'ticker') {
      if (!tickerHeaders.has(identifier)) {
        tickerHeaders.set(identifier, {
          firstSeen: index,
          agentCount: 0,
          completedCount: 0,
          staleCount: 0,
          status: 'running',
        });
      }

      const header = tickerHeaders.get(identifier)!;
      if (!existing) header.agentCount += 1;
      if (completed && !wasCompleted) header.completedCount += 1;
      header.status = header.completedCount >= header.agentCount && header.agentCount > 0 ? 'completed' : 'running';

      const prevTickerNode = lastTickerNodeByIdentifier.get(identifier);
      if (prevTickerNode && prevTickerNode !== recordId) {
        pushEdge(prevTickerNode, recordId);
      }
      lastTickerNodeByIdentifier.set(identifier, recordId);
    }

    const parentNodeId = evt.parent_node_id;
    if (parentNodeId && parentNodeId !== 'start') {
      const parentNormalized = normalizeNodeId(parentNodeId);
      const parentKind = classifyNode(parentNormalized, identifier);
      if (parentKind !== 'skip') {
        deferredEdges.push({
          source: scopeId(parentNormalized, identifier),
          target: recordId,
        });
      }
    }
  });

  deferredEdges.forEach(({ source, target }) => {
    if (records.has(source) && records.has(target)) {
      pushEdge(source, target);
    }
  });

  for (const record of records.values()) {
    const latestSeq = latestSeqByIdentifier.get(record.identifier) ?? 0;
    const latestStartOrder = latestSeqStartOrderByIdentifier.get(record.identifier);
    const order = getNodeOrder(record.kind, record.normalizedId);
    record.stale = (
      latestStartOrder !== undefined &&
      record.rerunSeq < latestSeq &&
      order >= latestStartOrder
    );
  }

  for (const [identifier, header] of tickerHeaders.entries()) {
    const scopedRecords = [...records.values()].filter((record) => record.kind === 'ticker' && record.identifier === identifier);
    header.agentCount = scopedRecords.length;
    header.completedCount = scopedRecords.filter((record) => record.status === 'completed' && !record.stale).length;
    header.staleCount = scopedRecords.filter((record) => record.stale).length;
    header.status = scopedRecords.some((record) => record.status === 'error' && !record.stale)
      ? 'error'
      : scopedRecords.some((record) => record.status === 'running' || record.stale)
        ? 'running'
        : 'completed';
  }

  if (runStatus === 'error') {
    for (const record of records.values()) {
      if (record.status === 'running') {
        record.status = 'error';
      }
    }
    for (const header of tickerHeaders.values()) {
      if (header.status === 'running') {
        header.status = 'error';
      }
    }
  }

  for (const record of records.values()) {
    if (record.kind === 'scan') {
      for (const parent of SCAN_PREDECESSORS[record.normalizedId] ?? []) {
        const source = scopeId(parent, record.identifier);
        if (records.has(source)) pushEdge(source, record.id);
      }
    }

    if (record.kind === 'portfolio') {
      for (const parent of PORTFOLIO_PREDECESSORS[record.normalizedId] ?? []) {
        const source = scopeId(parent, record.identifier);
        if (records.has(source)) pushEdge(source, record.id);
      }
    }
  }

  const scanRecords = [...records.values()]
    .filter((record) => record.kind === 'scan')
    .sort((a, b) => (SCAN_ORDER[a.normalizedId] ?? 999) - (SCAN_ORDER[b.normalizedId] ?? 999) || a.firstSeen - b.firstSeen);

  const portfolioRecords = [...records.values()]
    .filter((record) => record.kind === 'portfolio')
    .sort((a, b) => (PORTFOLIO_ORDER[a.normalizedId] ?? 999) - (PORTFOLIO_ORDER[b.normalizedId] ?? 999) || a.firstSeen - b.firstSeen);

  const tickerIdentifiers = [...tickerHeaders.entries()]
    .sort((a, b) => a[1].firstSeen - b[1].firstSeen)
    .map(([identifier]) => identifier);

  const analystOrder = [...records.values()]
    .filter((record) => record.kind === 'ticker' && ANALYST_IDS.has(record.normalizedId))
    .sort((a, b) => a.firstSeen - b.firstSeen)
    .reduce<string[]>((ordered, record) => {
      if (!ordered.includes(record.normalizedId)) ordered.push(record.normalizedId);
      return ordered;
    }, []);

  const tickerRowOrder = new Map<string, number>();
  analystOrder.forEach((normalizedId, index) => {
    tickerRowOrder.set(normalizedId, index);
  });

  const tickerBase = analystOrder.length;
  let fixedRow = tickerBase;
  Object.keys(TICKER_FIXED_ORDER).forEach((normalizedId) => {
    tickerRowOrder.set(normalizedId, fixedRow++);
  });

  const unknownTickerNodes = [...records.values()]
    .filter((record) => record.kind === 'ticker' && !tickerRowOrder.has(record.normalizedId))
    .sort((a, b) => a.firstSeen - b.firstSeen);

  unknownTickerNodes.forEach((record, index) => {
    tickerRowOrder.set(record.normalizedId, fixedRow + index);
  });

  const maxScanColumns = scanRecords.reduce((max, record) => {
    const rowCount = scanRecords.filter((item) => SCAN_LEVELS[item.normalizedId] === SCAN_LEVELS[record.normalizedId]).length;
    return Math.max(max, rowCount);
  }, 1);

  const maxPortfolioColumns = portfolioRecords.reduce((max, record) => {
    const rowCount = portfolioRecords.filter((item) => PORTFOLIO_LEVELS[item.normalizedId] === PORTFOLIO_LEVELS[record.normalizedId]).length;
    return Math.max(max, rowCount);
  }, 1);

  const maxColumns = Math.max(tickerIdentifiers.length, maxScanColumns, maxPortfolioColumns, 1);

  // Pre-compute ticker records and maxTickerRows so LR section geometry can use it
  const tickerRecords = [...records.values()]
    .filter((record) => record.kind === 'ticker')
    .sort((a, b) => {
      const byIdentifier = tickerIdentifiers.indexOf(a.identifier) - tickerIdentifiers.indexOf(b.identifier);
      if (byIdentifier !== 0) return byIdentifier;
      return (tickerRowOrder.get(a.normalizedId) ?? 999) - (tickerRowOrder.get(b.normalizedId) ?? 999) || a.firstSeen - b.firstSeen;
    });

  const maxTickerRows = tickerRecords.length > 0
    ? Math.max(...tickerRecords.map((r) => tickerRowOrder.get(r.normalizedId) ?? 0)) + 1
    : 0;

  const nodes: Node[] = [];

  // ── LR geometry ──────────────────────────────────────────────────────────
  const maxScanLevel = scanRecords.length > 0
    ? Math.max(...scanRecords.map((r) => SCAN_LEVELS[r.normalizedId] ?? 0))
    : -1;

  // LR: sections are placed left→right; scan first, then ticker, then portfolio
  const scanSectionSpanLR = maxScanLevel >= 0 ? (maxScanLevel + 1) * COL_WIDTH : 0;
  const tickerSectionStartLR = TOP_PADDING + (scanSectionSpanLR > 0 ? scanSectionSpanLR + TICKER_GAP : 0);
  const tickerNodeStartLR = tickerSectionStartLR + NODE_WIDTH + TICKER_HDR_TO_NODE_GAP;
  const tickerSectionSpanLR = tickerIdentifiers.length > 0
    ? NODE_WIDTH + TICKER_HDR_TO_NODE_GAP + maxTickerRows * COL_WIDTH
    : 0;
  const portfolioSectionStartLR = tickerSectionSpanLR > 0
    ? tickerSectionStartLR + tickerSectionSpanLR + TICKER_GAP
    : (scanSectionSpanLR > 0 ? TOP_PADDING + scanSectionSpanLR + TICKER_GAP : TOP_PADDING);

  const nodeData = (record: GraphRecord) => ({
    agent: record.rawNodeId,
    label: record.label,
    identifier: record.identifier,
    node_id: record.rawNodeId,
    status: record.status,
    metrics: record.metrics,
    stale: record.stale,
    rerunSeq: record.rerunSeq,
    layoutDir,
    onRerun: onNodeRerun && canRerunNode(record.normalizedId, record.identifier)
      ? () => onNodeRerun(record.identifier, record.rawNodeId)
      : undefined,
  });

  // ── Scan nodes ────────────────────────────────────────────────────────────
  const scanByLevel = new Map<number, GraphRecord[]>();
  scanRecords.forEach((record) => {
    const level = SCAN_LEVELS[record.normalizedId] ?? 0;
    scanByLevel.set(level, [...(scanByLevel.get(level) ?? []), record]);
  });

  for (const [level, row] of [...scanByLevel.entries()].sort((a, b) => a[0] - b[0])) {
    row.forEach((record, index) => {
      const position = layoutDir === 'LR'
        ? { x: TOP_PADDING + level * COL_WIDTH, y: centeredY(index, row.length, maxColumns) }
        : { x: centeredX(index, row.length, maxColumns), y: TOP_PADDING + level * ROW_HEIGHT };
      nodes.push({ id: record.id, type: 'agentNode', position, data: nodeData(record) });
    });
  }

  // ── Ticker section ────────────────────────────────────────────────────────
  const scanRowCount = scanByLevel.size;
  const tickerStartY = TOP_PADDING + (scanRowCount > 0 ? scanRowCount * ROW_HEIGHT + TICKER_GAP : 0);
  const tickerColumnOffset = ((maxColumns - Math.max(tickerIdentifiers.length, 1)) * COL_WIDTH) / 2;
  const tickerX = (index: number) => tickerColumnOffset + index * COL_WIDTH;

  tickerIdentifiers.forEach((identifier, index) => {
    const header = tickerHeaders.get(identifier)!;
    const position = layoutDir === 'LR'
      ? { x: tickerSectionStartLR, y: centeredY(index, tickerIdentifiers.length, maxColumns) }
      : { x: tickerX(index), y: tickerStartY };
    nodes.push({
      id: `header:${identifier}`,
      type: 'tickerHeader',
      position,
      data: { ticker: identifier, status: header.status, agentCount: header.agentCount, completedCount: header.completedCount, staleCount: header.staleCount, node_id: 'header', identifier, layoutDir },
    });
  });

  tickerRecords.forEach((record) => {
    const colIndex = tickerIdentifiers.indexOf(record.identifier);
    const rowIndex = tickerRowOrder.get(record.normalizedId) ?? 999;
    const position = layoutDir === 'LR'
      ? { x: tickerNodeStartLR + rowIndex * COL_WIDTH, y: centeredY(colIndex, tickerIdentifiers.length, maxColumns) }
      : { x: tickerX(colIndex), y: tickerStartY + TICKER_HDR_H + TICKER_HDR_TO_NODE_GAP + rowIndex * ROW_HEIGHT };
    nodes.push({ id: record.id, type: 'agentNode', position, data: nodeData(record) });
  });

  tickerIdentifiers.forEach((identifier) => {
    const firstTickerNode = tickerRecords.find((record) => record.identifier === identifier);
    if (firstTickerNode) {
      pushEdge(`header:${identifier}`, firstTickerNode.id, identifierColor(identifier), true);
    }
  });

  // ── Portfolio nodes ───────────────────────────────────────────────────────
  const portfolioStartY = tickerStartY + TICKER_HDR_H + TICKER_HDR_TO_NODE_GAP + (maxTickerRows > 0 ? maxTickerRows * ROW_HEIGHT + TICKER_GAP : 0);

  const portfolioByLevel = new Map<number, GraphRecord[]>();
  portfolioRecords.forEach((record) => {
    const level = PORTFOLIO_LEVELS[record.normalizedId] ?? 0;
    portfolioByLevel.set(level, [...(portfolioByLevel.get(level) ?? []), record]);
  });

  for (const [level, row] of [...portfolioByLevel.entries()].sort((a, b) => a[0] - b[0])) {
    row
      .sort((a, b) => (PORTFOLIO_ORDER[a.normalizedId] ?? 999) - (PORTFOLIO_ORDER[b.normalizedId] ?? 999) || a.firstSeen - b.firstSeen)
      .forEach((record, index) => {
        const position = layoutDir === 'LR'
          ? { x: portfolioSectionStartLR + level * COL_WIDTH, y: centeredY(index, row.length, maxColumns) }
          : { x: centeredX(index, row.length, maxColumns), y: portfolioStartY + level * ROW_HEIGHT };
        nodes.push({
          id: record.id,
          type: 'agentNode',
          position,
          data: {
            agent: record.rawNodeId,
            label: record.label,
            identifier: record.identifier,
            node_id: record.rawNodeId,
            status: record.status,
            metrics: record.metrics,
            stale: record.stale,
            rerunSeq: record.rerunSeq,
            layoutDir,
            onRerun: onNodeRerun && canRerunNode(record.normalizedId, record.identifier)
              ? () => onNodeRerun(record.identifier, record.rawNodeId)
              : undefined,
          },
        });
      });
  }

  return { nodes, edges };
}

export const AgentGraph: React.FC<AgentGraphProps> = ({ events, allEvents, runStatus, onNodeClick, onNodeRerun }) => {
  const [layoutDir, setLayoutDir] = useState<'TB' | 'LR'>('TB');
  const [positionOverrides, setPositionOverrides] = useState<PositionOverrides>({});
  const rfInstanceRef = useRef<ReactFlowInstance | null>(null);

  const { nodes: layoutNodes, edges } = useMemo(
    () => buildGraph(events, allEvents ?? events, runStatus, onNodeRerun, layoutDir),
    [events, allEvents, runStatus, onNodeRerun, layoutDir],
  );

  // Clear position overrides and re-fit when layout direction changes
  useEffect(() => {
    setPositionOverrides({});
    // Delay to let ReactFlow commit the new node positions after the state update
    const t = setTimeout(() => rfInstanceRef.current?.fitView({ padding: 0.15 }), 150);
    return () => clearTimeout(t);
  }, [layoutDir]);

  useEffect(() => {
    const validIds = new Set(layoutNodes.map((node) => node.id));
    setPositionOverrides((prev) => {
      const nextEntries = Object.entries(prev).filter(([id]) => validIds.has(id));
      if (nextEntries.length === Object.keys(prev).length) return prev;
      return Object.fromEntries(nextEntries);
    });
  }, [layoutNodes]);

  const nodes = useMemo(() => {
    return layoutNodes.map((node) => {
      const override = positionOverrides[node.id];
      return override ? { ...node, position: override } : node;
    });
  }, [layoutNodes, positionOverrides]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    setPositionOverrides((prev) => {
      const next = { ...prev };
      const updatedNodes = applyNodeChanges(changes, nodes);

      changes.forEach((change) => {
        if (change.type === 'remove') {
          delete next[change.id];
          return;
        }

        if (change.type === 'position') {
          const updated = updatedNodes.find((node) => node.id === change.id);
          if (updated) {
            next[change.id] = updated.position;
          }
        }
      });

      return next;
    });
  }, [nodes]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    onNodeClick?.(node.data.node_id as string, node.data.identifier as string);
  }, [onNodeClick]);

  return (
    <Box h="100%" w="100%" bg="#020617">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onNodeClick={handleNodeClick}
        onInit={(instance: ReactFlowInstance) => { rfInstanceRef.current = instance; }}
        nodeTypes={nodeTypes}
        nodesDraggable
        fitView
        fitViewOptions={{ padding: 0.15 }}
      >
        <Background color="#1e293b" gap={20} />
        <Controls />
        <Panel position="top-right">
          <Box
            as="button"
            onClick={() => setLayoutDir((d: 'TB' | 'LR') => (d === 'TB' ? 'LR' : 'TB'))}
            bg="#0f172a"
            border="1px solid"
            borderColor="whiteAlpha.200"
            color="whiteAlpha.700"
            fontSize="xs"
            fontWeight="semibold"
            px={3}
            py={1.5}
            borderRadius="md"
            cursor="pointer"
            _hover={{ borderColor: '#4fd1c5', color: '#4fd1c5' }}
            transition="all 0.15s"
            title={layoutDir === 'TB' ? 'Switch to horizontal layout' : 'Switch to vertical layout'}
          >
            {layoutDir === 'TB' ? '⇔ Horizontal' : '⇕ Vertical'}
          </Box>
        </Panel>
      </ReactFlow>
    </Box>
  );
};
