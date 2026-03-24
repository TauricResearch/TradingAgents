import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Flex,
  VStack,
  HStack,
  Text,
  Badge,
  Code,
  Spinner,
  Select,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Icon,
} from '@chakra-ui/react';
import { Wallet, ArrowUpRight, ArrowDownRight, RefreshCw } from 'lucide-react';
import axios from 'axios';

const API_BASE = 'http://127.0.0.1:8088/api';

interface Holding {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
  sector?: string;
  [key: string]: unknown;
}

interface Trade {
  id?: string;
  ticker: string;
  action: string;
  quantity: number;
  price: number;
  executed_at?: string;
  rationale?: string;
  stop_loss?: number | null;
  take_profit?: number | null;
  [key: string]: unknown;
}

interface PortfolioInfo {
  id: string;
  name?: string;
  cash_balance?: number;
  [key: string]: unknown;
}

interface PortfolioState {
  portfolio: PortfolioInfo;
  snapshot: Record<string, unknown> | null;
  holdings: Holding[];
  recent_trades: Trade[];
}

interface PortfolioViewerProps {
  defaultPortfolioId?: string;
}

export const PortfolioViewer: React.FC<PortfolioViewerProps> = ({ defaultPortfolioId = 'main_portfolio' }) => {
  const [portfolios, setPortfolios] = useState<PortfolioInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string>(defaultPortfolioId);
  const [state, setState] = useState<PortfolioState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch portfolio list
  useEffect(() => {
    const fetchList = async () => {
      try {
        const res = await axios.get(`${API_BASE}/portfolios/`);
        const list = res.data as PortfolioInfo[];
        setPortfolios(list);
        if (list.length > 0 && !list.find((p) => p.id === selectedId)) {
          setSelectedId(list[0].id);
        }
      } catch {
        // Might fail if no DB — use fallback
        setPortfolios([{ id: defaultPortfolioId, name: defaultPortfolioId }]);
      }
    };
    fetchList();
  }, [defaultPortfolioId, selectedId]);

  // Fetch portfolio state when selection changes
  const fetchState = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE}/portfolios/${selectedId}/latest`);
      setState(res.data as PortfolioState);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load portfolio';
      setError(msg);
      setState(null);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  return (
    <Flex direction="column" h="100%" bg="slate.950" color="white" overflow="hidden">
      {/* Header */}
      <Flex p={4} bg="slate.900" borderBottom="1px solid" borderColor="whiteAlpha.100" align="center" gap={3}>
        <Icon as={Wallet} color="cyan.400" boxSize={5} />
        <Text fontWeight="bold" fontSize="lg">Portfolio Viewer</Text>

        <Select
          size="sm"
          maxW="220px"
          ml="auto"
          bg="whiteAlpha.100"
          borderColor="whiteAlpha.200"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {portfolios.map((p) => (
            <option key={p.id} value={p.id} style={{ background: '#0f172a' }}>
              {p.name || p.id}
            </option>
          ))}
        </Select>

        <Box cursor="pointer" onClick={fetchState} opacity={0.6} _hover={{ opacity: 1 }}>
          <RefreshCw size={16} />
        </Box>
      </Flex>

      {/* Body */}
      {loading && (
        <Flex flex="1" align="center" justify="center"><Spinner color="cyan.400" /></Flex>
      )}

      {error && (
        <Flex flex="1" align="center" justify="center" direction="column" gap={2} opacity={0.5}>
          <Text fontSize="sm" color="red.300">{error}</Text>
          <Text fontSize="xs">Make sure the backend is running and the portfolio exists.</Text>
        </Flex>
      )}

      {!loading && !error && state && (
        <Tabs variant="soft-rounded" colorScheme="cyan" size="sm" flex="1" display="flex" flexDirection="column" overflow="hidden">
          <TabList px={4} pt={3}>
            <Tab>Holdings ({state.holdings.length})</Tab>
            <Tab>Trade History ({state.recent_trades.length})</Tab>
            <Tab>Summary</Tab>
          </TabList>

          <TabPanels flex="1" overflow="auto">
            {/* Holdings */}
            <TabPanel px={4}>
              {state.holdings.length === 0 ? (
                <Text color="whiteAlpha.500" fontSize="sm" textAlign="center" mt={8}>No holdings found.</Text>
              ) : (
                <Box overflowX="auto">
                  <Table size="sm" variant="unstyled">
                    <Thead>
                      <Tr>
                        <Th color="whiteAlpha.500" borderBottom="1px solid" borderColor="whiteAlpha.100">Ticker</Th>
                        <Th color="whiteAlpha.500" borderBottom="1px solid" borderColor="whiteAlpha.100" isNumeric>Qty</Th>
                        <Th color="whiteAlpha.500" borderBottom="1px solid" borderColor="whiteAlpha.100" isNumeric>Avg Cost</Th>
                        <Th color="whiteAlpha.500" borderBottom="1px solid" borderColor="whiteAlpha.100" isNumeric>Mkt Value</Th>
                        <Th color="whiteAlpha.500" borderBottom="1px solid" borderColor="whiteAlpha.100" isNumeric>P&L</Th>
                        <Th color="whiteAlpha.500" borderBottom="1px solid" borderColor="whiteAlpha.100">Sector</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {state.holdings.map((h, i) => {
                        const pnl = h.unrealized_pnl ?? 0;
                        return (
                          <Tr key={i} _hover={{ bg: 'whiteAlpha.50' }}>
                            <Td fontWeight="bold"><Code colorScheme="cyan" fontSize="sm">{h.ticker}</Code></Td>
                            <Td isNumeric>{h.quantity}</Td>
                            <Td isNumeric>${(h.avg_cost ?? 0).toFixed(2)}</Td>
                            <Td isNumeric>${(h.market_value ?? 0).toFixed(2)}</Td>
                            <Td isNumeric color={pnl >= 0 ? 'green.400' : 'red.400'}>
                              <HStack justify="flex-end" spacing={1}>
                                <Icon as={pnl >= 0 ? ArrowUpRight : ArrowDownRight} boxSize={3} />
                                <Text>${Math.abs(pnl).toFixed(2)}</Text>
                              </HStack>
                            </Td>
                            <Td><Badge variant="outline" fontSize="2xs">{h.sector || '—'}</Badge></Td>
                          </Tr>
                        );
                      })}
                    </Tbody>
                  </Table>
                </Box>
              )}
            </TabPanel>

            {/* Trade History */}
            <TabPanel px={4}>
              {state.recent_trades.length === 0 ? (
                <Text color="whiteAlpha.500" fontSize="sm" textAlign="center" mt={8}>No trades recorded yet.</Text>
              ) : (
                <VStack align="stretch" spacing={2}>
                  {state.recent_trades.map((t, i) => (
                    <Flex
                      key={i}
                      bg="whiteAlpha.50"
                      p={3}
                      borderRadius="md"
                      border="1px solid"
                      borderColor="whiteAlpha.100"
                      justify="space-between"
                      align="flex-start"
                    >
                      <HStack spacing={3} align="flex-start">
                        <Badge colorScheme={t.action?.toUpperCase() === 'BUY' ? 'green' : t.action?.toUpperCase() === 'SELL' ? 'red' : 'gray'}>
                          {t.action?.toUpperCase()}
                        </Badge>
                        <VStack align="flex-start" spacing={0}>
                          <HStack spacing={2}>
                            <Code colorScheme="cyan" fontSize="sm">{t.ticker}</Code>
                            <Text fontSize="sm">{t.quantity} @ ${(t.price ?? 0).toFixed(2)}</Text>
                          </HStack>
                          {(t.stop_loss != null || t.take_profit != null) && (
                            <HStack spacing={3} mt={1}>
                              {t.stop_loss != null && (
                                <HStack spacing={1}>
                                  <Text fontSize="2xs" color="red.400">SL:</Text>
                                  <Text fontSize="2xs" color="red.300" fontWeight="semibold">${t.stop_loss.toFixed(2)}</Text>
                                </HStack>
                              )}
                              {t.take_profit != null && (
                                <HStack spacing={1}>
                                  <Text fontSize="2xs" color="green.400">TP:</Text>
                                  <Text fontSize="2xs" color="green.300" fontWeight="semibold">${t.take_profit.toFixed(2)}</Text>
                                </HStack>
                              )}
                            </HStack>
                          )}
                        </VStack>
                      </HStack>
                      <VStack align="flex-end" spacing={0}>
                        <Text fontSize="2xs" color="whiteAlpha.400">{t.executed_at || '—'}</Text>
                        {t.rationale && (
                          <Text fontSize="2xs" color="whiteAlpha.500" maxW="200px" isTruncated>{t.rationale}</Text>
                        )}
                      </VStack>
                    </Flex>
                  ))}
                </VStack>
              )}
            </TabPanel>

            {/* Summary */}
            <TabPanel px={4}>
              <VStack align="stretch" spacing={3}>
                <HStack>
                  <Text fontSize="sm" color="whiteAlpha.600" minW="100px">Portfolio ID:</Text>
                  <Code fontSize="sm">{state.portfolio.id}</Code>
                </HStack>
                {state.portfolio.cash_balance != null && (
                  <HStack>
                    <Text fontSize="sm" color="whiteAlpha.600" minW="100px">Cash Balance:</Text>
                    <Code colorScheme="green" fontSize="sm">${state.portfolio.cash_balance.toFixed(2)}</Code>
                  </HStack>
                )}
                {state.snapshot && (
                  <Box mt={2}>
                    <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" mb={1}>Latest Snapshot</Text>
                    <Box bg="blackAlpha.500" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100" maxH="300px" overflowY="auto">
                      <Text fontSize="xs" fontFamily="mono" whiteSpace="pre-wrap" wordBreak="break-word" color="whiteAlpha.900">
                        {JSON.stringify(state.snapshot, null, 2)}
                      </Text>
                    </Box>
                  </Box>
                )}
              </VStack>
            </TabPanel>
          </TabPanels>
        </Tabs>
      )}

      {!loading && !error && !state && (
        <Flex flex="1" align="center" justify="center" direction="column" gap={4} opacity={0.3}>
          <Wallet size={48} />
          <Text fontSize="sm">Select a portfolio to view</Text>
        </Flex>
      )}
    </Flex>
  );
};
