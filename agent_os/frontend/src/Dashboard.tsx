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
} from '@chakra-ui/react';
import { LayoutDashboard, Wallet, Settings, Play, Terminal as TerminalIcon, ChevronRight, Eye } from 'lucide-react';
import { MetricHeader } from './components/MetricHeader';
import { AgentGraph } from './components/AgentGraph';
import { useAgentStream, AgentEvent } from './hooks/useAgentStream';
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8088/api';

/** Return the colour token for a given event type. */
const eventColor = (type: AgentEvent['type']): string => {
  switch (type) {
    case 'tool':   return 'purple.400';
    case 'result': return 'green.400';
    case 'log':    return 'yellow.300';
    default:       return 'cyan.400';
  }
};

/** Return a short label badge for the event type. */
const eventLabel = (type: AgentEvent['type']): string => {
  switch (type) {
    case 'thought': return '💭';
    case 'tool':    return '🔧';
    case 'result':  return '✅';
    case 'log':     return 'ℹ️';
    default:        return '●';
  }
};

/** Short summary for terminal — no inline prompts, just agent + type. */
const eventSummary = (evt: AgentEvent): string => {
  switch (evt.type) {
    case 'thought': return `Thinking… (${evt.metrics?.model || 'LLM'})`;
    case 'tool':    return evt.message.startsWith('✓') ? 'Tool result received' : `Tool call: ${evt.message.replace(/^▶ Tool: /, '').split(' | ')[0]}`;
    case 'result':  return 'Completed';
    case 'log':     return evt.message;
    default:        return evt.type;
  }
};

// ─── Detail drawer for a single event ─────────────────────────────────
const EventDetail: React.FC<{ event: AgentEvent }> = ({ event }) => (
  <VStack align="stretch" spacing={4}>
    <HStack>
      <Badge colorScheme="cyan">{event.type.toUpperCase()}</Badge>
      <Badge variant="outline">{event.agent}</Badge>
      <Text fontSize="xs" color="whiteAlpha.400">{event.timestamp}</Text>
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
          {event.metrics.tokens_in != null && (
            <Text>Tokens: <Code>{event.metrics.tokens_in}</Code> in / <Code>{event.metrics.tokens_out}</Code> out</Text>
          )}
          {event.metrics.latency_ms != null && event.metrics.latency_ms > 0 && (
            <Text>Latency: <Code>{event.metrics.latency_ms}ms</Code></Text>
          )}
        </HStack>
      </Box>
    )}

    <Box>
      <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>
        {event.type === 'thought' ? 'Request / Prompt' : event.type === 'result' ? 'Response' : 'Message'}
      </Text>
      <Box bg="blackAlpha.500" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100" maxH="300px" overflowY="auto">
        <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
          {event.message}
        </Text>
      </Box>
    </Box>

    {event.node_id && (
      <Box>
        <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Node ID</Text>
        <Code fontSize="xs">{event.node_id}</Code>
      </Box>
    )}
  </VStack>
);

// ─── Detail drawer showing all events for a given graph node ──────────
const NodeEventsDetail: React.FC<{ nodeId: string; events: AgentEvent[] }> = ({ nodeId, events }) => {
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
          <EventDetail event={evt} />
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

  // What's shown in the drawer: either a single event or all events for a node
  const [drawerMode, setDrawerMode] = useState<'event' | 'node'>('event');
  const [selectedEvent, setSelectedEvent] = useState<AgentEvent | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Auto-scroll the terminal to the bottom as new events arrive
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  const startRun = async (type: string) => {
    if (isTriggering || status === 'streaming' || status === 'connecting') return;
    
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
             <HStack position="absolute" top={4} left={4} bg="blackAlpha.800" p={2} borderRadius="lg" backdropFilter="blur(10px)" border="1px solid" borderColor="whiteAlpha.200" spacing={3}>
                <Button 
                  size="sm" 
                  leftIcon={<Play size={14} />} 
                  colorScheme="cyan" 
                  variant="solid"
                  onClick={() => startRun('scan')}
                  isLoading={isTriggering || status === 'connecting' || status === 'streaming'}
                >
                  Start Market Scan
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
              <EventDetail event={selectedEvent} />
            )}
            {drawerMode === 'node' && selectedNodeId && (
              <NodeEventsDetail nodeId={selectedNodeId} events={events} />
            )}
          </DrawerBody>
        </DrawerContent>
      </Drawer>
    </Flex>
  );
};
