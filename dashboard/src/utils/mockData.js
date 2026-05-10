// Mock data generator aligned with TradingAgents architecture
const generateMockData = () => {
  const agents = [
    { name: 'Market Analyst', role: 'Phase 1 - Analysis', status: 'active', icon: '📊' },
    { name: 'Social Media Analyst', role: 'Phase 1 - Analysis', status: 'active', icon: '📱' },
    { name: 'News Analyst', role: 'Phase 1 - Analysis', status: 'idle', icon: '📰' },
    { name: 'Fundamentals Analyst', role: 'Phase 1 - Analysis', status: 'processing', icon: '💹' },
    { name: 'Bull Researcher', role: 'Phase 2 - Debate', status: 'active', icon: '🐂' },
    { name: 'Bear Researcher', role: 'Phase 2 - Debate', status: 'idle', icon: '🐻' },
    { name: 'Research Manager', role: 'Phase 2 - Synthesis', status: 'processing', icon: '📋' },
    { name: 'Trader', role: 'Phase 3 - Planning', status: 'active', icon: '💼' },
    { name: 'Aggressive Risk Analyst', role: 'Phase 4 - Risk', status: 'idle', icon: '⚡' },
    { name: 'Conservative Risk Analyst', role: 'Phase 4 - Risk', status: 'idle', icon: '🛡️' },
    { name: 'Neutral Risk Analyst', role: 'Phase 4 - Risk', status: 'idle', icon: '⚖️' },
    { name: 'Portfolio Manager', role: 'Phase 5 - Decision', status: 'processing', icon: '🎯' },
  ];

  const trades = [
    { id: 1, ticker: 'AAPL', date: '2024-01-15', rating: 'Buy', price: 185.50, confidence: 0.87 },
    { id: 2, ticker: 'GOOGL', date: '2024-01-14', rating: 'Overweight', price: 142.30, confidence: 0.79 },
    { id: 3, ticker: 'TSLA', date: '2024-01-14', rating: 'Hold', price: 238.45, confidence: 0.65 },
    { id: 4, ticker: 'MSFT', date: '2024-01-13', rating: 'Buy', price: 390.20, confidence: 0.91 },
    { id: 5, ticker: 'NVDA', date: '2024-01-12', rating: 'Overweight', price: 548.80, confidence: 0.88 },
    { id: 6, ticker: 'META', date: '2024-01-11', rating: 'Sell', price: 352.15, confidence: 0.72 },
  ];

  const performanceData = Array.from({ length: 30 }, (_, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    portfolio: 100000 * Math.pow(1.002, i) + Math.random() * 2000,
    benchmark: 100000 * Math.pow(1.001, i) + Math.random() * 1000,
  }));

  const logs = Array.from({ length: 50 }, (_, i) => {
    const levels = ['INFO', 'WARNING', 'ERROR', 'SUCCESS'];
    const messages = [
      'Market Analyst completed analysis for AAPL',
      'Bull researcher initiated debate round 1',
      'Risk assessment completed - moderate volatility detected',
      'Portfolio Manager issued Buy rating with 87% confidence',
      'Data fetch successful: OHLCV data retrieved',
      'Warning: Rate limit approaching for Alpha Vantage API',
      'Checkpoint saved successfully',
      'Reflection updated for previous TSLA trade',
    ];
    return {
      timestamp: new Date(Date.now() - i * 60000).toISOString(),
      level: levels[Math.floor(Math.random() * levels.length)],
      message: messages[Math.floor(Math.random() * messages.length)],
      agent: agents[Math.floor(Math.random() * agents.length)].name,
    };
  });

  return { agents, trades, performanceData, logs };
};

export { generateMockData };
