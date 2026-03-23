import { render, screen } from '@testing-library/react'
import RunHistoryTable from '@/features/history/components/RunHistoryTable'

const runs = [
  { id: 'abc', ticker: 'NVDA', date: '2024-05-10', status: 'complete' as const,
    decision: 'BUY' as const, created_at: '2026-03-23T09:00:00' },
  { id: 'def', ticker: 'AAPL', date: '2024-05-09', status: 'complete' as const,
    decision: 'HOLD' as const, created_at: '2026-03-22T16:00:00' },
]

test('renders ticker and decision for each run', () => {
  render(<RunHistoryTable runs={runs} />)
  expect(screen.getByText('NVDA')).toBeInTheDocument()
  expect(screen.getByText('BUY')).toBeInTheDocument()
  expect(screen.getByText('AAPL')).toBeInTheDocument()
  expect(screen.getByText('HOLD')).toBeInTheDocument()
})

test('renders View Report links for each run', () => {
  render(<RunHistoryTable runs={runs} />)
  const links = screen.getAllByText('View Report →')
  expect(links).toHaveLength(2)
  expect(links[0].closest('a')).toHaveAttribute('href', '/runs/abc')
})
