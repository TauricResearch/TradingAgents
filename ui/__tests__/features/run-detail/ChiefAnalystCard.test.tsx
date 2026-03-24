import { render, screen } from '@testing-library/react'
import ChiefAnalystCard from '@/features/run-detail/components/ChiefAnalystCard'
import type { ChiefAnalystReport } from '@/lib/types/agents'

// react-to-pdf uses browser APIs not available in Jest — mock it
jest.mock('react-to-pdf', () => ({
  usePDF: () => ({ toPDF: jest.fn(), targetRef: { current: null } }),
}))

const mockReport: ChiefAnalystReport = {
  verdict:   'BUY',
  catalyst:  'Strong Q4 earnings beat with record margins',
  execution: 'Enter at market price, stop loss at $180',
  tail_risk: 'Federal Reserve rate hike could compress multiples',
}

test('shows pending state when status is pending and report is null', () => {
  render(<ChiefAnalystCard report={null} status="pending" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByText(/standing by/i)).toBeInTheDocument()
})

test('shows running skeleton when status is running', () => {
  render(<ChiefAnalystCard report={null} status="running" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByTestId('chief-analyst-card')).toBeInTheDocument()
})

test('shows verdict when status is done and report is provided', () => {
  render(<ChiefAnalystCard report={mockReport} status="done" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByText('BUY')).toBeInTheDocument()
})

test('shows catalyst when done', () => {
  render(<ChiefAnalystCard report={mockReport} status="done" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByText(/Strong Q4 earnings beat/i)).toBeInTheDocument()
})

test('shows execution when done', () => {
  render(<ChiefAnalystCard report={mockReport} status="done" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByText(/Enter at market price/i)).toBeInTheDocument()
})

test('shows tail_risk when done', () => {
  render(<ChiefAnalystCard report={mockReport} status="done" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByText(/Federal Reserve rate hike/i)).toBeInTheDocument()
})

test('shows download button when done', () => {
  render(<ChiefAnalystCard report={mockReport} status="done" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument()
})

test('shows report-unavailable fallback when done but report is null', () => {
  render(<ChiefAnalystCard report={null} status="done" ticker="AAPL" date="2024-01-15" />)
  expect(screen.getByText(/report unavailable/i)).toBeInTheDocument()
})
