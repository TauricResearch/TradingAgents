import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Overview from '../dashboard/Overview';
import AgentMonitor from '../dashboard/AgentMonitor';
import TradeHistory from '../dashboard/TradeHistory';
import LogConsole from '../dashboard/LogConsole';
import Analytics from '../dashboard/Analytics';
import { generateMockData } from '../utils/mockData';

// Helper to wrap components with Router
const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('Dashboard UI Tests', () => {
  describe('generateMockData', () => {
    it('should generate mock data with all required fields', () => {
      const data = generateMockData();
      
      expect(data).toHaveProperty('agents');
      expect(data).toHaveProperty('trades');
      expect(data).toHaveProperty('performanceData');
      expect(data).toHaveProperty('logs');
      
      expect(Array.isArray(data.agents)).toBe(true);
      expect(Array.isArray(data.trades)).toBe(true);
      expect(Array.isArray(data.performanceData)).toBe(true);
      expect(Array.isArray(data.logs)).toBe(true);
    });

    it('should generate 12 agents matching TradingAgents architecture', () => {
      const data = generateMockData();
      expect(data.agents.length).toBe(12);
    });

    it('should generate trades with required properties', () => {
      const data = generateMockData();
      const trade = data.trades[0];
      
      expect(trade).toHaveProperty('id');
      expect(trade).toHaveProperty('ticker');
      expect(trade).toHaveProperty('date');
      expect(trade).toHaveProperty('rating');
      expect(trade).toHaveProperty('price');
      expect(trade).toHaveProperty('confidence');
    });
  });

  describe('Overview Component', () => {
    it('should render Overview component', () => {
      renderWithRouter(<Overview />);
      expect(screen.getByText(/TradingAgents Overview/i)).toBeInTheDocument();
    });

    it('should display metrics grid', async () => {
      renderWithRouter(<Overview />);
      // Wait for data to load
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(screen.getByText(/Active Agents/i)).toBeInTheDocument();
      expect(screen.getByText(/Total Trades/i)).toBeInTheDocument();
    });
  });

  describe('AgentMonitor Component', () => {
    it('should render AgentMonitor component', () => {
      renderWithRouter(<AgentMonitor />);
      expect(screen.getByText(/Agent Monitor/i)).toBeInTheDocument();
    });

    it('should display all 12 agents', async () => {
      renderWithRouter(<AgentMonitor />);
      await new Promise(resolve => setTimeout(resolve, 100));
      const agentCards = document.querySelectorAll('.card');
      expect(agentCards.length).toBeGreaterThan(0);
    });
  });

  describe('TradeHistory Component', () => {
    it('should render TradeHistory component', () => {
      renderWithRouter(<TradeHistory />);
      expect(screen.getByText(/Trade History/i)).toBeInTheDocument();
    });

    it('should display trade table with headers', async () => {
      renderWithRouter(<TradeHistory />);
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(screen.getByText(/Ticker/i)).toBeInTheDocument();
      expect(screen.getByText(/Rating/i)).toBeInTheDocument();
      expect(screen.getByText(/Confidence/i)).toBeInTheDocument();
    });
  });

  describe('LogConsole Component', () => {
    it('should render LogConsole component', () => {
      renderWithRouter(<LogConsole />);
      expect(screen.getByText(/System Logs/i)).toBeInTheDocument();
    });

    it('should display log filtering controls', async () => {
      renderWithRouter(<LogConsole />);
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(screen.getByPlaceholderText(/Search logs/i)).toBeInTheDocument();
    });
  });

  describe('Analytics Component', () => {
    it('should render Analytics component', () => {
      renderWithRouter(<Analytics />);
      expect(screen.getByText(/Analytics/i)).toBeInTheDocument();
    });

    it('should display rating distribution chart', async () => {
      renderWithRouter(<Analytics />);
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(screen.getByText(/Rating Distribution/i)).toBeInTheDocument();
    });
  });
});
