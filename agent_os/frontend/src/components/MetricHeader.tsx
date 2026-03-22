import React from 'react';
import { Box, Flex, Text, Stat, StatLabel, StatNumber, StatHelpText, StatArrow, Badge, Icon } from '@chakra-ui/react';
import { Activity, ShieldAlert, TrendingUp } from 'lucide-react';

export const MetricHeader: React.FC = () => {
  return (
    <Flex bg="slate.900" borderBottom="1px solid" borderColor="whiteAlpha.200" p={4} gap={6} align="center" width="100%">
      {/* Metric 1: Sharpe Ratio */}
      <Box flex="1" bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
        <Flex align="center" gap={2} mb={1}>
          <Icon as={TrendingUp} color="green.400" boxSize={4} />
          <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" textTransform="uppercase">Sharpe Ratio (30d)</Text>
        </Flex>
        <Flex align="baseline" gap={2}>
          <Text fontSize="2xl" fontWeight="black" color="white">2.42</Text>
          <Badge colorScheme="green" variant="subtle" fontSize="2xs">High Efficiency</Badge>
        </Flex>
      </Box>

      {/* Metric 2: Market Regime */}
      <Box flex="1" bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
        <Flex align="center" gap={2} mb={1}>
          <Icon as={Activity} color="cyan.400" boxSize={4} />
          <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" textTransform="uppercase">Market Regime</Text>
        </Flex>
        <Flex align="baseline" gap={2}>
          <Text fontSize="2xl" fontWeight="black" color="cyan.400">BULL</Text>
          <Text fontSize="xs" color="whiteAlpha.500">Beta: 1.15</Text>
        </Flex>
      </Box>

      {/* Metric 3: Risk / Drawdown */}
      <Box flex="1" bg="whiteAlpha.50" p={3} borderRadius="md" border="1px solid" borderColor="whiteAlpha.100">
        <Flex align="center" gap={2} mb={1}>
          <Icon as={ShieldAlert} color="red.400" boxSize={4} />
          <Text fontSize="xs" fontWeight="bold" color="whiteAlpha.600" textTransform="uppercase">Risk / Drawdown</Text>
        </Flex>
        <Flex align="baseline" gap={2}>
          <Text fontSize="2xl" fontWeight="black" color="red.400">-2.4%</Text>
          <Text fontSize="xs" color="whiteAlpha.500">VaR (1d): $4.2k</Text>
        </Flex>
      </Box>
    </Flex>
  );
};
