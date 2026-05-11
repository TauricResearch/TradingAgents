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

  const reports = [
    { id: 'rep-001', title: 'Weekly Market Analysis - Tech Sector', date: '2024-01-14', type: 'Weekly', author: 'Research Manager', summary: 'Deep dive into tech sector performance and agent consensus.' },
    { id: 'rep-002', title: 'AAPL Earnings Deep Dive', date: '2024-01-12', type: 'Flash', author: 'Market Analyst', summary: 'Detailed breakdown of Apple Q4 results and forward-looking guidance.' },
    { id: 'rep-003', title: 'Monthly Performance Review - Dec 2023', date: '2024-01-05', type: 'Monthly', author: 'Portfolio Manager', summary: 'Analysis of last month\'s trading performance and alpha generation.' },
    { id: 'rep-004', title: 'AI Ethics and Compliance Report', date: '2024-01-02', type: 'Special', author: 'Risk Manager', summary: 'Evaluation of agent compliance with ethical trading guidelines.' },
  ];

  const prompts = [
    { id: 'p-1', name: 'Market Analysis System Prompt', category: 'Phase 1', lastUpdated: '2024-01-10', version: '2.4.1', description: 'Core prompt for analyzing market data and technical indicators.' },
    { id: 'p-2', name: 'Debate Facilitator Prompt', category: 'Phase 2', lastUpdated: '2024-01-08', version: '1.2.0', description: 'Manages the dialectic process between bull and bear agents.' },
    { id: 'p-3', name: 'Risk Assessment Framework', category: 'Phase 4', lastUpdated: '2024-01-12', version: '3.0.5', description: 'Defines risk parameters and loss mitigation strategies.' },
    { id: 'p-4', name: 'Trade Execution Planner', category: 'Phase 3', lastUpdated: '2024-01-11', version: '2.1.0', description: 'Translates research findings into actionable trade plans.' },
  ];

  return { agents, trades, performanceData, logs, reports, prompts };
};

export { generateMockData };
