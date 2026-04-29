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

const AgentNode = React.memo(({ data }: NodeProps) => {
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
});

const TickerHeaderNode = React.memo(({ data }: NodeProps) => {
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
});

const nodeTypes = { agentNode: AgentNode, tickerHeader: TickerHeaderNode };

interface AgentGraphProps {
  events: AgentEvent[];
  allEvents?: AgentEvent[];
  runStatus?: 'idle' | 'connecting' | 'streaming' | 'completed' | 'paused' | 'error';
  onNodeClick?: (nodeId: string, identifier?: string) => void;
  onNodeRerun?: (identifier: string, nodeId: string) => void;
}

// ── NodeVisit: one temporal occurrence of a node in the pipeline ──────────────

interface NodeVisit {
  id: string;
  nodeKey: string;
  normalizedId: string;
  identifier: string;
  rawNodeId: string;
  label: string;
  kind: Exclude<NodeKind, 'skip'>;
  visitIndex: number;
  status: 'running' | 'completed' | 'error';
  startOrder: number;
  metrics?: AgentEvent['metrics'];
  stale: boolean;
  rerunSeq: number;
}

// buildVisits: builds a temporal ordered list of node visits.
// The same node can appear multiple times (e.g. bull/bear debate loops).
function buildVisits(
  events: AgentEvent[],
  allEvents: AgentEvent[],
  runStatus?: AgentGraphProps['runStatus'],
): NodeVisit[] {
  const visits: NodeVisit[] = [];
  const closedCount = new Map<string, number>();
  const currentVisit = new Map<string, NodeVisit>();
  const latestSeqByIdentifier = new Map<string, number>();
  const latestSeqStartOrderByIdentifier = new Map<string, number>();

  // First pass over allEvents: find latest rerun seq per identifier (for stale detection)
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
    const cur = latestSeqStartOrderByIdentifier.get(identifier);
    if (cur === undefined || order < cur) latestSeqStartOrderByIdentifier.set(identifier, order);
  });

  // Main pass: build temporal visits from events
  events.forEach((evt, index) => {
    const rawNodeId = evt.node_id;
    if (!rawNodeId || rawNodeId === '__system__') return;
    const identifier = evt.identifier ?? '';
    const normalizedId = normalizeNodeId(rawNodeId);
    const kind = classifyNode(normalizedId, identifier);
    if (kind === 'skip') return;

    const nodeKey = scopeId(normalizedId, identifier);
    const rerunSeq = getEventRerunSeq(evt);
    const isTerminal =
      evt.type === 'result' ||
      evt.status === 'success' ||
      evt.status === 'graceful_skip' ||
      evt.status === 'error';
    const nextStatus: NodeVisit['status'] =
      evt.status === 'error' ? 'error' : isTerminal ? 'completed' : 'running';

    let visit = currentVisit.get(nodeKey);

    if (!visit) {
      const visitIndex = closedCount.get(nodeKey) ?? 0;
      visit = {
        id: `${nodeKey}:v${visitIndex}`,
        nodeKey,
        normalizedId,
        identifier,
        rawNodeId,
        label: toLabel(rawNodeId),
        kind,
        visitIndex,
        status: nextStatus,
        startOrder: index,
        metrics: evt.metrics,
        stale: false,
        rerunSeq,
      };
      visits.push(visit);
      currentVisit.set(nodeKey, visit);
    } else {
      if (rerunSeq >= visit.rerunSeq) {
        visit.rerunSeq = rerunSeq;
        if (evt.metrics && Object.keys(evt.metrics).length > 0) visit.metrics = evt.metrics;
      }
      visit.status =
        visit.status === 'error' || nextStatus === 'error'
          ? 'error'
          : visit.status === 'completed' || nextStatus === 'completed'
            ? 'completed'
            : 'running';
    }

    if (isTerminal) {
      closedCount.set(nodeKey, (closedCount.get(nodeKey) ?? 0) + 1);
      currentVisit.delete(nodeKey);
    }
  });

  // Compute stale flag
  for (const visit of visits) {
    const latestSeq = latestSeqByIdentifier.get(visit.identifier) ?? 0;
    const latestStartOrder = latestSeqStartOrderByIdentifier.get(visit.identifier);
    const order = getNodeOrder(visit.kind, visit.normalizedId);
    visit.stale =
      latestStartOrder !== undefined &&
      visit.rerunSeq < latestSeq &&
      order >= latestStartOrder;
  }

  if (runStatus === 'error') {
    visits.forEach((v) => { if (v.status === 'running') v.status = 'error'; });
  }

  return visits;
}

// ── VisitRow: one row in the steps view ──────────────────────────────────────

interface VisitRowProps {
  visit: NodeVisit;
  isLast: boolean;
  isOpen: boolean;
  onToggle: () => void;
  onRerun?: () => void;
  onSelect?: () => void;
}

const VisitRow: React.FC<VisitRowProps> = ({ visit, isLast, isOpen, onToggle, onRerun, onSelect }) => {
  const sc = statusColor(visit.status);
  const totalTok = (visit.metrics?.tokens_in ?? 0) + (visit.metrics?.tokens_out ?? 0);
  const hasModel = Boolean(
    visit.metrics?.model &&
    visit.metrics.model !== 'unknown' &&
    visit.metrics.model !== 'langgraph_node',
  );
  const canRerunVisit = onRerun && (visit.status === 'completed' || visit.status === 'error');
  const hasDetails = hasModel || totalTok > 0 || Boolean(canRerunVisit);

  return (
    <Box position="relative" pl="28px">
      {/* Timeline connector */}
      {!isLast && (
        <Box
          position="absolute"
          left="9px"
          top="24px"
          w="2px"
          bottom="0"
          bg="whiteAlpha.100"
        />
      )}

      {/* Status dot */}
      <Box
        position="absolute"
        left="4px"
        top="13px"
        w="11px"
        h="11px"
        borderRadius="full"
        border="2px solid"
        borderColor={sc}
        bg={visit.status === 'running' ? sc : '#020617'}
        boxShadow={visit.status === 'running' ? `0 0 8px ${sc}` : 'none'}
        zIndex={1}
        sx={
          visit.status === 'running'
            ? {
                animation: 'visitdotpulse 1.4s ease-in-out infinite',
                '@keyframes visitdotpulse': {
                  '0%,100%': { opacity: 1 },
                  '50%': { opacity: 0.5 },
                },
              }
            : {}
        }
      />

      {/* Main row */}
      <Flex
        align="center"
        gap={2}
        py={1.5}
        pr={2}
        cursor={hasDetails ? 'pointer' : 'default'}
        borderRadius="md"
        _hover={hasDetails ? { bg: 'whiteAlpha.50' } : {}}
        onClick={() => {
          if (hasDetails) onToggle();
          onSelect?.();
        }}
        minH="36px"
      >
        <Text
          fontSize="sm"
          color={visit.stale ? 'whiteAlpha.350' : 'whiteAlpha.900'}
          fontWeight={visit.status === 'running' ? 'semibold' : 'normal'}
          textDecoration={visit.stale ? 'line-through' : 'none'}
          flex={1}
          noOfLines={1}
        >
          {visit.label}
        </Text>

        {/* Visit counter badge — shown when same node is visited more than once */}
        {visit.visitIndex > 0 && (
          <Badge colorScheme="gray" fontSize="2xs" flexShrink={0}>
            #{visit.visitIndex + 1}
          </Badge>
        )}
        {visit.stale && (
          <Badge colorScheme="orange" fontSize="2xs" flexShrink={0}>STALE</Badge>
        )}
        {visit.rerunSeq > 0 && (
          <Badge colorScheme="cyan" fontSize="2xs" flexShrink={0}>R{visit.rerunSeq}</Badge>
        )}

        <Flex align="center" gap={1.5} flexShrink={0}>
          {visit.metrics?.latency_ms != null && visit.metrics.latency_ms > 0 && (
            <Text fontSize="2xs" color="whiteAlpha.400">
              {visit.metrics.latency_ms >= 1000
                ? `${(visit.metrics.latency_ms / 1000).toFixed(1)}s`
                : `${visit.metrics.latency_ms}ms`}
            </Text>
          )}
          {visit.status === 'completed' && (
            <Text color="green.300" fontSize="xs" lineHeight={1}>✓</Text>
          )}
          {visit.status === 'error' && (
            <Text color="red.400" fontSize="xs" lineHeight={1}>✗</Text>
          )}
          {visit.status === 'running' && (
            <Box
              w="6px"
              h="6px"
              borderRadius="full"
              bg={sc}
              sx={{
                animation: 'visitrundot 1s ease-in-out infinite',
                '@keyframes visitrundot': {
                  '0%,100%': { transform: 'scale(1)', opacity: 1 },
                  '50%': { transform: 'scale(1.6)', opacity: 0.5 },
                },
              }}
            />
          )}
        </Flex>
      </Flex>

      {/* Expanded details */}
      {isOpen && hasDetails && (
        <Box pl={1} pb={2}>
          {hasModel && (
            <Text fontSize="2xs" fontFamily="mono" color="blue.300" noOfLines={1} mb={0.5}>
              {visit.metrics!.model}
            </Text>
          )}
          {totalTok > 0 && (
            <Text fontSize="2xs" color="whiteAlpha.400">
              {(visit.metrics?.tokens_in ?? 0).toLocaleString()} in&nbsp;·&nbsp;
              {(visit.metrics?.tokens_out ?? 0).toLocaleString()} out
            </Text>
          )}
          {canRerunVisit && (
            <Flex
              as="button"
              align="center"
              gap={1}
              mt={1.5}
              fontSize="2xs"
              color="cyan.400"
              cursor="pointer"
              _hover={{ color: 'cyan.300' }}
              onClick={(e: React.MouseEvent) => { e.stopPropagation(); onRerun!(); }}
            >
              <RefreshCw size={10} />
              <Text>Re-run</Text>
            </Flex>
          )}
        </Box>
      )}
    </Box>
  );
};

// ── ParallelChip: compact status chip for a parallel node ────────────────────

const ParallelChip: React.FC<{
  visit: NodeVisit;
  isOpen: boolean;
  onToggle: () => void;
  onSelect?: () => void;
}> = ({ visit, isOpen, onToggle, onSelect }) => {
  const sc = statusColor(visit.status);
  return (
    <Flex
      align="center"
      gap={1.5}
      px={2}
      py={1}
      borderRadius="md"
      border="1px solid"
      borderColor={isOpen ? sc : `${sc}40`}
      bg={isOpen ? 'whiteAlpha.100' : 'transparent'}
      cursor="pointer"
      _hover={{ borderColor: sc, bg: 'whiteAlpha.50' }}
      transition="all 0.12s"
      onClick={() => { onToggle(); onSelect?.(); }}
      flexShrink={0}
    >
      <Box
        w="7px"
        h="7px"
        borderRadius="full"
        bg={visit.status === 'running' ? sc : 'transparent'}
        border="1.5px solid"
        borderColor={sc}
        boxShadow={visit.status === 'running' ? `0 0 6px ${sc}` : 'none'}
        flexShrink={0}
        sx={visit.status === 'running' ? {
          animation: 'chippulse 1.4s ease-in-out infinite',
          '@keyframes chippulse': { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.4 } },
        } : {}}
      />
      <Text fontSize="xs" color={visit.stale ? 'whiteAlpha.350' : 'whiteAlpha.850'} noOfLines={1} maxW="140px"
        textDecoration={visit.stale ? 'line-through' : 'none'}>
        {visit.label}
      </Text>
      {visit.metrics?.latency_ms != null && visit.metrics.latency_ms > 0 && (
        <Text fontSize="2xs" color="whiteAlpha.400" flexShrink={0}>
          {visit.metrics.latency_ms >= 1000
            ? `${(visit.metrics.latency_ms / 1000).toFixed(1)}s`
            : `${visit.metrics.latency_ms}ms`}
        </Text>
      )}
      {visit.status === 'completed' && <Text color="green.300" fontSize="xs" lineHeight={1} flexShrink={0}>✓</Text>}
      {visit.status === 'error' && <Text color="red.400" fontSize="xs" lineHeight={1} flexShrink={0}>✗</Text>}
    </Flex>
  );
};

// ── PipelineStepView ──────────────────────────────────────────────────────────

const PipelineStepView: React.FC<AgentGraphProps> = ({
  events,
  allEvents,
  runStatus,
  onNodeClick,
  onNodeRerun,
}) => {
  const [openVisits, setOpenVisits] = useState<Set<string>>(new Set());

  const visits = useMemo(
    () => buildVisits(events, allEvents ?? events, runStatus),
    [events, allEvents, runStatus],
  );

  // Auto-expand error visits
  useEffect(() => {
    const errorIds = visits.filter((v) => v.status === 'error').map((v) => v.id);
    if (errorIds.length === 0) return;
    setOpenVisits((prev) => {
      const next = new Set(prev);
      errorIds.forEach((id) => next.add(id));
      return next;
    });
  }, [visits]);

  const toggle = (id: string) =>
    setOpenVisits((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const scanVisits = visits.filter((v) => v.kind === 'scan');

  const tickerIds = useMemo(() => {
    const seen = new Set<string>();
    const order: string[] = [];
    visits
      .filter((v) => v.kind === 'ticker')
      .forEach((v) => {
        if (!seen.has(v.identifier)) {
          seen.add(v.identifier);
          order.push(v.identifier);
        }
      });
    return order;
  }, [visits]);

  const portfolioVisits = visits.filter((v) => v.kind === 'portfolio');

  // Group scan visits by SCAN_LEVEL so parallel nodes appear as chips
  const scanLevelGroups = useMemo(() => {
    const map = new Map<number, NodeVisit[]>();
    scanVisits.forEach((v) => {
      const level = SCAN_LEVELS[v.normalizedId] ?? 0;
      map.set(level, [...(map.get(level) ?? []), v]);
    });
    return [...map.entries()].sort((a, b) => a[0] - b[0]).map(([, vs]) => vs);
  }, [scanVisits]);

  // Group portfolio visits by PORTFOLIO_LEVEL (e.g. macro_summary + micro_summary)
  const portfolioLevelGroups = useMemo(() => {
    const map = new Map<number, NodeVisit[]>();
    portfolioVisits.forEach((v) => {
      const level = PORTFOLIO_LEVELS[v.normalizedId] ?? 0;
      map.set(level, [...(map.get(level) ?? []), v]);
    });
    return [...map.entries()].sort((a, b) => a[0] - b[0]).map(([, vs]) => vs);
  }, [portfolioVisits]);

  // Renders a section that groups nodes by level (scan / portfolio).
  // Single node at a level → VisitRow; multiple → horizontal ParallelChips.
  const renderGroupedSection = (
    groups: NodeVisit[][],
    label: string,
    color: string,
    allVisits: NodeVisit[],
  ) => {
    if (groups.length === 0) return null;
    const uniqueNodes = new Set(allVisits.map((v) => v.nodeKey));
    const completedUnique = new Set(
      allVisits.filter((v) => v.status === 'completed' && !v.stale).map((v) => v.nodeKey),
    );

    return (
      <Box>
        <Flex align="center" gap={2} mb={2}>
          <Box w="3px" h="14px" bg={color} borderRadius="full" flexShrink={0} />
          <Text fontSize="2xs" textTransform="uppercase" letterSpacing="wider" color={color} fontWeight="bold">
            {label}
          </Text>
          {uniqueNodes.size > 0 && (
            <Text fontSize="2xs" color="whiteAlpha.400" ml="auto">
              {completedUnique.size}/{uniqueNodes.size}
            </Text>
          )}
        </Flex>
        <Box ml="5px">
          {groups.map((groupVisits, gi) => {
            const isLastGroup = gi === groups.length - 1;

            if (groupVisits.length === 1) {
              const v = groupVisits[0];
              const rerunFn =
                onNodeRerun && canRerunNode(v.normalizedId, v.identifier)
                  ? () => onNodeRerun(v.identifier, v.rawNodeId)
                  : undefined;
              return (
                <VisitRow
                  key={v.id}
                  visit={v}
                  isLast={isLastGroup}
                  isOpen={openVisits.has(v.id)}
                  onToggle={() => toggle(v.id)}
                  onRerun={rerunFn}
                  onSelect={() => onNodeClick?.(v.rawNodeId, v.identifier)}
                />
              );
            }

            // Parallel level: horizontal chip row
            return (
              <Box key={gi} position="relative" pl="28px" pb={isLastGroup ? 0 : 2}>
                {/* Connector line to next level */}
                {!isLastGroup && (
                  <Box position="absolute" left="9px" top="30px" w="2px" bottom="0" bg="whiteAlpha.100" />
                )}
                {/* Left-side parallel bracket */}
                <Box
                  position="absolute"
                  left="4px"
                  top="4px"
                  w="2px"
                  h="22px"
                  bg={color}
                  borderRadius="full"
                  opacity={0.5}
                />
                <Flex gap={1.5} flexWrap="wrap" py={0.5}>
                  {groupVisits.map((v) => (
                    <ParallelChip
                      key={v.id}
                      visit={v}
                      isOpen={openVisits.has(v.id)}
                      onToggle={() => toggle(v.id)}
                      onSelect={() => onNodeClick?.(v.rawNodeId, v.identifier)}
                    />
                  ))}
                </Flex>
                {/* Expanded details for any open chip in this group */}
                {groupVisits.filter((v) => openVisits.has(v.id)).map((v) => {
                  const totalTok = (v.metrics?.tokens_in ?? 0) + (v.metrics?.tokens_out ?? 0);
                  const hasModel = Boolean(v.metrics?.model && v.metrics.model !== 'unknown' && v.metrics.model !== 'langgraph_node');
                  const rerunFn =
                    onNodeRerun && canRerunNode(v.normalizedId, v.identifier)
                      ? () => onNodeRerun(v.identifier, v.rawNodeId)
                      : undefined;
                  return (
                    <Box
                      key={v.id + '_exp'}
                      ml={1}
                      mb={1}
                      mt={1}
                      p={2}
                      borderRadius="md"
                      bg="whiteAlpha.50"
                      border="1px solid"
                      borderColor="whiteAlpha.100"
                    >
                      <Text fontSize="2xs" fontWeight="bold" color="whiteAlpha.600" mb={0.5}>{v.label}</Text>
                      {hasModel && (
                        <Text fontSize="2xs" fontFamily="mono" color="blue.300">{v.metrics!.model}</Text>
                      )}
                      {totalTok > 0 && (
                        <Text fontSize="2xs" color="whiteAlpha.400">
                          {(v.metrics?.tokens_in ?? 0).toLocaleString()} in · {(v.metrics?.tokens_out ?? 0).toLocaleString()} out
                        </Text>
                      )}
                      {rerunFn && (v.status === 'completed' || v.status === 'error') && (
                        <Flex
                          as="button"
                          align="center"
                          gap={1}
                          mt={1}
                          fontSize="2xs"
                          color="cyan.400"
                          cursor="pointer"
                          _hover={{ color: 'cyan.300' }}
                          onClick={(e: React.MouseEvent) => { e.stopPropagation(); rerunFn(); }}
                        >
                          <RefreshCw size={10} />
                          <Text>Re-run</Text>
                        </Flex>
                      )}
                    </Box>
                  );
                })}
              </Box>
            );
          })}
        </Box>
      </Box>
    );
  };

  // Single ticker section (vertical list — preserves debate revisit order)
  const renderSingleTickerSection = (id: string) => {
    const color = identifierColor(id);
    const tickerVisits = visits.filter((v) => v.kind === 'ticker' && v.identifier === id);
    if (tickerVisits.length === 0) return null;
    const uniqueNodes = new Set(tickerVisits.map((v) => v.nodeKey));
    const completedUnique = new Set(
      tickerVisits.filter((v) => v.status === 'completed' && !v.stale).map((v) => v.nodeKey),
    );
    return (
      <Box key={id}>
        <Flex align="center" gap={2} mb={2}>
          <Box w="3px" h="14px" bg={color} borderRadius="full" flexShrink={0} />
          <Text fontSize="2xs" textTransform="uppercase" letterSpacing="wider" color={color} fontWeight="bold">
            Pipeline · {id}
          </Text>
          <Text fontSize="2xs" color="whiteAlpha.400" ml="auto">
            {completedUnique.size}/{uniqueNodes.size}
          </Text>
        </Flex>
        <Box ml="5px">
          {tickerVisits.map((visit, i) => {
            const rerunFn =
              onNodeRerun && canRerunNode(visit.normalizedId, visit.identifier)
                ? () => onNodeRerun(visit.identifier, visit.rawNodeId)
                : undefined;
            return (
              <VisitRow
                key={visit.id}
                visit={visit}
                isLast={i === tickerVisits.length - 1}
                isOpen={openVisits.has(visit.id)}
                onToggle={() => toggle(visit.id)}
                onRerun={rerunFn}
                onSelect={() => onNodeClick?.(visit.rawNodeId, visit.identifier)}
              />
            );
          })}
        </Box>
      </Box>
    );
  };

  // Multiple ticker sections: side-by-side columns so parallel runs are obvious
  const renderParallelTickerColumns = () => (
    <Box>
      <Flex align="center" gap={2} mb={3}>
        <Box w="3px" h="14px" bg="whiteAlpha.300" borderRadius="full" flexShrink={0} />
        <Text fontSize="2xs" textTransform="uppercase" letterSpacing="wider" color="whiteAlpha.500" fontWeight="bold">
          Pipeline · {tickerIds.length} in parallel
        </Text>
      </Flex>
      <Flex
        gap={4}
        align="flex-start"
        overflowX="auto"
        pb={2}
        sx={{
          '&::-webkit-scrollbar': { height: '3px' },
          '&::-webkit-scrollbar-thumb': { background: 'rgba(255,255,255,0.15)' },
        }}
      >
        {tickerIds.map((id) => {
          const color = identifierColor(id);
          const tickerVisits = visits.filter((v) => v.kind === 'ticker' && v.identifier === id);
          const uniqueNodes = new Set(tickerVisits.map((v) => v.nodeKey));
          const completedUnique = new Set(
            tickerVisits.filter((v) => v.status === 'completed' && !v.stale).map((v) => v.nodeKey),
          );
          return (
            <Box key={id} flex="1" minW="170px" maxW="230px">
              {/* Column header */}
              <Flex align="center" gap={2} mb={2} pb={1.5} borderBottom="2px solid" borderColor={color}>
                <Text fontSize="sm" fontWeight="black" color={color} letterSpacing="wide">{id}</Text>
                <Text fontSize="2xs" color="whiteAlpha.400" ml="auto">
                  {completedUnique.size}/{uniqueNodes.size}
                </Text>
              </Flex>
              {/* Visits in temporal order — debate revisits show as repeated rows */}
              {tickerVisits.map((visit, i) => {
                const rerunFn =
                  onNodeRerun && canRerunNode(visit.normalizedId, visit.identifier)
                    ? () => onNodeRerun(visit.identifier, visit.rawNodeId)
                    : undefined;
                return (
                  <VisitRow
                    key={visit.id}
                    visit={visit}
                    isLast={i === tickerVisits.length - 1}
                    isOpen={openVisits.has(visit.id)}
                    onToggle={() => toggle(visit.id)}
                    onRerun={rerunFn}
                    onSelect={() => onNodeClick?.(visit.rawNodeId, visit.identifier)}
                  />
                );
              })}
            </Box>
          );
        })}
      </Flex>
    </Box>
  );

  const isEmpty =
    scanVisits.length === 0 && tickerIds.length === 0 && portfolioVisits.length === 0;

  return (
    <Box
      h="100%"
      w="100%"
      bg="#020617"
      overflowY="auto"
      px={5}
      py={4}
      sx={{
        '&::-webkit-scrollbar': { width: '4px' },
        '&::-webkit-scrollbar-track': { background: 'transparent' },
        '&::-webkit-scrollbar-thumb': { background: 'rgba(255,255,255,0.15)' },
      }}
    >
      <Flex direction="column" gap={6}>
        {/* Scan: parallel nodes at same level shown as horizontal chips */}
        {renderGroupedSection(scanLevelGroups, 'Scan', '#4fd1c5', scanVisits)}

        {/* Ticker pipelines: columns when parallel, vertical list when single */}
        {tickerIds.length === 1
          ? renderSingleTickerSection(tickerIds[0])
          : tickerIds.length > 1
            ? renderParallelTickerColumns()
            : null}

        {/* Portfolio: parallel nodes (e.g. macro + micro summary) shown as chips */}
        {renderGroupedSection(portfolioLevelGroups, 'Portfolio', '#9f7aea', portfolioVisits)}

        {isEmpty && (
          <Flex h="280px" align="center" justify="center" direction="column" gap={3} opacity={0.25}>
            <Settings size={40} />
            <Text fontSize="sm">Awaiting agent events…</Text>
          </Flex>
        )}
      </Flex>
    </Box>
  );
};

// ── ReactFlow graph helpers ───────────────────────────────────────────────────

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

  const maxScanLevel = scanRecords.length > 0
    ? Math.max(...scanRecords.map((r) => SCAN_LEVELS[r.normalizedId] ?? 0))
    : -1;

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
          data: nodeData(record),
        });
      });
  }

  return { nodes, edges };
}

// ── AgentGraph: top-level component with Steps/Graph toggle ──────────────────

export const AgentGraph: React.FC<AgentGraphProps> = ({ events, allEvents, runStatus, onNodeClick, onNodeRerun }) => {
  const [viewMode, setViewMode] = useState<'steps' | 'graph'>('steps');
  const [layoutDir, setLayoutDir] = useState<'TB' | 'LR'>('TB');
  const [positionOverrides, setPositionOverrides] = useState<PositionOverrides>({});
  const rfInstanceRef = useRef<ReactFlowInstance | null>(null);

  const { nodes: layoutNodes, edges } = useMemo(
    () => buildGraph(events, allEvents ?? events, runStatus, onNodeRerun, layoutDir),
    [events, allEvents, runStatus, onNodeRerun, layoutDir],
  );

  useEffect(() => {
    setPositionOverrides({});
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
        if (change.type === 'remove') { delete next[change.id]; return; }
        if (change.type === 'position') {
          const updated = updatedNodes.find((node) => node.id === change.id);
          if (updated) next[change.id] = updated.position;
        }
      });
      return next;
    });
  }, [nodes]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    onNodeClick?.(node.data.node_id as string, node.data.identifier as string);
  }, [onNodeClick]);

  return (
    <Flex h="100%" w="100%" bg="#020617" direction="column">
      {/* ── Header bar: view toggle + graph layout button ── */}
      <Flex
        flexShrink={0}
        align="center"
        justify="space-between"
        px={3}
        h="40px"
        borderBottom="1px solid"
        borderColor="rgba(255,255,255,0.08)"
        bg="#0a1628"
      >
        {/* Left: section label */}
        <Text fontSize="2xs" textTransform="uppercase" letterSpacing="widest" color="whiteAlpha.300" fontWeight="bold">
          {viewMode === 'steps' ? 'Agent Steps' : 'Agent Graph'}
        </Text>

        <Flex align="center" gap={2}>
          {/* Layout direction button — only visible in graph mode */}
          {viewMode === 'graph' && (
            <Box
              as="button"
              onClick={() => setLayoutDir((d: 'TB' | 'LR') => (d === 'TB' ? 'LR' : 'TB'))}
              bg="rgba(255,255,255,0.06)"
              border="1px solid"
              borderColor="rgba(255,255,255,0.12)"
              color="whiteAlpha.600"
              fontSize="2xs"
              fontWeight="semibold"
              px={2}
              py={0.5}
              borderRadius="sm"
              cursor="pointer"
              _hover={{ borderColor: '#4fd1c5', color: '#4fd1c5' }}
              transition="all 0.15s"
            >
              {layoutDir === 'TB' ? '⇔ H' : '⇕ V'}
            </Box>
          )}

          {/* Steps / Graph toggle pill */}
          <Flex
            bg="rgba(255,255,255,0.05)"
            border="1px solid"
            borderColor="rgba(255,255,255,0.12)"
            borderRadius="md"
            overflow="hidden"
          >
            {(['steps', 'graph'] as const).map((mode) => (
              <Box
                key={mode}
                as="button"
                px={3}
                py={1.5}
                fontSize="xs"
                fontWeight="semibold"
                bg={viewMode === mode ? 'rgba(79,209,197,0.15)' : 'transparent'}
                color={viewMode === mode ? '#4fd1c5' : 'rgba(255,255,255,0.4)'}
                cursor="pointer"
                borderRight={mode === 'steps' ? '1px solid rgba(255,255,255,0.08)' : undefined}
                _hover={{ color: viewMode === mode ? '#4fd1c5' : 'white' }}
                transition="all 0.15s"
                onClick={() => setViewMode(mode)}
              >
                {mode === 'steps' ? '≡ Steps' : '⊡ Graph'}
              </Box>
            ))}
          </Flex>
        </Flex>
      </Flex>

      {/* ── Content area fills remaining height ── */}
      <Box flex={1} minH={0} position="relative" overflow="hidden">
        {viewMode === 'steps' ? (
          <PipelineStepView
            events={events}
            allEvents={allEvents}
            runStatus={runStatus}
            onNodeClick={onNodeClick}
            onNodeRerun={onNodeRerun}
          />
        ) : (
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
          </ReactFlow>
        )}
      </Box>
    </Flex>
  );
};
