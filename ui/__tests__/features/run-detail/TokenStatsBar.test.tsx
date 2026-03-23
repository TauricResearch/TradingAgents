import { render, screen } from '@testing-library/react'
import TokenStatsBar from '@/features/run-detail/components/TokenStatsBar'

test('renders nothing when both token counts are zero', () => {
  const { container } = render(
    <TokenStatsBar tokensTotal={{ in: 0, out: 0 }} status="running" />
  )
  expect(container.firstChild).toBeNull()
})

test('renders total, input, output when tokens are non-zero', () => {
  render(
    <TokenStatsBar tokensTotal={{ in: 3100, out: 1100 }} status="running" />
  )
  // Total = 3100 + 1100 = 4200 → "4.2k"
  expect(screen.getByText('4.2k')).toBeInTheDocument()
  // Input → "3.1k"
  expect(screen.getByText('3.1k')).toBeInTheDocument()
  // Output → "1.1k"
  expect(screen.getByText('1.1k')).toBeInTheDocument()
})

test('formats values below 1000 without k suffix', () => {
  render(
    <TokenStatsBar tokensTotal={{ in: 800, out: 150 }} status="complete" />
  )
  expect(screen.getByText('950')).toBeInTheDocument()  // total
  expect(screen.getByText('800')).toBeInTheDocument()  // input
  expect(screen.getByText('150')).toBeInTheDocument()  // output
})
