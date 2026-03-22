import React, { useState, useEffect } from 'react';
import { Box, Flex, Text, Badge, Icon, Spinner } from '@chakra-ui/react';
import { Activity, ShieldAlert, TrendingUp } from 'lucide-react';
import axios from 'axios';

interface SummaryData {
  sharpe_ratio: number;
  market_regime: string;
  beta: number;
  drawdown: number;
  var_1d: number;
  efficiency_label: string;
}

interface MetricHeaderProps {
  portfolioId: string | null;
}

export const MetricHeader: React.FC<MetricHeaderProps> = ({ portfolioId }) => {
  const [data, setData] = useState<SummaryData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!portfolioId) return;

    const fetchSummary = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`http://localhost:8000/api/portfolios/${portfolioId}/summary`);
        setData(res.data);
      } catch (err) {
        console.error("Failed to fetch summary:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
    const interval = setInterval(fetchSummary, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, [portfolioId]);

  if (!data && loading) {
    return (
      <Flex bg="slate.900" borderBottom="1px solid" borderColor="whiteAlpha.200" p={4} justify="center">
        <Spinner color="cyan.400" size="sm" />
      </Flex>
    );
  }

  const displayData = data || {
    sharpe_ratio: 0.0,
    market_regime: 'UNKNOWN',
    beta: 1.0,
    drawdown: 0.0,
    var_1d: 0,
    efficiency_label: 'Pending'
  };

  return (
    <Flex bg="slate.900" borderBottom="1px solid" borderColor="whiteAlpha.200" p={4} gap={6} align="center" width="100%">
      {/* Metric 1: Sharpe Ratio */}
      <Box flex="1" bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
        <Flex align="center" gap={2} mb={1}>
          <Icon as={TrendingUp} color="green.400" boxSize={4} />
          <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" textTransform="uppercase">Sharpe Ratio (30d)</Text>
        </Flex>
        <Flex align="baseline" gap={2}>
          <Text fontSize="2xl" fontWeight="black" color="white">{displayData.sharpe_ratio.toFixed(2)}</Text>
          <Badge colorScheme={displayData.sharpe_ratio > 1.5 ? "green" : "orange"} variant="subtle" fontSize="2xs">
            {displayData.efficiency_label}
          </Badge>
        </Flex>
      </Box>

      {/* Metric 2: Market Regime */}
      <Box flex="1" bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
        <Flex align="center" gap={2} mb={1}>
          <Icon as={Activity} color="cyan.400" boxSize={4} />
          <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" textTransform="uppercase">Market Regime</Text>
        </Flex>
        <Flex align="baseline" gap={2}>
          <Text fontSize="2xl" fontWeight="black" color="cyan.400">{displayData.market_regime}</Text>
          <Text fontSize="xs" color="whiteAlpha.500">Beta: {displayData.beta.toFixed(2)}</Text>
        </Flex>
      </Box>

      {/* Metric 3: Risk / Drawdown */}
      <Box flex="1" bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
        <Flex align="center" gap={2} mb={1}>
          <Icon as={ShieldAlert} color="red.400" boxSize={4} />
          <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" textTransform="uppercase">Risk / Drawdown</Text>
        </Flex>
        <Flex align="baseline" gap={2}>
          <Text fontSize="2xl" fontWeight="black" color="red.400">{displayData.drawdown.toFixed(1)}%</Text>
          <Text fontSize="xs" color="whiteAlpha.500">VaR (1d): ${ (displayData.var_1d / 1000).toFixed(1) }k</Text>
        </Flex>
      </Box>
    </Flex>
  );
};
