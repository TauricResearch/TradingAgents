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
  InputGroup,
  InputLeftElement,
  Checkbox,
  Switch,
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
type EventScope = 'all' | 'latest' | number;

interface RunParams {
  date: string;
  ticker: string;
  portfolio_id: string;
  max_auto_tickers: string;
  continue_on_ticker_failure: boolean;
  include_portfolio_holdings: boolean;
  mock_type: MockType;
  speed: string;
  force: boolean;
}

const parseTickerInput = (value: string): string[] =>
  value
    .split(',')
    .map((ticker) => ticker.trim().toUpperCase())
    .filter(Boolean);

const restoreTickerInput = (run: any, fallback: string): string => {
  const params = run?.params || {};
  if (run?.type === 'mock' && params.mock_type === 'auto') {
    const tickers = Array.isArray(params.tickers) ? params.tickers : [];
    return tickers.join(',');
  }
  if (run?.type === 'auto' || run?.type === 'scan' || run?.type === 'portfolio') {
    return '';
  }
  return params.ticker || fallback;
};

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

  const errorEvent = nodeEvents.find((e) => e.status === 'error');
  const errorMsg = errorEvent?.error || errorEvent?.message;

  return (
    <VStack align="stretch" spacing={4}>
      {errorMsg && (
        <Box bg="red.900" border="1px solid" borderColor="red.500" borderRadius="md" p={3}>
          <Text fontSize="xs" fontWeight="bold" color="red.300" mb={1}>Failure Reason</Text>
          <Text fontSize="xs" color="red.200" fontFamily="mono" whiteSpace="pre-wrap">{errorMsg}</Text>
        </Box>
      )}
      {nodeEvents.map((evt) => (
        <Box
          key={evt.id}
          bg={evt.status === 'error' ? 'red.950' : 'whiteAlpha.50'}
          p={3}
          borderRadius="md"
          border="1px solid"
          borderColor={evt.status === 'error' ? 'red.700' : 'whiteAlpha.100'}
        >
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
  const [activeRunRecord, setActiveRunRecord] = useState<any | null>(null);
  const [activeRunReloadKey, setActiveRunReloadKey] = useState(0);
  const [stopRequestedRunId, setStopRequestedRunId] = useState<string | null>(null);
  const [actionRunId, setActionRunId] = useState<string | null>(null);
  const [actionKind, setActionKind] = useState<'resume' | 'stop' | null>(null);
  const [streamEnabled, setStreamEnabled] = useState(true);
  const [activeRunType, setActiveRunType] = useState<RunType | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const { events, status, clearEvents, replaceEvents, setTerminalStatus } = useAgentStream(activeRunId, activeRunReloadKey, streamEnabled);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const toast = useToast();
  const {
    isOpen: isPhase3DecisionOpen,
    onOpen: onPhase3DecisionOpen,
    onClose: onPhase3DecisionClose,
  } = useDisclosure();

  // Event detail modal state
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const [modalEvent, setModalEvent] = useState<AgentEvent | null>(null);
  const [phase3DecisionSelection, setPhase3DecisionSelection] = useState<Record<string, boolean>>({});
  const [phase3DecisionSubmitting, setPhase3DecisionSubmitting] = useState(false);

  // What's shown in the drawer: either a single event or all events for a node
  const [drawerMode, setDrawerMode] = useState<'event' | 'node'>('event');
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedNodeIdentifier, setSelectedNodeIdentifier] = useState<string | null>(null);

  // Parameter inputs
  const [showParams, setShowParams] = useState(false);

  // Terminal search filter
  const [terminalSearchTerm, setTerminalSearchTerm] = useState('');
  const [eventScope, setEventScope] = useState<EventScope>('latest');
  const [tickerFilter, setTickerFilter] = useState<string | null>(null);

  const rerunSeqs = useMemo(() => {
    const unique = new Set<number>();
    events.forEach((evt) => unique.add(typeof evt.rerun_seq === 'number' ? evt.rerun_seq : 0));
    return [...unique].sort((a, b) => a - b);
  }, [events]);

  const latestRerunSeq = rerunSeqs.length > 0 ? rerunSeqs[rerunSeqs.length - 1] : 0;
  const scopedSeq = eventScope === 'all' ? null : eventScope === 'latest' ? latestRerunSeq : eventScope;

  useEffect(() => {
    if (eventScope === 'all' || eventScope === 'latest') return;
    if (!rerunSeqs.includes(eventScope)) {
      setEventScope('latest');
    }
  }, [eventScope, rerunSeqs]);

  const scopedEvents = useMemo(() => {
    if (scopedSeq === null) return events;
    return events.filter((evt) => (typeof evt.rerun_seq === 'number' ? evt.rerun_seq : 0) === scopedSeq);
  }, [events, scopedSeq]);

  const availableIdentifiers = useMemo(() => {
    const ids = new Set<string>();
    scopedEvents.forEach((e) => {
      if (e.identifier && e.identifier !== 'MARKET' && e.identifier !== 'PORTFOLIO') ids.add(e.identifier);
    });
    return [...ids].sort();
  }, [scopedEvents]);

  const filteredEvents = useMemo(() => {
    let result = scopedEvents;
    if (tickerFilter) result = result.filter((e) => e.identifier === tickerFilter);
    if (!terminalSearchTerm.trim()) return result;
    const term = terminalSearchTerm.toLowerCase();
    return result.filter(evt =>
      evt.agent?.toLowerCase().includes(term) ||
      evt.node_id?.toLowerCase().includes(term) ||
      evt.service?.toLowerCase().includes(term) ||
      evt.message?.toLowerCase().includes(term) ||
      evt.identifier?.toLowerCase().includes(term)
    );
  }, [scopedEvents, tickerFilter, terminalSearchTerm]);
  const [params, setParams] = useState<RunParams>({
    date: new Date().toISOString().split('T')[0],
    ticker: 'AAPL',
    portfolio_id: 'main_portfolio',
    max_auto_tickers: '',
    continue_on_ticker_failure: false,
    include_portfolio_holdings: true,
    mock_type: 'pipeline',
    speed: '3',
    force: false,
  });

  // Auto-scroll the terminal to the bottom as new events arrive
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Fetch initial config
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await axios.get(`${API_BASE}/config`);
        if (res.data.default_portfolio_id) {
          setParams((p) => ({ ...p, portfolio_id: res.data.default_portfolio_id }));
        }
      } catch (err) {
        console.error("Failed to fetch config:", err);
      }
    };
    fetchConfig();
  }, []);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  // Clear activeRunType when run completes
  useEffect(() => {
    if (status === 'completed' || status === 'error' || status === 'paused') {
      setActiveRunType(null);
      setStopRequestedRunId(null);
      if (status === 'completed' || status === 'error') {
        setActiveRunRecord((prev: any) => (prev ? { ...prev, status: status === 'completed' ? 'completed' : 'failed' } : prev));
      }
    }
  }, [status]);

  useEffect(() => {
    if (status !== 'paused' || !activeRunId) return;
    const loadPausedRun = async () => {
      try {
        const res = await axios.get(`${API_BASE}/run/${activeRunId}`);
        setActiveRunRecord(res.data);
        setStreamEnabled(false);
        loadHistory();
      } catch (err) {
        console.error('Failed to refresh paused run details', err);
      }
    };
    loadPausedRun();
  }, [status, activeRunId]);

  const isRunning = isTriggering || status === 'streaming' || status === 'connecting';
  const isActiveRunStopping = Boolean(activeRunId && stopRequestedRunId === activeRunId && isRunning);
  const selectedRunId = activeRunRecord?.id ?? null;
  const selectedRunStatus = activeRunRecord?.status ?? null;
  const isSelectedRunStopping = Boolean(selectedRunId && stopRequestedRunId === selectedRunId);
  const canStopSelectedRun = Boolean(
    selectedRunId && (
      selectedRunStatus === 'running'
      || isSelectedRunStopping
      || (activeRunId === selectedRunId && isRunning)
    ),
  );
  const canResumeSelectedRun = Boolean(selectedRunId && selectedRunStatus === 'failed' && !isRunning);
  const pendingPhase3Decision = activeRunRecord?.pending_phase3_decision || null;
  const incompletePhase3Tickers = pendingPhase3Decision?.incomplete_tickers || [];
  const selectedRetryTickers = incompletePhase3Tickers
    .filter((item: any) => phase3DecisionSelection[item.ticker])
    .map((item: any) => item.ticker);

  useEffect(() => {
    if (activeRunRecord?.status !== 'awaiting_decision' || !pendingPhase3Decision) return;
    setPhase3DecisionSelection(
      Object.fromEntries(
        (pendingPhase3Decision.incomplete_tickers || []).map((item: any) => [item.ticker, false]),
      ),
    );
    onPhase3DecisionOpen();
  }, [activeRunRecord?.status, pendingPhase3Decision, onPhase3DecisionOpen]);

  const syncParamsFromRun = useCallback((run: any) => {
    if (!run?.params) return;
    setParams((p) => ({
      ...p,
      date: run.params.date || p.date,
      ticker: restoreTickerInput(run, p.ticker),
      portfolio_id: run.params.portfolio_id || p.portfolio_id,
      max_auto_tickers: run.params.max_tickers?.toString() || run.params.max_auto_tickers?.toString() || '',
      continue_on_ticker_failure: Boolean(run.params.continue_on_ticker_failure),
      include_portfolio_holdings: run.params.include_portfolio_holdings !== false,
      mock_type: run.params.mock_type || p.mock_type,
      speed: run.params.speed?.toString() || p.speed,
      force: Boolean(run.params.force),
    }));
  }, []);

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
      setStreamEnabled(true);
      clearEvents();
      const inputTickers = parseTickerInput(effectiveParams.ticker);
      let body: Record<string, unknown>;
      if (type === 'mock') {
        body = {
          mock_type: effectiveParams.mock_type,
          date: effectiveParams.date,
          speed: parseFloat(effectiveParams.speed) || 3,
        };
        if (effectiveParams.mock_type === 'auto') {
          if (inputTickers.length > 0) body.tickers = inputTickers;
        } else if (effectiveParams.mock_type === 'pipeline' && inputTickers.length > 0) {
          body.ticker = inputTickers[0];
        }
      } else {
        body = {
          portfolio_id: effectiveParams.portfolio_id,
          date: effectiveParams.date,
          force: effectiveParams.force,
          continue_on_ticker_failure: effectiveParams.continue_on_ticker_failure,
          include_portfolio_holdings: effectiveParams.include_portfolio_holdings,
          ...(effectiveParams.max_auto_tickers ? { max_tickers: parseInt(effectiveParams.max_auto_tickers, 10) } : {}),
        };
        if (type === 'pipeline' && inputTickers.length > 0) {
          body.ticker = inputTickers[0];
        }
      }
      const res = await axios.post(`${API_BASE}/run/${type}`, body);
      setActiveRunId(res.data.run_id);
      setActiveRunRecord({ id: res.data.run_id, type, status: 'running', params: body });
      setStopRequestedRunId(null);
      setEventScope('latest');
    } catch (err) {
      console.error("Failed to start run:", err);
      setActiveRunType(null);
    } finally {
      setIsTriggering(false);
    }
  };

  /** Re-run triggered from a graph node's Re-run button. */
  const handleNodeRerun = useCallback((identifier: string, nodeId: string) => {
    // If we have an active loaded run, re-run the selected node within that run.
    if (activeRunId && nodeId && identifier) {
      triggerNodeRerun(activeRunId, identifier, nodeId);
      return;
    }
    toast({
      title: 'Load a run before re-running a node',
      description: 'Select the historical run first, then use the node re-run action.',
      status: 'warning',
      duration: 4000,
      isClosable: true,
      position: 'top',
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId, toast]);

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

  const loadRun = async (run: any) => {
    clearEvents();
    setEventScope('latest');
    syncParamsFromRun(run);
    try {
      const res = await axios.get(`${API_BASE}/run/${run.id}`);
      const snapshot = res.data as any;
      replaceEvents((snapshot.events || []) as AgentEvent[]);
      setActiveRunRecord({ ...run, ...snapshot });
      setStopRequestedRunId(null);
      if (snapshot.status === 'completed') {
        setTerminalStatus('completed');
        setStreamEnabled(false);
      } else if (snapshot.status === 'awaiting_decision') {
        setTerminalStatus('paused');
        setStreamEnabled(false);
        setActiveRunId(run.id);
      } else if (snapshot.status === 'failed') {
        setTerminalStatus('error', snapshot.error ? `Error: Run failed: ${snapshot.error}` : 'Error: Run failed');
        setStreamEnabled(false);
      } else {
        setStreamEnabled(true);
        setTerminalStatus('idle');
        setActiveRunId(run.id);
        setActiveRunReloadKey((k) => k + 1);
      }
    } catch (err) {
      console.error('Failed to load run details', err);
      setActiveRunRecord(run);
      setStopRequestedRunId(null);
      setStreamEnabled(true);
      setTerminalStatus('idle');
      setActiveRunId(run.id);
      setActiveRunReloadKey((k) => k + 1);
    }
  };

  const resumeRun = async (run: any) => {
    const targetRun = run || activeRunRecord;
    if (!targetRun?.id) return;

    syncParamsFromRun(targetRun);
    setActionRunId(targetRun.id);
    setActionKind('resume');
    try {
      await axios.post(`${API_BASE}/run/${targetRun.id}/resume`);
      clearEvents();
      setStreamEnabled(true);
      setTerminalStatus('idle');
      setActiveRunId(targetRun.id);
      setActiveRunType((targetRun.type || null) as RunType | null);
      setActiveRunRecord({ ...targetRun, status: 'running' });
      setStopRequestedRunId(null);
      setEventScope('latest');
      setActiveRunReloadKey((k) => k + 1);
      toast({
        title: `Resumed run ${targetRun.id.slice(-8)}`,
        status: 'success',
        duration: 3000,
        isClosable: true,
        position: 'top',
      });
      loadHistory();
    } catch (err: any) {
      toast({
        title: 'Resume failed',
        description: err?.response?.data?.detail || String(err),
        status: 'error',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });
    } finally {
      setActionRunId(null);
      setActionKind(null);
    }
  };

  const stopRun = async (run: any) => {
    const targetRun = run || activeRunRecord;
    if (!targetRun?.id) return;

    setActionRunId(targetRun.id);
    setActionKind('stop');
    try {
      await axios.post(`${API_BASE}/run/${targetRun.id}/stop`);
      setStopRequestedRunId(targetRun.id);
      setActiveRunRecord((prev: any) => (prev?.id === targetRun.id ? { ...prev, status: 'stopping' } : prev));
      toast({
        title: 'Stop requested',
        description: 'This run will stop and can be resumed later from history.',
        status: 'info',
        duration: 3500,
        isClosable: true,
        position: 'top',
      });
      loadHistory();
    } catch (err: any) {
      toast({
        title: 'Stop failed',
        description: err?.response?.data?.detail || String(err),
        status: 'error',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });
    } finally {
      setActionRunId(null);
      setActionKind(null);
    }
  };

  const submitPhase3Decision = async () => {
    if (!activeRunRecord?.id) return;
    setPhase3DecisionSubmitting(true);
    try {
      await axios.post(`${API_BASE}/run/${activeRunRecord.id}/phase3-decision`, {
        retry_tickers: selectedRetryTickers,
      });
      onPhase3DecisionClose();
      setStreamEnabled(true);
      setTerminalStatus('idle');
      setActiveRunId(activeRunRecord.id);
      setActiveRunRecord((prev: any) => (prev ? { ...prev, status: 'running' } : prev));
      setEventScope('latest');
      setActiveRunReloadKey((k) => k + 1);
      loadHistory();
      toast({
        title: selectedRetryTickers.length > 0 ? 'Retrying selected tickers' : 'Continuing to Phase 3',
        status: 'info',
        duration: 3000,
        isClosable: true,
        position: 'top',
      });
    } catch (err: any) {
      toast({
        title: 'Phase 3 decision failed',
        description: err?.response?.data?.detail || String(err),
        status: 'error',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });
    } finally {
      setPhase3DecisionSubmitting(false);
    }
  };

  /** Trigger a phase-level re-run for a specific node on the active run. */
  const triggerNodeRerun = async (runId: string, identifier: string, nodeId: string) => {
    try {
      setStreamEnabled(true);
      const res = await axios.post(`${API_BASE}/run/rerun-node`, {
        run_id: runId,
        node_id: nodeId,
        identifier,
        date: params.date,
        portfolio_id: params.portfolio_id,
      });
      // Preserve in-session history so the user can compare base vs rerun output.
      setEventScope('all');
      setActiveRunId(res.data.run_id);
      setActiveRunReloadKey((k) => k + 1);
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
               <AgentGraph events={events} allEvents={events} runStatus={status} onNodeClick={openNodeDetail} onNodeRerun={handleNodeRerun} />
               
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
                    {canResumeSelectedRun && (
                      <Button
                        size="sm"
                        colorScheme="blue"
                        variant="outline"
                        onClick={() => resumeRun(activeRunRecord)}
                        isLoading={actionRunId === selectedRunId && actionKind === 'resume'}
                      >
                        Resume Loaded Run
                      </Button>
                    )}
                    {activeRunRecord?.status === 'awaiting_decision' && !isRunning && (
                      <Button
                        size="sm"
                        colorScheme="orange"
                        variant="outline"
                        onClick={onPhase3DecisionOpen}
                      >
                        Review Incomplete Tickers
                      </Button>
                    )}
                    {canStopSelectedRun && (
                      <Button
                        size="sm"
                        colorScheme="orange"
                        variant={isSelectedRunStopping || isActiveRunStopping ? 'solid' : 'outline'}
                        onClick={() => stopRun(activeRunRecord)}
                        isDisabled={isSelectedRunStopping}
                        isLoading={actionRunId === selectedRunId && actionKind === 'stop'}
                      >
                        {isSelectedRunStopping ? 'Stopping…' : 'Stop Loaded Run'}
                      </Button>
                    )}
                    <Divider orientation="vertical" h="20px" />
                    <Tag size="sm" colorScheme={status === 'streaming' ? 'green' : status === 'completed' ? 'blue' : status === 'paused' ? 'orange' : status === 'error' ? 'red' : 'gray'}>
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
                                <Tag size="sm" colorScheme={r.status === 'completed' ? 'blue' : r.status === 'running' ? 'green' : r.status === 'awaiting_decision' ? 'orange' : r.status === 'failed' ? 'red' : 'gray'} ml="auto">
                                  {r.status}
                                </Tag>
                                <Text fontSize="2xs" color="whiteAlpha.400">
                                  {r.created_at ? new Date(r.created_at * 1000).toLocaleTimeString() : ''}
                                </Text>
                                {r.status === 'failed' && (
                                  <Button
                                    size="xs"
                                    colorScheme="blue"
                                    variant="ghost"
                                    isLoading={actionRunId === r.id && actionKind === 'resume'}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      resumeRun(r);
                                    }}
                                  >
                                    Resume
                                  </Button>
                                )}
                                {r.status === 'awaiting_decision' && (
                                  <Button
                                    size="xs"
                                    colorScheme="orange"
                                    variant="ghost"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      loadRun(r);
                                      onPhase3DecisionOpen();
                                    }}
                                  >
                                    Review
                                  </Button>
                                )}
                                {(r.status === 'running' || stopRequestedRunId === r.id) && (
                                  <Button
                                    size="xs"
                                    colorScheme="orange"
                                    variant="ghost"
                                    isLoading={actionRunId === r.id && actionKind === 'stop'}
                                    isDisabled={stopRequestedRunId === r.id}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      stopRun(r);
                                    }}
                                  >
                                    {stopRequestedRunId === r.id ? 'Stopping…' : 'Stop'}
                                  </Button>
                                )}
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
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Holdings:</Text>
                         <Switch
                           size="sm"
                           colorScheme="teal"
                           isChecked={params.include_portfolio_holdings}
                           onChange={(e) => setParams((p) => ({ ...p, include_portfolio_holdings: e.target.checked }))}
                         />
                         <Text fontSize="xs" color="whiteAlpha.500">Include portfolio holdings</Text>
                       </HStack>
                       <HStack>
                         <Text fontSize="xs" color="whiteAlpha.600" minW="70px">Max Tickers</Text>
                         <Input size="xs" type="number" min={1} placeholder="default (env)" w="80px"
                           bg="whiteAlpha.100"
                           borderColor="whiteAlpha.200"
                           value={params.max_auto_tickers}
                           onChange={(e) => setParams((p) => ({ ...p, max_auto_tickers: e.target.value }))} />
                         <Text fontSize="2xs" color="whiteAlpha.400">(scan candidates only)</Text>
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
                           isChecked={params.continue_on_ticker_failure}
                           onChange={(e) => setParams((p) => ({ ...p, continue_on_ticker_failure: e.target.checked }))}
                         >
                           <Text fontSize="xs" color="orange.300">Auto only: continue to Phase 3 and skip failed tickers</Text>
                         </Checkbox>
                       </HStack>
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

                 <Collapse in={rerunSeqs.length > 1 || eventScope === 'all'} animateOpacity>
                   <HStack
                     bg="blackAlpha.800"
                     p={2}
                     borderRadius="lg"
                     backdropFilter="blur(10px)"
                     border="1px solid"
                     borderColor="whiteAlpha.200"
                     spacing={2}
                     flexWrap="wrap"
                   >
                     <Text fontSize="2xs" color="whiteAlpha.600" textTransform="uppercase" letterSpacing="wider">
                       Event Scope
                     </Text>
                     <Button
                       size="xs"
                       variant={eventScope === 'latest' ? 'solid' : 'ghost'}
                       colorScheme="cyan"
                       onClick={() => setEventScope('latest')}
                     >
                       Latest
                     </Button>
                     <Button
                       size="xs"
                       variant={eventScope === 'all' ? 'solid' : 'ghost'}
                       colorScheme="cyan"
                       onClick={() => setEventScope('all')}
                     >
                       All
                     </Button>
                     {rerunSeqs.map((seq) => (
                       <Button
                         key={seq}
                         size="xs"
                         variant={eventScope === seq ? 'solid' : 'ghost'}
                         colorScheme={seq === 0 ? 'gray' : 'orange'}
                         onClick={() => setEventScope(seq)}
                       >
                         {seq === 0 ? 'Base' : `R${seq}`}
                       </Button>
                     ))}
                   </HStack>
                 </Collapse>
               </VStack>
            </Box>

            {/* Right Side: Live Terminal */}
            <VStack w="400px" bg="blackAlpha.400" align="stretch" spacing={0}>
              <Flex p={2} bg="whiteAlpha.50" align="center" gap={2} borderBottom="1px solid" borderColor="whiteAlpha.100">
                 <TerminalIcon size={16} color="#4fd1c5" />
                 <Text fontSize="xs" fontWeight="bold" textTransform="uppercase" letterSpacing="wider" display={{ base: 'none', lg: 'block' }}>Terminal</Text>
                 <InputGroup size="xs" maxW="200px" ml="auto">
                    <InputLeftElement pointerEvents="none">
                      <Search size={12} color="gray.500" />
                    </InputLeftElement>
                    <Input 
                      placeholder="Filter..." 
                      variant="filled" 
                      bg="whiteAlpha.100" 
                      _hover={{ bg: 'whiteAlpha.200' }}
                      value={terminalSearchTerm}
                      onChange={(e) => setTerminalSearchTerm(e.target.value)}
                    />
                 </InputGroup>
                 <Text fontSize="2xs" color="whiteAlpha.400" ml={2} minW="40px" textAlign="right">
                   {filteredEvents.length} / {scopedEvents.length}
                 </Text>
              </Flex>

              {availableIdentifiers.length > 0 && (
                <Flex gap={1} px={3} py={1.5} borderBottom="1px solid" borderColor="whiteAlpha.100" flexWrap="wrap" bg="blackAlpha.300">
                  <Button size="xs" variant={tickerFilter === null ? 'solid' : 'ghost'} colorScheme="cyan" onClick={() => setTickerFilter(null)}>All</Button>
                  {availableIdentifiers.map((id) => (
                    <Button key={id} size="xs" variant={tickerFilter === id ? 'solid' : 'ghost'} colorScheme="purple" onClick={() => setTickerFilter(tickerFilter === id ? null : id)}>{id}</Button>
                  ))}
                </Flex>
              )}

              <Box flex="1" overflowY="auto" p={4} sx={{
                '&::-webkit-scrollbar': { width: '4px' },
                '&::-webkit-scrollbar-track': { background: 'transparent' },
                '&::-webkit-scrollbar-thumb': { background: 'whiteAlpha.300' }
              }}>
                 {filteredEvents.map((evt) => (
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
                       {evt.identifier && evt.identifier !== 'MARKET' && evt.identifier !== 'PORTFOLIO' && (
                         <Badge fontSize="2xs" colorScheme="purple" variant="subtle" flexShrink={0}>{evt.identifier}</Badge>
                       )}
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
              <NodeEventsDetail nodeId={selectedNodeId} identifier={selectedNodeIdentifier} events={scopedEvents} onOpenModal={openModal} />
            )}
          </DrawerBody>
        </DrawerContent>
      </Drawer>

      <Modal
        isOpen={isPhase3DecisionOpen}
        onClose={onPhase3DecisionClose}
        size="xl"
        closeOnOverlayClick={!phase3DecisionSubmitting}
      >
        <ModalOverlay backdropFilter="blur(6px)" />
        <ModalContent bg="slate.900" color="white" border="1px solid" borderColor="whiteAlpha.200">
          <ModalCloseButton isDisabled={phase3DecisionSubmitting} />
          <ModalHeader borderBottomWidth="1px" borderColor="whiteAlpha.100">
            Incomplete Tickers Before Phase 3
          </ModalHeader>
          <ModalBody py={4}>
            <VStack align="stretch" spacing={4}>
              <Text fontSize="sm" color="whiteAlpha.800">
                Select the incomplete tickers you want to retry. If you leave all boxes unchecked and continue, the run will proceed to Phase 3 with the current completed analyses only.
              </Text>
              {(incompletePhase3Tickers as any[]).map((item: any) => (
                <Box
                  key={item.ticker}
                  p={3}
                  borderRadius="md"
                  bg="whiteAlpha.50"
                  border="1px solid"
                  borderColor="whiteAlpha.100"
                >
                  <Checkbox
                    colorScheme="orange"
                    isChecked={Boolean(phase3DecisionSelection[item.ticker])}
                    onChange={(e) =>
                      setPhase3DecisionSelection((prev) => ({
                        ...prev,
                        [item.ticker]: e.target.checked,
                      }))
                    }
                  >
                    <Text as="span" fontWeight="bold">{item.ticker}</Text>
                  </Checkbox>
                  <Text mt={2} ml={6} fontSize="xs" color="whiteAlpha.700">
                    {item.reason}
                  </Text>
                  <Badge ml={6} mt={2} colorScheme={item.portfolio_context === 'holding' ? 'purple' : 'cyan'}>
                    {item.portfolio_context === 'holding' ? 'holding' : 'candidate'}
                  </Badge>
                </Box>
              ))}
              <HStack justify="flex-end" pt={2}>
                <Button variant="ghost" onClick={onPhase3DecisionClose} isDisabled={phase3DecisionSubmitting}>
                  Close
                </Button>
                <Button
                  colorScheme="orange"
                  onClick={submitPhase3Decision}
                  isLoading={phase3DecisionSubmitting}
                  loadingText="Submitting…"
                >
                  {selectedRetryTickers.length > 0 ? 'Retry Selected' : 'Continue To Phase 3'}
                </Button>
              </HStack>
            </VStack>
          </ModalBody>
        </ModalContent>
      </Modal>

      {/* Full event detail modal */}
      <EventDetailModal event={modalEvent} isOpen={isModalOpen} onClose={onModalClose} />
    </Flex>
  );
};
