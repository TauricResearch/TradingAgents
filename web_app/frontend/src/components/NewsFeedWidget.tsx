import React, { useState, useEffect } from 'react';

interface NewsItem {
  id: string;
  title: string;
  summary: string;
  timestamp: string;
  category: 'macro' | 'company' | 'sector';
  impact: 'positive' | 'negative' | 'neutral';
  source: string;
}

interface NewsFeedWidgetProps {
  symbol: string;
  maxItems?: number;
}

const NewsFeedWidget: React.FC<NewsFeedWidgetProps> = ({ symbol, maxItems = 10 }) => {
  const [newsItems, setNewsItems] = useState<NewsItem[]>([]);
  const [filter, setFilter] = useState<'all' | 'macro' | 'company' | 'sector'>('all');

  // Mock news data - in production, this would come from your backend
  useEffect(() => {
    const mockNews: NewsItem[] = [
      {
        id: '1',
        title: 'Federal Reserve Signals Potential Rate Cuts',
        summary: 'Fed Chairman indicates possible monetary policy easing in response to economic indicators.',
        timestamp: '2 hours ago',
        category: 'macro',
        impact: 'positive',
        source: 'Reuters'
      },
      {
        id: '2',
        title: `${symbol} Announces Strategic Partnership`,
        summary: 'Company enters into major partnership agreement to expand market reach.',
        timestamp: '4 hours ago',
        category: 'company',
        impact: 'positive',
        source: 'Business Wire'
      },
      {
        id: '3',
        title: 'Trade Policy Updates Impact Tech Sector',
        summary: 'New trade regulations expected to affect technology companies operations.',
        timestamp: '6 hours ago',
        category: 'sector',
        impact: 'negative',
        source: 'Financial Times'
      },
      {
        id: '4',
        title: 'Market Volatility Increases Amid Economic Uncertainty',
        summary: 'Global markets show increased volatility as investors assess economic conditions.',
        timestamp: '8 hours ago',
        category: 'macro',
        impact: 'negative',
        source: 'Bloomberg'
      },
      {
        id: '5',
        title: `${symbol} Q2 Earnings Preview`,
        summary: 'Analysts expect strong quarterly results driven by revenue growth initiatives.',
        timestamp: '12 hours ago',
        category: 'company',
        impact: 'positive',
        source: 'MarketWatch'
      },
      {
        id: '6',
        title: 'Sector Rotation Favors Growth Stocks',
        summary: 'Institutional investors showing renewed interest in growth-oriented companies.',
        timestamp: '1 day ago',
        category: 'sector',
        impact: 'positive',
        source: 'Wall Street Journal'
      }
    ];
    setNewsItems(mockNews);
  }, [symbol]);

  const filteredNews = newsItems.filter(item => 
    filter === 'all' || item.category === filter
  ).slice(0, maxItems);

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'positive': return 'text-green-600 bg-green-50 border-green-200';
      case 'negative': return 'text-red-600 bg-red-50 border-red-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'macro': return '🌍';
      case 'company': return '🏢';
      case 'sector': return '📊';
      default: return '📰';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">News Feed</h3>
        <div className="flex space-x-2">
          {['all', 'macro', 'company', 'sector'].map((filterOption) => (
            <button
              key={filterOption}
              onClick={() => setFilter(filterOption as any)}
              className={`px-3 py-1 rounded-full text-xs font-medium capitalize ${
                filter === filterOption
                  ? 'bg-blue-100 text-blue-800'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {filterOption}
            </button>
          ))}
        </div>
      </div>
      
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {filteredNews.map((item) => (
          <div
            key={item.id}
            className={`p-3 rounded-lg border ${getImpactColor(item.impact)}`}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center space-x-2">
                <span className="text-lg">{getCategoryIcon(item.category)}</span>
                <span className="text-xs font-medium text-gray-500 uppercase">
                  {item.category}
                </span>
              </div>
              <span className="text-xs text-gray-400">{item.timestamp}</span>
            </div>
            
            <h4 className="font-medium text-sm mb-1 text-gray-900">
              {item.title}
            </h4>
            
            <p className="text-xs text-gray-600 mb-2">
              {item.summary}
            </p>
            
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-500">{item.source}</span>
              <span className={`text-xs px-2 py-1 rounded-full ${
                item.impact === 'positive' ? 'bg-green-100 text-green-700' :
                item.impact === 'negative' ? 'bg-red-100 text-red-700' :
                'bg-gray-100 text-gray-700'
              }`}>
                {item.impact}
              </span>
            </div>
          </div>
        ))}
      </div>
      
      {filteredNews.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <p>No news items found for the selected filter.</p>
        </div>
      )}
    </div>
  );
};

export default NewsFeedWidget;
