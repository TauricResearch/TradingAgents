import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import NewsFeedWidget from '../components/NewsFeedWidget.tsx';

interface AnalysisData {
  symbol: string;
  currentPrice: number;
  marketCap: string;
  psRatio: number;
  forwardPE: number;
  targetPrice: number;
  rsi: number;
  macd: number;
  ma50: number;
  ma200: number;
  stopLoss: number;
  profitTarget1: number;
  profitTarget2: number;
  riskLevel: number;
  bullArguments: string[];
  bearArguments: string[];
  neutralPerspective: string;
  earningsDate: string;
  sentimentScore: number;
  insiderOwnership: number;
  institutionalOwnership: number;
  retailOwnership: number;
  finalDecision: string;
  decisionReasoning: string;
}

interface AnalysisWidgetsProps {
  data: AnalysisData;
  rawData?: any;
  onBackWidget?: () => void;
  onRefreshWidget?: () => void;
  symbol?: string;
  date?: string;
}

const AnalysisWidgets: React.FC<AnalysisWidgetsProps> = ({ data, rawData, onBackWidget, onRefreshWidget, symbol, date }) => {
  const [activeTab, setActiveTab] = useState('bull');
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());
  const [positionSize, setPositionSize] = useState(10000);
  const [portfolioAllocation, setPortfolioAllocation] = useState(4);

  const [showReflectionModal, setShowReflectionModal] = useState(false);
  const [lossResults, setLossResults] = useState('');
  const [isReflecting, setIsReflecting] = useState(false);
  const [reflectionResults, setReflectionResults] = useState(null);
  const [reflectionError, setReflectionError] = useState('');

  console.log('AnalysisWidgets props:', { symbol, date, hasRawData: !!rawData });

  const handleBack = () => {
    if (onBackWidget) return onBackWidget();
    if (typeof window !== 'undefined' && window.history) window.history.back();
  };
  const handleRefresh = () => {
    if (onRefreshWidget) return onRefreshWidget();
    if (typeof window !== 'undefined') window.location.reload();
  };

  const handleReflection = async () => {
    const symbolToUse = symbol || data.symbol || 'UNKNOWN';
    const dateToUse = date || new Date().toISOString().split('T')[0];

    console.log('Reflection attempt:', { symbolToUse, dateToUse, lossResults });

    if (!lossResults.trim()) {
      setReflectionError('Please enter your loss results');
      return;
    }

    setIsReflecting(true);
    setReflectionError('');

    try {
      const response = await fetch(`http://localhost:8000/reflect-on-analysis/${symbolToUse}/${dateToUse}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          returns_losses: lossResults
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to perform reflection');
      }

      const reflectionData = await response.json();
      setReflectionResults(reflectionData);
      setReflectionError('');
    } catch (error) {
      console.error('Reflection error:', error);
      setReflectionError(error.message || 'Failed to perform reflection');
    } finally {
      setIsReflecting(false);
    }
  };

  const WidgetHeader: React.FC<{ title: string }> = ({ title }) => (
    <div className="flex items-center justify-between mb-4">
      <button
        type="button"
        onClick={handleBack}
        className="p-2 rounded hover:bg-gray-100 text-gray-600"
        aria-label="Back"
        title="Back"
      >
        ←
      </button>
      <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
      <div className="flex items-center space-x-2">
        <button
          type="button"
          onClick={() => setShowReflectionModal(true)}
          className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
          title={`Reflect on Analysis (Symbol: ${symbol || data.symbol || 'N/A'}, Date: ${date || 'N/A'})`}
        >
          🤔 Reflect
        </button>
        <button
          type="button"
          onClick={handleRefresh}
          className="p-2 rounded hover:bg-gray-100 text-gray-600"
          aria-label="Refresh"
          title="Refresh"
        >
          ⟳
        </button>
      </div>
    </div>
  );

  const handleModalClose = () => {
    setShowReflectionModal(false);
    setLossResults('');
    setReflectionResults(null);
    setReflectionError('');
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            {data.symbol} Analysis Dashboard
          </h1>
          <div className="flex items-center space-x-4">
            <span className="text-2xl font-semibold text-green-600">
              ${data.currentPrice.toFixed(2)}
            </span>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              data.finalDecision === 'BUY' ? 'bg-green-100 text-green-800' : 
              data.finalDecision === 'SELL' ? 'bg-red-100 text-red-800' : 
              'bg-yellow-100 text-yellow-800'
            }`}>
              {data.finalDecision}
            </span>
          </div>
        </div>

        {/* Core Financial Widgets */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Stock Price Chart */}
          <div className="lg:col-span-2 bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Stock Price Chart" />
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={priceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="price" stroke="#2563eb" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
            <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Daily High:</span>
                <span className="ml-2 font-medium">${(data.currentPrice * 1.05).toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-600">Daily Low:</span>
                <span className="ml-2 font-medium">${(data.currentPrice * 0.95).toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Technical Indicators Dashboard */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Technical Indicators" />
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-gray-600">RSI</span>
                <span className={`font-medium ${data.rsi < 30 ? 'text-green-600' : data.rsi > 70 ? 'text-red-600' : 'text-yellow-600'}`}>
                  {data.rsi.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">MACD</span>
                <span className={`font-medium ${data.macd > 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {data.macd.toFixed(3)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">50-day MA</span>
                <span className={`font-medium ${getTrendColor(data.currentPrice, data.ma50)}`}>
                  ${data.ma50.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">200-day MA</span>
                <span className={`font-medium ${getTrendColor(data.currentPrice, data.ma200)}`}>
                  ${data.ma200.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Key Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-md p-6">
            <h4 className="text-sm font-medium text-gray-600 mb-2">Market Cap</h4>
            <p className="text-2xl font-bold text-gray-900">{data.marketCap}</p>
          </div>
          <div className="bg-white rounded-lg shadow-md p-6">
            <h4 className="text-sm font-medium text-gray-600 mb-2">P/S Ratio</h4>
            <p className="text-2xl font-bold text-gray-900">{data.psRatio.toFixed(1)}x</p>
            <p className="text-sm text-gray-500">vs 0.8x fair value</p>
          </div>
          <div className="bg-white rounded-lg shadow-md p-6">
            <h4 className="text-sm font-medium text-gray-600 mb-2">Forward P/E</h4>
            <p className="text-2xl font-bold text-gray-900">{data.forwardPE.toFixed(2)}</p>
          </div>
          <div className="bg-white rounded-lg shadow-md p-6">
            <h4 className="text-sm font-medium text-gray-600 mb-2">Price Target</h4>
            <p className="text-2xl font-bold text-gray-900">${data.targetPrice.toFixed(2)}</p>
          </div>
        </div>

        {/* Analysis & Decision Widgets */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Bull vs Bear Debate Viewer */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Bull vs Bear Debate" />
            <div className="flex space-x-1 mb-4">
              <button
                className={`px-4 py-2 rounded-lg text-sm font-medium ${
                  activeTab === 'bull' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                }`}
                onClick={() => setActiveTab('bull')}
              >
                Bull Case
              </button>
              <button
                className={`px-4 py-2 rounded-lg text-sm font-medium ${
                  activeTab === 'bear' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-600'
                }`}
                onClick={() => setActiveTab('bear')}
              >
                Bear Case
              </button>
              <button
                className={`px-4 py-2 rounded-lg text-sm font-medium ${
                  activeTab === 'neutral' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-600'
                }`}
                onClick={() => setActiveTab('neutral')}
              >
                Neutral
              </button>
            </div>
            <div className="min-h-[200px]">
              {activeTab === 'bull' && (
                <ul className="space-y-2">
                  {data.bullArguments.map((arg, index) => (
                    <li key={index} className="flex items-start">
                      <span className="text-green-500 mr-2">•</span>
                      <span className="text-sm">{arg}</span>
                    </li>
                  ))}
                </ul>
              )}
              {activeTab === 'bear' && (
                <ul className="space-y-2">
                  {data.bearArguments.map((arg, index) => (
                    <li key={index} className="flex items-start">
                      <span className="text-red-500 mr-2">•</span>
                      <span className="text-sm">{arg}</span>
                    </li>
                  ))}
                </ul>
              )}
              {activeTab === 'neutral' && (
                <p className="text-sm text-gray-700">{data.neutralPerspective}</p>
              )}
            </div>
          </div>

          {/* Investment Plan Timeline */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Investment Plan Timeline" />
            <div className="space-y-4">
              <div className="flex items-center">
                <div className="w-4 h-4 bg-blue-500 rounded-full mr-4"></div>
                <div>
                  <p className="font-medium">Entry Point</p>
                  <p className="text-sm text-gray-600">Current: ${data.currentPrice.toFixed(2)}</p>
                </div>
              </div>
              <div className="flex items-center">
                <div className="w-4 h-4 bg-red-500 rounded-full mr-4"></div>
                <div>
                  <p className="font-medium">Stop Loss</p>
                  <p className="text-sm text-gray-600">${data.stopLoss.toFixed(2)}</p>
                </div>
              </div>
              <div className="flex items-center">
                <div className="w-4 h-4 bg-green-500 rounded-full mr-4"></div>
                <div>
                  <p className="font-medium">Profit Target 1</p>
                  <p className="text-sm text-gray-600">${data.profitTarget1.toFixed(2)}</p>
                </div>
              </div>
              <div className="flex items-center">
                <div className="w-4 h-4 bg-green-600 rounded-full mr-4"></div>
                <div>
                  <p className="font-medium">Profit Target 2</p>
                  <p className="text-sm text-gray-600">${data.profitTarget2.toFixed(2)}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Interactive Decision Tools */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Risk Assessment Gauge */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Risk Assessment" />
            <div className="flex items-center justify-center mb-4">
              <div className="relative w-32 h-32">
                <svg className="w-32 h-32 transform -rotate-90" viewBox="0 0 36 36">
                  <path
                    d="M18 2.0845
                      a 15.9155 15.9155 0 0 1 0 31.831
                      a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="#e5e7eb"
                    strokeWidth="3"
                  />
                  <path
                    d="M18 2.0845
                      a 15.9155 15.9155 0 0 1 0 31.831
                      a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke={data.riskLevel < 30 ? '#10b981' : data.riskLevel < 70 ? '#f59e0b' : '#ef4444'}
                    strokeWidth="3"
                    strokeDasharray={`${data.riskLevel}, 100`}
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className={`text-2xl font-bold ${getRiskColor(data.riskLevel)}`}>
                    {data.riskLevel}%
                  </span>
                </div>
              </div>
            </div>
            <p className="text-center text-sm text-gray-600">Overall Risk Level</p>
          </div>

          {/* Position Calculator */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Position Calculator" />
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Portfolio Size ($)
                </label>
                <input
                  type="number"
                  value={positionSize}
                  onChange={(e) => setPositionSize(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Allocation (%)
                </label>
                <input
                  type="number"
                  value={portfolioAllocation}
                  onChange={(e) => setPortfolioAllocation(Number(e.target.value))}
                  min="1"
                  max="100"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="pt-2 border-t">
                <p className="text-sm text-gray-600">Recommended Position:</p>
                <p className="font-medium">${calculatePosition().allocation.toFixed(2)}</p>
                <p className="text-sm text-gray-600">{calculatePosition().shares} shares</p>
              </div>
            </div>
          </div>

          {/* Sentiment Thermometer */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Sentiment Thermometer" />
            <div className="flex items-center justify-center mb-4">
              <div className="w-8 h-32 bg-gray-200 rounded-full relative">
                <div
                  className={`absolute bottom-0 w-full rounded-full ${
                    data.sentimentScore > 70 ? 'bg-green-500' :
                    data.sentimentScore > 30 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ height: `${data.sentimentScore}%` }}
                ></div>
              </div>
              <div className="ml-4">
                <p className="text-2xl font-bold">{data.sentimentScore}%</p>
                <p className="text-sm text-gray-600">
                  {data.sentimentScore > 70 ? 'Bullish' :
                   data.sentimentScore > 30 ? 'Neutral' : 'Bearish'}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Monitoring & Alerts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* News Feed Widget */}
          <div className="lg:col-span-1">
            <NewsFeedWidget symbol={data.symbol} maxItems={8} onBack={handleBack} onRefresh={handleRefresh} />
          </div>

          {/* Earnings Countdown Timer */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Earnings Countdown" />
            <div className="text-center">
              <p className="text-3xl font-bold text-blue-600 mb-2">{data.earningsDate}</p>
              <p className="text-sm text-gray-600 mb-4">Next Earnings Call</p>
              <div className="text-left">
                <p className="font-medium mb-2">Key Focus Areas:</p>
                <ul className="text-sm text-gray-600 space-y-1">
                  <li>• Revenue growth trajectory</li>
                  <li>• Margin expansion</li>
                  <li>• Forward guidance</li>
                  <li>• Market share gains</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Ownership Structure Pie Chart */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Ownership Structure" />
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={ownershipData}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value.toFixed(2)}%`}
                >
                  {ownershipData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Decision History Tracker */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <WidgetHeader title="Decision History Tracker" />
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-300"></div>
            <div className="space-y-6">
              {[
                { date: '2024-07-20', decision: 'HOLD', reasoning: 'Initial analysis pending earnings data', color: 'yellow' },
                { date: '2024-07-22', decision: 'HOLD', reasoning: 'Technical indicators mixed, awaiting clearer signals', color: 'yellow' },
                { date: '2024-07-25', decision: 'BUY', reasoning: 'Strong fundamentals confirmed, positive technical momentum', color: 'green' },
                { date: '2024-07-26', decision: 'BUY', reasoning: 'Final recommendation based on comprehensive analysis', color: 'green' }
              ].map((item, index) => (
                <div key={index} className="relative flex items-start">
                  <div className={`absolute left-0 w-8 h-8 rounded-full border-4 border-white ${
                    item.color === 'green' ? 'bg-green-500' : 
                    item.color === 'red' ? 'bg-red-500' : 'bg-yellow-500'
                  } shadow-md`}></div>
                  <div className="ml-12">
                    <div className="flex items-center space-x-2 mb-1">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        item.decision === 'BUY' ? 'bg-green-100 text-green-800' :
                        item.decision === 'SELL' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }`}>
                        {item.decision}
                      </span>
                      <span className="text-sm text-gray-500">{item.date}</span>
                    </div>
                    <p className="text-sm text-gray-700">{item.reasoning}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Text Information Widgets */}
        <div className="space-y-6">
          {/* Executive Summary Box */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Executive Summary" />
            <div className="bg-blue-50 border-l-4 border-blue-400 p-4">
              <p className="text-sm">
                <strong>Final Recommendation: {data.finalDecision}</strong> - {data.decisionReasoning}
              </p>
            </div>
          </div>

          {/* Expandable Text Sections */}
          {[
            { key: 'market-report', title: 'Market Report Summary', content: 'Detailed technical analysis with key indicators and price movement analysis...' },
            { key: 'sentiment-report', title: 'Sentiment Report Card', content: 'Complete company sentiment analysis including recent news and social media sentiment...' },
            { key: 'fundamentals', title: 'Fundamentals Report Panel', content: 'Company overview, financial metrics, analyst insights, and key takeaways...' },
            { key: 'macro-news', title: 'Macroeconomic News Brief', content: 'Trade policies, Federal Reserve developments, and market dynamics...' },
            { key: 'debate-transcript', title: 'Investment Debate Transcript', content: 'Complete bull and bear analyst arguments with neutral perspective...' },
            { key: 'risk-analysis', title: 'Risk Analysis Discussion', content: 'Full risky vs safe analyst debate with neutral commentary...' },
            { key: 'investment-plan', title: 'Final Investment Plan Document', content: 'Comprehensive investment strategy with position sizing and risk management...' },
          ].map((section) => (
            <div key={section.key} className="bg-white rounded-lg shadow-md">
              <button
                className="w-full px-6 py-4 text-left flex justify-between items-center hover:bg-gray-50"
                onClick={() => toggleSection(section.key)}
              >
                <h3 className="text-lg font-semibold">{section.title}</h3>
                <span className="text-gray-400">
                  {expandedSections.has(section.key) ? '−' : '+'}
                </span>
              </button>
              {expandedSections.has(section.key) && (
                <div className="px-6 pb-6">
                  <p className="text-gray-700">{section.content}</p>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Raw Data Viewer */}
        {rawData && (
          <div className="bg-white rounded-lg shadow-md p-6">
            <WidgetHeader title="Detailed Analysis Data" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {Object.entries(rawData).map(([key, value]) => (
                <div key={key} className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700 capitalize">
                    {key.replace(/_/g, ' ')}
                  </label>
                  <textarea
                    value={typeof value === 'object' && value !== null ? JSON.stringify(value, null, 2) : String(value || '')}
                    readOnly
                    className="w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50 text-sm font-mono"
                    rows={typeof value === 'object' && value !== null ? Math.min(10, JSON.stringify(value, null, 2).split('\n').length) : 3}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Reflection Modal */}
      {showReflectionModal && (
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity">
          <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
            <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
              <div className="sm:flex sm:items-start">
                <div className="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-red-100 sm:mx-0 sm:h-10 sm:w-10">
                  <svg className="h-6 w-6 text-red-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left">
                  <h3 className="text-lg leading-6 font-medium text-gray-900" id="modal-headline">
                    Reflect on Analysis
                  </h3>
                  <div className="mt-2">
                    <p className="text-sm text-gray-500">
                      Please enter your loss results to reflect on the analysis.
                    </p>
                    <input
                      type="text"
                      value={lossResults}
                      onChange={(e) => setLossResults(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    {reflectionError && (
                      <p className="text-sm text-red-500">{reflectionError}</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
              <button
                type="button"
                onClick={handleReflection}
                disabled={isReflecting}
                className="w-full inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-blue-600 text-base font-medium text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:ml-3 sm:w-auto sm:text-sm"
              >
                {isReflecting ? 'Reflecting...' : 'Reflect'}
              </button>
              <button
                type="button"
                onClick={handleModalClose}
                className="mt-3 w-full inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalysisWidgets;
