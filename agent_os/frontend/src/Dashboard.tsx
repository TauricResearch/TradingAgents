import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { 
  Box, 
  Flex, 
  VStack, 
  HStack, 
  Text, 
  IconButton, 
  Button, 
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
} from '@chakra-ui/react';
import { LayoutDashboard, Wallet, Settings, Play, Terminal as TerminalIcon, ChevronRight, Eye, Search, BarChart3, Bot } from 'lucide-react';
import { MetricHeader } from './components/MetricHeader';
import { AgentGraph } from './components/AgentGraph';
import { useAgentStream, AgentEvent } from './hooks/useAgentStream';
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8088/api';

/** Return the colour token for a given event type. */
const eventColor = (type: AgentEvent['type']): string => {
  switch (type) {
    case 'tool':        return 'purple.400';
    case 'tool_result': return 'purple.300';
    case 'result':      return 'green.400';
    case 'log':         return 'yellow.300';
    default:            return 'cyan.400';
  }
};

/** Return a short label badge for the event type. */
const eventLabel = (type: AgentEvent['type']): string => {
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
  switch (evt.type) {
    case 'thought':     return `Thinking… (${evt.metrics?.model || 'LLM'})`;
    case 'tool':        return evt.message.startsWith('✓') ? 'Tool result received' : `Tool call: ${evt.message.replace(/^▶ Tool: /, '').split(' | ')[0]}`;
    case 'tool_result': return `Tool done: ${evt.message.replace(/^✓ Tool result: /, '').split(' | ')[0]}`;
    case 'result':      return 'Completed';
    case 'log':         return evt.message;
    default:            return evt.type;
  }
};

// ─── Full Event Detail Modal ─────────────────────────────────────────
const EventDetailModal: React.FC<{ event: AgentEvent | null; isOpen: boolean; onClose: () => void }> = ({ event, isOpen, onClose }) => {
  if (!event) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="4xl" scrollBehavior="inside">
      <ModalOverlay backdropFilter="blur(6px)" />
      <ModalContent bg="slate.900" color="white" maxH="85vh" border="1px solid" borderColor="whiteAlpha.200">
        <ModalCloseButton />
        <ModalHeader borderBottomWidth="1px" borderColor="whiteAlpha.100">
          <HStack>
            <Badge colorScheme={event.type === 'result' ? 'green' : event.type === 'tool' || event.type === 'tool_result' ? 'purple' : 'cyan'} fontSize="sm">
              {event.type.toUpperCase()}
            </Badge>
            <Badge variant="outline" fontSize="sm">{event.agent}</Badge>
            <Text fontSize="sm" color="whiteAlpha.400" fontWeight="normal">{event.timestamp}</Text>
          </HStack>
        </ModalHeader>
        <ModalBody py={4}>
          <Tabs variant="soft-rounded" colorScheme="cyan" size="sm">
            <TabList mb={4}>
              {event.prompt && <Tab>Prompt / Request</Tab>}
              {(event.response || (event.type === 'result' && event.message)) && <Tab>Response</Tab>}
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
                  <Box bg="blackAlpha.500" p={4} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100" maxH="60vh" overflowY="auto">
                    <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
                      {event.response || event.message}
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
const EventDetail: React.FC<{ event: AgentEvent; onOpenModal?: (evt: AgentEvent) => void }> = ({ event, onOpenModal }) => (
  <VStack align="stretch" spacing={4}>
    <HStack>
      <Badge colorScheme={event.type === 'result' ? 'green' : event.type === 'tool' || event.type === 'tool_result' ? 'purple' : 'cyan'}>{event.type.toUpperCase()}</Badge>
      <Badge variant="outline">{event.agent}</Badge>
      <Text fontSize="xs" color="whiteAlpha.400">{event.timestamp}</Text>
      {onOpenModal && (
        <Button size="xs" variant="ghost" colorScheme="cyan" ml="auto" onClick={() => onOpenModal(event)}>
          Full Detail →
        </Button>
      )}
    </HStack>

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
        <Box bg="blackAlpha.500" p={3} borderRadius="md" border="1px solid" borderColor="green.900" maxH="200px" overflowY="auto">
          <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
            {event.response.length > 1000 ? event.response.substring(0, 1000) + '…' : event.response}
          </Text>
        </Box>
      </Box>
    )}

    {/* Fallback: show message if no prompt/response */}
    {!event.prompt && !event.response && (
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

// ─── Detail drawer showing all events for a given graph node ──────────
const NodeEventsDetail: React.FC<{ nodeId: string; events: AgentEvent[]; onOpenModal: (evt: AgentEvent) => void }> = ({ nodeId, events, onOpenModal }) => {
  const nodeEvents = useMemo(
    () => events.filter((e) => e.node_id === nodeId),
    [events, nodeId],
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

export const Dashboard: React.FC = () => {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [portfolioId, setPortfolioId] = useState<string>("main_portfolio");
  const { events, status, clearEvents } = useAgentStream(activeRunId);
  const { isOpen, onOpen, onClose } = useDisclosure();

  // Event detail modal state
  const { isOpen: isModalOpen, onOpen: onModalOpen, onClose: onModalClose } = useDisclosure();
  const [modalEvent, setModalEvent] = useState<AgentEvent | null>(null);

  // What's shown in the drawer: either a single event or all events for a node
  const [drawerMode, setDrawerMode] = useState<'event' | 'node'>('event');
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Auto-scroll the terminal to the bottom as new events arrive
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  const isRunning = isTriggering || status === 'streaming' || status === 'connecting';

  const startRun = async (type: string) => {
    if (isRunning) return;
    
    setIsTriggering(true);
    try {
      clearEvents();
      const res = await axios.post(`${API_BASE}/run/${type}`, {
        portfolio_id: portfolioId,
        date: new Date().toISOString().split('T')[0]
      });
      setActiveRunId(res.data.run_id);
    } catch (err) {
      console.error("Failed to start run:", err);
    } finally {
      setIsTriggering(false);
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
  const openNodeDetail = useCallback((nodeId: string) => {
    setDrawerMode('node');
    setSelectedNodeId(nodeId);
    setSelectedEvent(null);
    onOpen();
  }, [onOpen]);

  // Derive a readable drawer title
  const drawerTitle = drawerMode === 'event'
    ? `Event: ${selectedEvent?.agent ?? ''} — ${selectedEvent?.type ?? ''}`
    : `Node: ${selectedNodeId ?? ''}`;

  return (
    <Flex h="100vh" bg="slate.950" color="white" overflow="hidden">
      {/* Sidebar */}
      <VStack w="64px" bg="slate.900" borderRight="1px solid" borderColor="whiteAlpha.100" py={4} spacing={6}>
        <Box mb={4}><Text fontWeight="black" color="cyan.400" fontSize="xl">A</Text></Box>
        <IconButton aria-label="Dashboard" icon={<LayoutDashboard size={20} />} variant="ghost" color="cyan.400" _hover={{ bg: "whiteAlpha.100" }} />
        <IconButton aria-label="Portfolio" icon={<Wallet size={20} />} variant="ghost" color="whiteAlpha.600" _hover={{ bg: "whiteAlpha.100" }} />
        <IconButton aria-label="Settings" icon={<Settings size={20} />} variant="ghost" color="whiteAlpha.600" _hover={{ bg: "whiteAlpha.100" }} />
      </VStack>

      {/* Main Content */}
      <Flex flex="1" direction="column">
        {/* Top Metric Header */}
        <MetricHeader portfolioId={portfolioId} />

        {/* Dashboard Body */}
        <Flex flex="1" overflow="hidden">
          {/* Left Side: Graph Area */}
          <Box flex="1" position="relative" borderRight="1px solid" borderColor="whiteAlpha.100">
             <AgentGraph events={events} onNodeClick={openNodeDetail} />
             
             {/* Floating Control Panel */}
             <HStack position="absolute" top={4} left={4} bg="blackAlpha.800" p={2} borderRadius="lg" backdropFilter="blur(10px)" border="1px solid" borderColor="whiteAlpha.200" spacing={2} flexWrap="wrap">
                <Button 
                  size="sm" 
                  leftIcon={<Search size={14} />} 
                  colorScheme="cyan" 
                  variant="solid"
                  onClick={() => startRun('scan')}
                  isLoading={isRunning}
                  loadingText="Running…"
                >
                  Scan
                </Button>
                <Button 
                  size="sm" 
                  leftIcon={<BarChart3 size={14} />} 
                  colorScheme="blue" 
                  variant="solid"
                  onClick={() => startRun('pipeline')}
                  isLoading={isRunning}
                  loadingText="Running…"
                >
                  Pipeline
                </Button>
                <Button 
                  size="sm" 
                  leftIcon={<Wallet size={14} />} 
                  colorScheme="purple" 
                  variant="solid"
                  onClick={() => startRun('portfolio')}
                  isLoading={isRunning}
                  loadingText="Running…"
                >
                  Portfolio
                </Button>
                <Button 
                  size="sm" 
                  leftIcon={<Bot size={14} />} 
                  colorScheme="green" 
                  variant="solid"
                  onClick={() => startRun('auto')}
                  isLoading={isRunning}
                  loadingText="Running…"
                >
                  Auto
                </Button>
                <Divider orientation="vertical" h="20px" />
                <Tag size="sm" colorScheme={status === 'streaming' ? 'green' : status === 'completed' ? 'blue' : 'gray'}>
                  {status.toUpperCase()}
                </Tag>
             </HStack>
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
                   _hover={{ bg: 'whiteAlpha.100' }}
                   onClick={() => openEventDetail(evt)}
                   transition="background 0.15s"
                 >
                   <Flex gap={2} align="center">
                     <Text color="whiteAlpha.400" minW="52px" flexShrink={0}>[{evt.timestamp}]</Text>
                     <Text flexShrink={0}>{eventLabel(evt.type)}</Text>
                     <Text color={eventColor(evt.type)} fontWeight="bold" flexShrink={0}>
                        {evt.agent}
                     </Text>
                     <ChevronRight size={10} style={{ flexShrink: 0, opacity: 0.4 }} />
                     <Text color="whiteAlpha.700" isTruncated>{eventSummary(evt)}</Text>
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
              <NodeEventsDetail nodeId={selectedNodeId} events={events} onOpenModal={openModal} />
            )}
          </DrawerBody>
        </DrawerContent>
      </Drawer>

      {/* Full event detail modal */}
      <EventDetailModal event={modalEvent} isOpen={isModalOpen} onClose={onModalClose} />
    </Flex>
  );
};
