import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { 
  Box, 
  Flex, 
  VStack, 
  HStack, 
  Text, 
  IconButton, 
  Button, 
  Input,
  Checkbox,
  useDisclosure,
  Drawer,
  DrawerOverlay,
  DrawerContent,
  DrawerHeader,
  DrawerBody,
  DrawerCloseButton,
  Divider,
  Tag,
  Code,
  Badge,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Tooltip,
  Collapse,
  useToast,
  Popover,
  PopoverTrigger,
  PopoverContent,
  PopoverHeader,
  PopoverBody,
  PopoverCloseButton,
} from '@chakra-ui/react';
import { LayoutDashboard, Wallet, Settings, Terminal as TerminalIcon, ChevronRight, Eye, Search, BarChart3, Bot, ChevronDown, ChevronUp, FlaskConical, Trash2, History, Loader2 } from 'lucide-react';
import { MetricHeader } from './components/MetricHeader';
import { AgentGraph } from './components/AgentGraph';
import { PortfolioViewer } from './components/PortfolioViewer';
import { useAgentStream, AgentEvent } from './hooks/useAgentStream';
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8088/api';

// ─── Run type definitions with required parameters ────────────────────
type RunType = 'scan' | 'pipeline' | 'portfolio' | 'auto' | 'mock';

/** Mock-specific sub-type. */
type MockType = 'pipeline' | 'scan' | 'auto';

interface RunParams {
  date: string;
  ticker: string;
  portfolio_id: string;
  max_auto_tickers: string;
  mock_type: MockType;
  speed: string;
  force: boolean;
}

const RUN_TYPE_LABELS: Record<RunType, string> = {
  scan: 'Scan',
  pipeline: 'Pipeline',
  portfolio: 'Portfolio',
  auto: 'Auto',
  mock: 'Mock',
};

/** Which params each run type needs. */
const REQUIRED_PARAMS: Record<RunType, (keyof RunParams)[]> = {
  scan: ['date'],
  pipeline: ['ticker', 'date'],
  portfolio: ['date', 'portfolio_id'],
  auto: ['date', 'portfolio_id'],
  mock: [],
};

/** Return the colour token for a given event type. */
const eventColor = (type: AgentEvent['type'], status?: AgentEvent['status']): string => {
  // Error events always show in red
  if (status === 'error') return 'red.400';
  // Graceful skips show in orange/yellow
  if (status === 'graceful_skip') return 'orange.300';
  switch (type) {
    case 'tool':        return 'purple.400';
    case 'tool_result': return 'purple.300';
    case 'result':      return 'green.400';
    case 'log':         return 'yellow.300';
    default:            return 'cyan.400';
  }
};

/** Return a short label badge for the event type. */
const eventLabel = (type: AgentEvent['type'], status?: AgentEvent['status']): string => {
  if (status === 'error') return '❌';
  if (status === 'graceful_skip') return '⚠️';
  switch (type) {
    case 'thought':     return '💭';
    case 'tool':        return '🔧';
    case 'tool_result': return '✅🔧';
    case 'result':      return '✅';
    case 'log':         return 'ℹ️';
    default:            return '●';
  }
};

/** Short summary for terminal — no inline prompts, just agent + type. */
const eventSummary = (evt: AgentEvent): string => {
  const svc = evt.service ? ` [${evt.service}]` : '';
  switch (evt.type) {
    case 'thought':     return `Thinking… (${evt.metrics?.model || 'LLM'})`;
    case 'tool': {
      if (evt.message.startsWith('✓')) return 'Tool result received';
      const toolName = evt.message.replace(/^▶ Tool: /, '').split(' | ')[0];
      return `Tool call: ${toolName}${svc}`;
    }
    case 'tool_result': {
      const resultToolName = evt.message.replace(/^[✓✗⚠] Tool result: /, '').split(' | ')[0];
      if (evt.status === 'error') return `Tool error: ${resultToolName}${svc}`;
      if (evt.status === 'graceful_skip') return `Tool skipped: ${resultToolName}${svc}`;
      return `Tool done: ${resultToolName}${svc}`;
    }
    case 'result':      return 'Completed';
    case 'log':         return evt.message;
    default:            return evt.type;
  }
};

// ─── Full Event Detail Modal ─────────────────────────────────────────
const EventDetailModal: React.FC<{ event: AgentEvent | null; isOpen: boolean; onClose: () => void }> = ({ event, isOpen, onClose }) => {
  if (!event) return null;

  const headerBadgeColor = event.status === 'error' ? 'red'
    : event.status === 'graceful_skip' ? 'orange'
    : event.type === 'result' ? 'green'
    : event.type === 'tool' || event.type === 'tool_result' ? 'purple'
    : 'cyan';

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="4xl" scrollBehavior="inside">
      <ModalOverlay backdropFilter="blur(6px)" />
      <ModalContent bg="slate.900" color="white" maxH="85vh" border="1px solid" borderColor="whiteAlpha.200">
        <ModalCloseButton />
        <ModalHeader borderBottomWidth="1px" borderColor="whiteAlpha.100">
          <HStack>
            <Badge colorScheme={headerBadgeColor} fontSize="sm">
              {event.type.toUpperCase()}
            </Badge>
            <Badge variant="outline" fontSize="sm">{event.agent}</Badge>
            {event.status === 'error' && <Badge colorScheme="red" variant="solid" fontSize="sm">ERROR</Badge>}
            {event.status === 'graceful_skip' && <Badge colorScheme="orange" variant="solid" fontSize="sm">GRACEFUL SKIP</Badge>}
            {event.service && <Badge colorScheme="teal" fontSize="sm">{event.service}</Badge>}
            <Text fontSize="sm" color="whiteAlpha.400" fontWeight="normal">{event.timestamp}</Text>
          </HStack>
        </ModalHeader>
        <ModalBody py={4}>
          <Tabs variant="soft-rounded" colorScheme="cyan" size="sm">
            <TabList mb={4}>
              {event.prompt && <Tab>Prompt / Request</Tab>}
              {(event.response || (event.type === 'result' && event.message)) && <Tab>Response</Tab>}
              {event.error && <Tab color="red.400">Error</Tab>}
              <Tab>Summary</Tab>
              {event.metrics && <Tab>Metrics</Tab>}
            </TabList>
            <TabPanels>
              {event.prompt && (
                <TabPanel p={0}>
                  <Box bg="blackAlpha.500" p={4} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100" maxH="60vh" overflowY="auto">
                    <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
                      {event.prompt}
                    </Text>
                  </Box>
                </TabPanel>
              )}
              {(event.response || (event.type === 'result' && event.message)) && (
                <TabPanel p={0}>
                  <Box bg="blackAlpha.500" p={4} borderRadius="md" border="1px solid" borderColor={event.status === 'error' ? 'red.700' : 'whiteAlpha.100'} maxH="60vh" overflowY="auto">
                    <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color={event.status === 'error' ? 'red.200' : 'whiteAlpha.900'}>
                      {event.response || event.message}
                    </Text>
                  </Box>
                </TabPanel>
              )}
              {event.error && (
                <TabPanel p={0}>
                  <Box bg="red.900" p={4} borderRadius="md" border="1px solid" borderColor="red.600" maxH="60vh" overflowY="auto">
                    <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="red.200">
                      {event.error}
                    </Text>
                  </Box>
                </TabPanel>
              )}
              <TabPanel p={0}>
                <Box bg="blackAlpha.500" p={4} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
                  <Text fontSize="sm" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
                    {event.message}
                  </Text>
                </Box>
              </TabPanel>
              {event.metrics && (
                <TabPanel p={0}>
                  <VStack align="stretch" spacing={3}>
                    {event.metrics.model && event.metrics.model !== 'unknown' && (
                      <HStack><Text fontSize="sm" color="whiteAlpha.600" minW="80px">Model:</Text><Code colorScheme="blue" fontSize="sm">{event.metrics.model}</Code></HStack>
                    )}
                    {event.service && (
                      <HStack><Text fontSize="sm" color="whiteAlpha.600" minW="80px">Service:</Text><Code colorScheme="teal" fontSize="sm">{event.service}</Code></HStack>
                    )}
                    {event.metrics.tokens_in != null && event.metrics.tokens_in > 0 && (
                      <HStack><Text fontSize="sm" color="whiteAlpha.600" minW="80px">Tokens In:</Text><Code>{event.metrics.tokens_in}</Code></HStack>
                    )}
                    {event.metrics.tokens_out != null && event.metrics.tokens_out > 0 && (
                      <HStack><Text fontSize="sm" color="whiteAlpha.600" minW="80px">Tokens Out:</Text><Code>{event.metrics.tokens_out}</Code></HStack>
                    )}
                    {event.metrics.latency_ms != null && event.metrics.latency_ms > 0 && (
                      <HStack><Text fontSize="sm" color="whiteAlpha.600" minW="80px">Latency:</Text><Code>{event.metrics.latency_ms}ms</Code></HStack>
                    )}
                    {event.node_id && (
                      <HStack><Text fontSize="sm" color="whiteAlpha.600" minW="80px">Node ID:</Text><Code fontSize="xs">{event.node_id}</Code></HStack>
                    )}
                  </VStack>
                </TabPanel>
              )}
            </TabPanels>
          </Tabs>
        </ModalBody>
      </ModalContent>
    </Modal>
  );
};

// ─── Detail card for a single event in the drawer ─────────────────────
const EventDetail: React.FC<{ event: AgentEvent; onOpenModal?: (evt: AgentEvent) => void }> = ({ event, onOpenModal }) => {
  const badgeColor = event.status === 'error' ? 'red'
    : event.status === 'graceful_skip' ? 'orange'
    : event.type === 'result' ? 'green'
    : event.type === 'tool' || event.type === 'tool_result' ? 'purple'
    : 'cyan';

  return (
  <VStack align="stretch" spacing={4}>
    <HStack>
      <Badge colorScheme={badgeColor}>{event.type.toUpperCase()}</Badge>
      <Badge variant="outline">{event.agent}</Badge>
      {event.status === 'error' && <Badge colorScheme="red" variant="solid">ERROR</Badge>}
      {event.status === 'graceful_skip' && <Badge colorScheme="orange" variant="solid">GRACEFUL SKIP</Badge>}
      <Text fontSize="xs" color="whiteAlpha.400">{event.timestamp}</Text>
      {onOpenModal && (
        <Button size="xs" variant="ghost" colorScheme="cyan" ml="auto" onClick={() => onOpenModal(event)}>
          Full Detail →
        </Button>
      )}
    </HStack>

    {/* Service info for tool events */}
    {event.service && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Service</Text>
        <Code colorScheme="teal" fontSize="sm">{event.service}</Code>
      </Box>
    )}

    {event.metrics?.model && event.metrics.model !== 'unknown' && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Model</Text>
        <Code colorScheme="blue" fontSize="sm">{event.metrics.model}</Code>
      </Box>
    )}

    {event.metrics && (event.metrics.tokens_in != null || event.metrics.latency_ms != null) && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Metrics</Text>
        <HStack spacing={4} fontSize="sm">
          {event.metrics.tokens_in != null && event.metrics.tokens_in > 0 && (
            <Text>Tokens: <Code>{event.metrics.tokens_in}</Code> in / <Code>{event.metrics.tokens_out}</Code> out</Text>
          )}
          {event.metrics.latency_ms != null && event.metrics.latency_ms > 0 && (
            <Text>Latency: <Code>{event.metrics.latency_ms}ms</Code></Text>
          )}
        </HStack>
      </Box>
    )}

    {/* Error display */}
    {event.error && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="red.400" mb={1}>Error</Text>
        <Box bg="red.900" p={3} borderRadius="md" border="1px solid" borderColor="red.600" maxH="200px" overflowY="auto">
          <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="red.200">
            {event.error}
          </Text>
        </Box>
      </Box>
    )}

    {/* Show prompt if available */}
    {event.prompt && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Request / Prompt</Text>
        <Box bg="blackAlpha.500" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100" maxH="200px" overflowY="auto">
          <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
            {event.prompt.length > 1000 ? event.prompt.substring(0, 1000) + '…' : event.prompt}
          </Text>
        </Box>
      </Box>
    )}

    {/* Show response if available (result events) */}
    {event.response && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Response</Text>
        <Box bg="blackAlpha.500" p={3} borderRadius="md" border="1px solid" borderColor={event.status === 'error' ? 'red.700' : 'green.900'} maxH="200px" overflowY="auto">
          <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color={event.status === 'error' ? 'red.200' : 'whiteAlpha.900'}>
            {event.response.length > 1000 ? event.response.substring(0, 1000) + '…' : event.response}
          </Text>
        </Box>
      </Box>
    )}

    {/* Fallback: show message if no prompt/response */}
    {!event.prompt && !event.response && !event.error && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Message</Text>
        <Box bg="blackAlpha.500" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100" maxH="300px" overflowY="auto">
          <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
            {event.message}
          </Text>
        </Box>
      </Box>
    )}

    {event.node_id && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Node ID</Text>
        <Code fontSize="xs">{event.node_id}</Code>
      </Box>
    )}
  </VStack>
  );
};

// ─── Detail drawer showing all events for a given graph node ──────────
const NodeEventsDetail: React.FC<{ nodeId: string; identifier?: string | null; events: AgentEvent[]; onOpenModal: (evt: AgentEvent) => void }> = ({ nodeId, identifier, events, onOpenModal }) => {
  const nodeEvents = useMemo(
    () => events.filter((e) =>
      e.node_id === nodeId &&
      (!identifier || e.identifier === identifier)
    ),
    [events, nodeId, identifier],
  );

  if (nodeEvents.length === 0) {
    return <Text color="whiteAlpha.500" fontSize="sm">No events recorded for this node yet.</Text>;
  }

  return (
    <VStack align="stretch" spacing={4}>
      {nodeEvents.map((evt) => (
        <Box key={evt.id} bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
          <EventDetail event={evt} onOpenModal={onOpenModal} />
        </Box>
      ))}
    </VStack>
  );
};

// ─── Sidebar page type ────────────────────────────────────────────────
type Page = 'dashboard' | 'portfolio';

export const Dashboard: React.FC = () => {
  const [activePage, setActivePage] = useState<Page>('dashboard');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeRunType, setActiveRunType] = useState<RunType | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const { events, status, clearEvents } = useAgentStream(activeRunId);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();

  // Event detail modal state
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const [modalEvent, setModalEvent] = useState<AgentEvent | null>(null);

  // What's shown in the drawer: either a single event or all events for a node
  const [drawerMode, setDrawerMode] = useState<'event' | 'node'>('event');
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeIdentifier, setSelectedNodeIdentifier] = useState<string | null>(null);

  // Parameter inputs
  const [showParams, setShowParams] = useState(false);
  const [params, setParams] = useState<RunParams>({
    date: new Date().toISOString().split('T')[0],
    ticker: 'AAPL',
    portfolio_id: 'main_portfolio',
    max_auto_tickers: '',
    mock_type: 'pipeline',
    speed: '3',
    force: false,
  });

  // Auto-scroll the terminal to the bottom as new events arrive
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  // Clear activeRunType when run completes
  useEffect(() => {
    if (status === 'completed' || status === 'error') {
      setActiveRunType(null);
    }
  }, [status]);

  const isRunning = isTriggering || status === 'streaming' || status === 'connecting';

  const startRun = async (type: RunType, overrideParams?: Partial<RunParams>) => {
    if (isRunning) return;

    const effectiveParams = { ...params, ...overrideParams };

    // Validate required params
    const required = REQUIRED_PARAMS[type];
    const missing = required.filter((k) => { const v = effectiveParams[k]; return typeof v === 'string' ? !v.trim() : !v; });
    if (missing.length > 0) {
      toast({
        title: `Missing required fields for ${RUN_TYPE_LABELS[type]}`,
        description: `Please fill in: ${missing.join(', ')}`,
        status: 'warning',
        duration: 3000,
        isClosable: true,
        position: 'top',
      });
      setShowParams(true);
      return;
    }

    setIsTriggering(true);
    setActiveRunType(type);
    try {
      clearEvents();
      // For mock auto runs, parse comma-separated tickers into an array
      const mockTickers = effectiveParams.mock_type === 'auto'
        ? effectiveParams.ticker.split(',').map((t) => t.trim().toUpperCase()).filter(Boolean)
        : undefined;
      const body = type === 'mock'
        ? {
            mock_type: effectiveParams.mock_type,
            ticker: effectiveParams.ticker.split(',')[0].trim().toUpperCase(),
            ...(mockTickers && mockTickers.length > 1 ? { tickers: mockTickers } : {}),
            date: effectiveParams.date,
            speed: parseFloat(effectiveParams.speed) || 3,
          }
        : {
            portfolio_id: effectiveParams.portfolio_id,
            date: effectiveParams.date,
            ticker: effectiveParams.ticker,
            force: effectiveParams.force,
            ...(effectiveParams.max_auto_tickers ? { max_tickers: parseInt(effectiveParams.max_auto_tickers, 10) } : {}),
          };
      const res = await axios.post(`${API_BASE}/run/${type}`, body);
      setActiveRunId(res.data.run_id);
    } catch (err) {
      console.error("Failed to start run:", err);
      setActiveRunType(null);
    } finally {
      setIsTriggering(false);
    }
  };

  /** Re-run triggered from a graph node's Re-run button. */
  const handleNodeRerun = useCallback((identifier: string, nodeId: string) => {
    // If we have an active loaded run and the node is in NODE_TO_PHASE, use phase-level rerun
    if (activeRunId && nodeId && identifier && identifier !== 'MARKET' && identifier !== '') {
      triggerNodeRerun(activeRunId, identifier, nodeId);
      return;
    }
    if (identifier === 'MARKET' || identifier === '') {
      startRun('scan');
    } else {
      startRun('pipeline', { ticker: identifier });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, params, activeRunId]);

  const resetPortfolioStage = async () => {
    if (!params.date || !params.portfolio_id) {
      toast({ title: 'Date and Portfolio ID are required', status: 'warning', duration: 3000, isClosable: true, position: 'top' });
      setShowParams(true);
      return;
    }
    try {
      const res = await axios.delete(`${API_BASE}/run/portfolio-stage`, { data: { date: params.date, portfolio_id: params.portfolio_id } });
      const deleted: string[] = res.data.deleted;
      toast({
        title: deleted.length ? `Cleared: ${deleted.join(', ')}` : 'Nothing to clear — no decision files found',
        status: deleted.length ? 'success' : 'info',
        duration: 4000,
        isClosable: true,
        position: 'top',
      });
    } catch (err) {
      toast({ title: 'Failed to reset portfolio stage', status: 'error', duration: 3000, isClosable: true, position: 'top' });
    }
  };

  // ─── History panel state ───────────────────────────────────────────
  const [historyRuns, setHistoryRuns] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/run/`);
      const sorted = (res.data as any[]).sort((a: any, b: any) => (b.created_at || 0) - (a.created_at || 0));
      setHistoryRuns(sorted);
    } catch (err) {
      console.error('Failed to load run history', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadRun = (run: any) => {
    clearEvents();
    // Pre-fill params from run
    if (run.params) {
      setParams((p) => ({
        ...p,
        date: run.params.date || p.date,
        ticker: run.params.ticker || p.ticker,
        portfolio_id: run.params.portfolio_id || p.portfolio_id,
      }));
    }
    setActiveRunId(null);
    setTimeout(() => setActiveRunId(run.id), 0);
  };

  /** Trigger a phase-level re-run for a specific node on the active run. */
  const triggerNodeRerun = async (runId: string, identifier: string, nodeId: string) => {
    try {
      const res = await axios.post(`${API_BASE}/run/rerun-node`, {
        run_id: runId,
        node_id: nodeId,
        identifier,
        date: params.date,
        portfolio_id: params.portfolio_id,
      });
      // Force WebSocket reconnect to stream new events
      setActiveRunId(null);
      setTimeout(() => setActiveRunId(res.data.run_id), 0);
      toast({
        title: `Re-running ${res.data.phase} phase for ${identifier}`,
        status: 'info',
        duration: 3000,
        isClosable: true,
        position: 'top',
      });
    } catch (err: any) {
      toast({
        title: 'Re-run failed',
        description: err?.response?.data?.detail || String(err),
        status: 'error',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });
    }
  };

  /** Open the full-screen event detail modal */
  const openModal = useCallback((evt: AgentEvent) => {
    setModalEvent(evt);
    onModalOpen();
  }, [onModalOpen]);

  /** Open the drawer for a single event (terminal click). */
  const openEventDetail = useCallback((evt: AgentEvent) => {
    setDrawerMode('event');
    setSelectedEvent(evt);
    setSelectedNodeId(null);
    onOpen();
  }, [onOpen]);

  /** Open the drawer showing all events for a graph node (node click). */
  const openNodeDetail = useCallback((nodeId: string, identifier?: string) => {
    setDrawerMode('node');
    setSelectedNodeId(nodeId);
    setSelectedNodeIdentifier(identifier || null);
    setSelectedEvent(null);
    onOpen();
  }, [onOpen]);

  // Derive a readable drawer title
  const drawerTitle = drawerMode === 'event'
    ? `Event: ${selectedEvent?.agent ?? ''} — ${selectedEvent?.type ?? ''}`
    : `Node: ${selectedNodeId ?? ''}${selectedNodeIdentifier ? ` · ${selectedNodeIdentifier}` : ''}`;

  return (
    <Flex h="100vh" bg="slate.950" color="white" overflow="hidden">
      {/* Sidebar */}
      <VStack w="64px" bg="slate.900" borderRight="1px solid" borderColor="whiteAlpha.100" py={4} spacing={6}>
        <Box mb={4}><Text fontWeight="black" color="cyan.400" fontSize="xl">A</Text></Box>
        <Tooltip label="Dashboard" placement="right">
          <IconButton
            aria-label="Dashboard"
            icon={<LayoutDashboard size={20} />}
            variant="ghost"
            color={activePage === 'dashboard' ? 'cyan.400' : 'whiteAlpha.600'}
            bg={activePage === 'dashboard' ? 'whiteAlpha.100' : 'transparent'}
            _hover={{ bg: "whiteAlpha.100" }}
            onClick={() => setActivePage('dashboard')}
          />
        </Tooltip>
        <Tooltip label="Portfolio" placement="right">
          <IconButton
            aria-label="Portfolio"
            icon={<Wallet size={20} />}
            variant="ghost"
            color={activePage === 'portfolio' ? 'cyan.400' : 'whiteAlpha.600'}
            bg={activePage === 'portfolio' ? 'whiteAlpha.100' : 'transparent'}
            _hover={{ bg: "whiteAlpha.100" }}
            onClick={() => setActivePage('portfolio')}
          />
        </Tooltip>
        <IconButton aria-label="Settings" icon={<Settings size={20} />} variant="ghost" color="whiteAlpha.600" _hover={{ bg: "whiteAlpha.100" }} />
      </VStack>

      {/* ─── Portfolio Page ────────────────────────────────────────── */}
      {activePage === 'portfolio' && (
        <Box flex="1">
          <PortfolioViewer defaultPortfolioId={params.portfolio_id} />
        </Box>
      )}

      {/* ─── Dashboard Page ────────────────────────────────────────── */}
      {activePage === 'dashboard' && (
        <Flex flex="1" direction="column">
          {/* Top Metric Header */}
          <MetricHeader portfolioId={params.portfolio_id} />

          {/* Dashboard Body */}
          <Flex flex="1" overflow="hidden">
            {/* Left Side: Graph Area */}
            <Box flex="1" position="relative" borderRight="1px solid" borderColor="whiteAlpha.100">
               <AgentGraph events={events} onNodeClick={openNodeDetail} onNodeRerun={handleNodeRerun} />
               
               {/* Floating Control Panel */}
               <VStack position="absolute" top={4} left={4} spacing={2} align="stretch">
                 {/* Run buttons row */}
                 <HStack bg="blackAlpha.800" p={2} borderRadius="lg" backdropFilter="blur(10px)" border="1px solid" borderColor="whiteAlpha.200" spacing={2}>
                    {(['scan', 'pipeline', 'portfolio', 'auto'] as RunType[]).map((type) => {
                      const isThisRunning = isRunning && activeRunType === type;
                      const isOtherRunning = isRunning && activeRunType !== type;
                      const icons: Record<string, React.ReactElement> = {
                        scan: <Search size={14} />,
                        pipeline: <BarChart3 size={14} />,
                        portfolio: <Wallet size={14} />,
                        auto: <Bot size={14} />,
                      };
                      const colors: Record<string, string> = {
                        scan: 'cyan',
                        pipeline: 'blue',
                        portfolio: 'purple',
                        auto: 'green',
                      };
                      return (
                        <Button
                          key={type}
                          size="sm"
                          leftIcon={icons[type]}
                          colorScheme={colors[type]}
                          variant="solid"
                          onClick={() => startRun(type)}
                          isLoading={isThisRunning}
                          loadingText="Running…"
                          isDisabled={isOtherRunning}
                        >
                          {RUN_TYPE_LABELS[type]}
                        </Button>
                      );
                    })}
                    <Divider orientation="vertical" h="20px" />
                    {/* Mock run button — no LLM calls */}
                    <Tooltip label="Stream scripted events — no LLM calls" hasArrow placement="bottom">
                      <Button
                        size="sm"
                        leftIcon={<FlaskConical size={14} />}
                        colorScheme="orange"
                        variant="outline"
                        onClick={() => startRun('mock')}
                        isLoading={isRunning && activeRunType === 'mock'}
                        loadingText="Mocking…"
                        isDisabled={isRunning && activeRunType !== 'mock'}
                      >
                        Mock
                      </Button>
                    </Tooltip>
                    <Tooltip label="Clear PM decision & execution result for this date/portfolio, then re-run Auto to start Phase 3 fresh">
                      <Button
                        size="sm"
                        leftIcon={<Trash2 size={14} />}
                        colorScheme="red"
                        variant="outline"
                        onClick={resetPortfolioStage}
                        isDisabled={isRunning}
                      >
                        Reset Decision
                      </Button>
                    </Tooltip>
                    <Divider orientation="vertical" h="20px" />
                    <Tag size="sm" colorScheme={status === 'streaming' ? 'green' : status === 'completed' ? 'blue' : status === 'error' ? 'red' : 'gray'}>
                      {status.toUpperCase()}
                    </Tag>
                    <Popover placement="bottom-end" onOpen={loadHistory}>
                      <PopoverTrigger>
                        <IconButton
                          aria-label="Run history"
                          icon={<History size={14} />}
                          size="xs"
                          variant="ghost"
                          color="whiteAlpha.600"
                        />
                      </PopoverTrigger>
                      <PopoverContent bg="slate.900" borderColor="whiteAlpha.200" maxH="400px" overflowY="auto" w="360px">
                        <PopoverCloseButton />
                        <PopoverHeader borderColor="whiteAlpha.100" fontSize="sm" fontWeight="bold">Run History</PopoverHeader>
                        <PopoverBody p={2}>
                          {historyLoading && <Flex justify="center" py={4}><Loader2 size={20} /></Flex>}
                          {!historyLoading && historyRuns.length === 0 && (
                            <Text fontSize="sm" color="whiteAlpha.400" textAlign="center" py={4}>No runs found</Text>
                          )}
                          <VStack spacing={1} align="stretch">
                            {historyRuns.map((r) => (
                              <Flex
                                key={r.id}
                                p={2}
                                borderRadius="md"
                                _hover={{ bg: 'whiteAlpha.100' }}
                                cursor="pointer"
                                onClick={() => loadRun(r)}
                                align="center"
                                gap={2}
                              >
                                <Badge colorScheme={r.type === 'auto' ? 'green' : r.type === 'scan' ? 'cyan' : r.type === 'pipeline' ? 'blue' : 'purple'} fontSize="2xs">
                                  {r.type}
                                </Badge>
                                <Text fontSize="xs" color="whiteAlpha.700">{(r.params || {}).date || '—'}</Text>
                                <Tag size="sm" colorScheme={r.status === 'completed' ? 'blue' : r.status === 'running' ? 'green' : r.status === 'failed' ? 'red' : 'gray'} ml="auto">
                                  {r.status}
                                </Tag>
                                <Text fontSize="2xs" color="whiteAlpha.400">
                                  {r.created_at ? new Date(r.created_at * 1000).toLocaleTimeString() : ''}
                                </Text>
                              </Flex>
                            ))}
                          </VStack>
                        </PopoverBody>
                      </PopoverContent>
                    </Popover>
                    <IconButton
                      aria-label="Toggle params"
                      icon={showParams ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      size="xs"
                      variant="ghost"
                      color="whiteAlpha.600"
                      onClick={() => setShowParams(!showParams)}
                    />
                 </HStack>

                 {/* Collapsible parameter inputs */}
                 <Collapse in={showParams} animateOpacity>
                   <Box bg="blackAlpha.800" p={3} borderRadius="lg" backdropFilter="blur(10px)" border="1px solid" borderColor="whiteAlpha.200">
                     <VStack spacing={2} align="stretch">
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Date:</Text>
                         <Input
                           size="xs"
                           type="date"
                           bg="whiteAlpha.100"
                           borderColor="whiteAlpha.200"
                           value={params.date}
                           onChange={(e) => setParams((p) => ({ ...p, date: e.target.value }))}
                         />
                       </HStack>
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Ticker:</Text>
                         <Input
                           size="xs"
                           placeholder={params.mock_type === 'auto' ? 'AAPL,NVDA,TSLA' : 'AAPL'}
                           bg="whiteAlpha.100"
                           borderColor="whiteAlpha.200"
                           value={params.ticker}
                           onChange={(e) => setParams((p) => ({ ...p, ticker: e.target.value.toUpperCase() }))}
                         />
                       </HStack>
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Portfolio:</Text>
                         <Input
                           size="xs"
                           placeholder="main_portfolio"
                           bg="whiteAlpha.100"
                           borderColor="whiteAlpha.200"
                           value={params.portfolio_id}
                           onChange={(e) => setParams((p) => ({ ...p, portfolio_id: e.target.value }))}
                         />
                       </HStack>
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Max Tickers</Text>
                         <Input size="xs" type="number" min={1} placeholder="default (env)" w="80px"
                           bg="whiteAlpha.100"
                           borderColor="whiteAlpha.200"
                           value={params.max_auto_tickers}
                           onChange={(e) => setParams((p) => ({ ...p, max_auto_tickers: e.target.value }))} />
                         <Text fontSize="2xs" color="whiteAlpha.400">(scan only, portfolio always included)</Text>
                       </HStack>
                       {/* Mock-specific controls */}
                       <Box height="1px" bg="whiteAlpha.100" />
                       <Text fontSize="2xs" color="orange.300" fontWeight="bold">Mock settings</Text>
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Type:</Text>
                         <HStack spacing={1}>
                           {(['pipeline', 'scan', 'auto'] as const).map((t) => (
                             <Button
                               key={t}
                               size="xs"
                               variant={params.mock_type === t ? 'solid' : 'ghost'}
                               colorScheme="orange"
                               onClick={() => setParams((p) => ({ ...p, mock_type: t }))}
                             >
                               {t}
                             </Button>
                           ))}
                         </HStack>
                       </HStack>
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Speed:</Text>
                         <HStack spacing={1}>
                           {[['1×', '1'], ['3×', '3'], ['5×', '5'], ['10×', '10']].map(([label, val]) => (
                             <Button
                               key={val}
                               size="xs"
                               variant={params.speed === val ? 'solid' : 'ghost'}
                               colorScheme="orange"
                               onClick={() => setParams((p) => ({ ...p, speed: val }))}
                             >
                               {label}
                             </Button>
                           ))}
                         </HStack>
                       </HStack>
                       <Box height="1px" bg="whiteAlpha.100" />
                       <HStack>
                         <Checkbox
                           size="sm"
                           colorScheme="orange"
                           isChecked={params.force}
                           onChange={(e) => setParams((p) => ({ ...p, force: e.target.checked }))}
                         >
                           <Text fontSize="xs" color="orange.300">Force re-run (ignore cached results)</Text>
                         </Checkbox>
                       </HStack>
                       <Text fontSize="2xs" color="whiteAlpha.400">
                         Required: Scan → date · Pipeline → ticker, date · Portfolio → date, portfolio · Auto → date, portfolio · Mock → no API calls
                       </Text>
                     </VStack>
                   </Box>
                 </Collapse>
               </VStack>
            </Box>

            {/* Right Side: Live Terminal */}
            <VStack w="400px" bg="blackAlpha.400" align="stretch" spacing={0}>
              <Flex p={3} bg="whiteAlpha.50" align="center" gap={2} borderBottom="1px solid" borderColor="whiteAlpha.100">
                 <TerminalIcon size={16} color="#4fd1c5" />
                 <Text fontSize="xs" fontWeight="bold" textTransform="uppercase" letterSpacing="wider">Live Terminal</Text>
                 <Text fontSize="2xs" color="whiteAlpha.400" ml="auto">{events.length} events</Text>
              </Flex>
              
              <Box flex="1" overflowY="auto" p={4} sx={{
                '&::-webkit-scrollbar': { width: '4px' },
                '&::-webkit-scrollbar-track': { background: 'transparent' },
                '&::-webkit-scrollbar-thumb': { background: 'whiteAlpha.300' }
              }}>
                 {events.map((evt) => (
                   <Box
                     key={evt.id}
                     mb={2}
                     fontSize="xs"
                     fontFamily="mono"
                     px={2}
                     py={1}
                     borderRadius="md"
                     cursor="pointer"
                     bg={evt.status === 'error' ? 'red.900' : evt.status === 'graceful_skip' ? 'orange.900' : undefined}
                     borderLeft={evt.status === 'error' ? '3px solid' : evt.status === 'graceful_skip' ? '3px solid' : undefined}
                     borderColor={evt.status === 'error' ? 'red.500' : evt.status === 'graceful_skip' ? 'orange.500' : undefined}
                     _hover={{ bg: evt.status === 'error' ? 'red.800' : 'whiteAlpha.100' }}
                     onClick={() => openEventDetail(evt)}
                     transition="background 0.15s"
                   >
                     <Flex gap={2} align="center">
                       <Text color="whiteAlpha.400" minW="52px" flexShrink={0}>[{evt.timestamp}]</Text>
                       <Text flexShrink={0}>{eventLabel(evt.type, evt.status)}</Text>
                       <Text color={eventColor(evt.type, evt.status)} fontWeight="bold" flexShrink={0}>
                          {evt.agent}
                       </Text>
                       {evt.service && (
                         <Text color="teal.300" fontSize="2xs" flexShrink={0}>[{evt.service}]</Text>
                       )}
                       <ChevronRight size={10} style={{ flexShrink: 0, opacity: 0.4 }} />
                       <Text color={evt.status === 'error' ? 'red.300' : 'whiteAlpha.700'} isTruncated>{eventSummary(evt)}</Text>
                       <Eye size={12} style={{ flexShrink: 0, opacity: 0.3, marginLeft: 'auto' }} />
                     </Flex>
                   </Box>
                 ))}
                 {events.length === 0 && (
                   <Flex h="100%" align="center" justify="center" direction="column" gap={4} opacity={0.3}>
                      <TerminalIcon size={48} />
                      <Text fontSize="sm">Awaiting agent activation...</Text>
                   </Flex>
                 )}
                 <div ref={terminalEndRef} />
              </Box>
            </VStack>
          </Flex>
        </Flex>
      )}

      {/* Unified Inspector Drawer (single event or all node events) */}
      <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
        <DrawerOverlay backdropFilter="blur(4px)" />
        <DrawerContent bg="slate.900" color="white" borderLeft="1px solid" borderColor="whiteAlpha.200">
          <DrawerCloseButton />
          <DrawerHeader borderBottomWidth="1px" borderColor="whiteAlpha.100">
             {drawerTitle}
          </DrawerHeader>
          <DrawerBody py={4}>
            {drawerMode === 'event' && selectedEvent && (
              <EventDetail event={selectedEvent} onOpenModal={openModal} />
            )}
            {drawerMode === 'node' && selectedNodeId && (
              <NodeEventsDetail nodeId={selectedNodeId} identifier={selectedNodeIdentifier} events={events} onOpenModal={openModal} />
            )}
          </DrawerBody>
        </DrawerContent>
      </Drawer>

      {/* Full event detail modal */}
      <EventDetailModal event={modalEvent} isOpen={isModalOpen} onClose={onModalClose} />
    </Flex>
  );
};
