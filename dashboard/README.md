# TradingAgents Dashboard

A modern React-based dashboard for monitoring the TradingAgents multi-agent LLM financial trading framework.

## Features

### 📊 **Overview Dashboard**
- Real-time metrics display (active agents, total trades, confidence scores)
- Portfolio performance vs benchmark chart
- Agent status summary
- Recent trade decisions table

### 👥 **Agent Monitor**
- Live monitoring of all 12 specialized LLM agents
- Phase-based filtering (Analysis, Debate, Planning, Risk, Decision)
- Agent latency and token usage statistics
- Architecture documentation integrated

### 💼 **Trade History**
- Complete trade decision history
- Filter by rating (Buy, Overweight, Hold, Sell)
- Confidence score visualization
- Detailed trade information

### 📝 **Log Console**
- Real-time log streaming
- Multi-level filtering (INFO, WARNING, ERROR, SUCCESS)
- Search functionality
- Log statistics dashboard

### 📈 **Analytics**
- Rating distribution pie chart
- Agent activity bar charts
- Confidence score analysis
- Performance metrics

## Architecture Alignment

The dashboard is designed to reflect the TradingAgents architecture as described in `ARCHITECTURE.md`:

### Phase Mapping
1. **Phase 1 - Analysis**: Market, Social Media, News, Fundamentals Analysts
2. **Phase 2 - Debate**: Bull/Bear Researchers + Research Manager
3. **Phase 3 - Planning**: Trader agent
4. **Phase 4 - Risk**: Aggressive/Conservative/Neutral Risk Analysts
5. **Phase 5 - Decision**: Portfolio Manager

### Key Metrics Tracked
- Agent status (active, idle, processing)
- Trade ratings (Buy/Overweight/Hold/Underweight/Sell)
- Confidence scores from structured output
- System logs with level-based categorization

## Tech Stack

- **Framework**: React 18 with Vite build system
- **Routing**: React Router DOM
- **Charts**: Recharts
- **Icons**: Lucide React
- **Testing**: Vitest + React Testing Library
- **Styling**: Custom CSS with responsive design

## Installation

```bash
cd dashboard
npm install
```

## Development

```bash
# Start development server
npm run dev

# Run tests
npm test

# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
dashboard/
├── src/
│   ├── dashboard/          # Main dashboard components
│   │   ├── Overview.jsx
│   │   ├── AgentMonitor.jsx
│   │   ├── TradeHistory.jsx
│   │   ├── LogConsole.jsx
│   │   └── Analytics.jsx
│   ├── utils/
│   │   └── mockData.js     # Mock data generator
│   ├── tests/
│   │   ├── setup.js        # Test configuration
│   │   └── Dashboard.test.jsx
│   ├── App.jsx             # Main app with routing
│   ├── main.jsx            # Entry point
│   └── index.css           # Global styles
├── index.html
├── package.json
├── vite.config.js
└── README.md
```

## Responsive Design

The dashboard features a responsive sidebar navigation that adapts to different screen sizes:
- Desktop: Fixed sidebar with full navigation labels
- Mobile: Horizontal scrollable navigation with icons only

## Logging System

The integrated logging system supports:
- **INFO**: General operational messages
- **WARNING**: Potential issues or rate limit warnings
- **ERROR**: Critical errors requiring attention
- **SUCCESS**: Successful operations and completions

## Testing

Comprehensive test suite covering:
- Mock data generation validation
- Component rendering
- UI element presence
- Filtering functionality
- Navigation behavior

Run tests with:
```bash
npm test
```

## Integration with TradingAgents

The dashboard is designed to integrate with the TradingAgents backend via:
- JSON log file monitoring
- REST API endpoints (to be implemented)
- WebSocket connections for real-time updates (future)

## License

MIT
