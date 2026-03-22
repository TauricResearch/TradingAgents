import React, { useState } from 'react';
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
  Divider,
  Tag,
} from '@chakra-ui/react';
import { LayoutDashboard, Wallet, Settings, Play, Terminal as TerminalIcon, ChevronRight } from 'lucide-react';
import { MetricHeader } from './components/MetricHeader';
import { AgentGraph } from './components/AgentGraph';
import { useAgentStream } from './hooks/useAgentStream';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

export const Dashboard: React.FC = () => {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [portfolioId, setPortfolioId] = useState<string>("main_portfolio");
  const { events, status, clearEvents } = useAgentStream(activeRunId);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [selectedNode, setSelectedNode] = useState<any>(null);

  const startRun = async (type: string) => {
    try {
      clearEvents();
      const res = await axios.post(`${API_BASE}/run/${type}`, {
        portfolio_id: portfolioId,
        date: new Date().toISOString().split('T')[0]
      });
      setActiveRunId(res.data.run_id);
    } catch (err) {
      console.error("Failed to start run:", err);
    }
  };

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
             <AgentGraph events={events} />
             
             {/* Floating Control Panel */}
             <HStack position="absolute" top={4} left={4} bg="blackAlpha.800" p={2} borderRadius="lg" backdropFilter="blur(10px)" border="1px solid" borderColor="whiteAlpha.200" spacing={3}>
                <Button 
                  size="sm" 
                  leftIcon={<Play size={14} />} 
                  colorScheme="cyan" 
                  variant="solid"
                  onClick={() => startRun('scan')}
                  isLoading={status === 'connecting' || status === 'streaming'}
                >
                  Start Market Scan
                </Button>
                <Divider orientation="vertical" h="20px" />
                <Tag size="sm" colorScheme={status === 'streaming' ? 'green' : 'gray'}>
                  {status.toUpperCase()}
                </Tag>
             </HStack>
          </Box>

          {/* Right Side: Live Terminal */}
          <VStack w="400px" bg="blackAlpha.400" align="stretch" spacing={0}>
            <Flex p={3} bg="whiteAlpha.50" align="center" gap={2} borderBottom="1px solid" borderColor="whiteAlpha.100">
               <TerminalIcon size={16} color="#4fd1c5" />
               <Text fontSize="xs" fontWeight="bold" textTransform="uppercase" letterSpacing="wider">Live Terminal</Text>
            </Flex>
            
            <Box flex="1" overflowY="auto" p={4} sx={{
              '&::-webkit-scrollbar': { width: '4px' },
              '&::-webkit-scrollbar-track': { background: 'transparent' },
              '&::-webkit-scrollbar-thumb': { background: 'whiteAlpha.300' }
            }}>
               {events.map((evt, i) => (
                 <Box key={evt.id} mb={3} fontSize="xs" fontFamily="mono">
                   <Flex gap={2}>
                     <Text color="whiteAlpha.400" minW="60px">[{evt.timestamp}]</Text>
                     <Text color={evt.type === 'tool' ? 'purple.400' : evt.type === 'result' ? 'amber.400' : 'cyan.400'} fontWeight="bold">
                        {evt.agent}
                     </Text>
                     <ChevronRight size={12} style={{ marginTop: 2 }} />
                     <Text color="whiteAlpha.800">{evt.message}</Text>
                   </Flex>
                   {evt.metrics && (
                     <HStack spacing={4} mt={1} ml="70px" color="whiteAlpha.400" fontSize="10px">
                       <Text>tokens: {evt.metrics.tokens_in}/{evt.metrics.tokens_out}</Text>
                       <Text>time: {evt.metrics.latency_ms}ms</Text>
                     </HStack>
                   )}
                 </Box>
               ))}
               {events.length === 0 && (
                 <Flex h="100%" align="center" justify="center" direction="column" gap={4} opacity={0.3}>
                    <TerminalIcon size={48} />
                    <Text fontSize="sm">Awaiting agent activation...</Text>
                 </Flex>
               )}
            </Box>
          </VStack>
        </Flex>
      </Flex>

      {/* Node Inspector Drawer */}
      <Drawer isOpen={isOpen} placement="right" onClose={onClose} size="md">
        <DrawerOverlay backdropFilter="blur(4px)" />
        <DrawerContent bg="slate.900" color="white" borderLeft="1px solid" borderColor="whiteAlpha.200">
          <DrawerHeader borderBottomWidth="1px" borderColor="whiteAlpha.100">
             Node Inspector: {selectedNode?.agent}
          </DrawerHeader>
          <DrawerBody>
            {/* Inspector content would go here */}
            <Text>Detailed metrics and raw JSON responses for the selected node.</Text>
          </DrawerBody>
        </DrawerContent>
      </Drawer>
    </Flex>
  );
};
