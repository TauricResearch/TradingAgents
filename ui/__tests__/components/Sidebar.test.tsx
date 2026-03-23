import { render, screen } from '@testing-library/react'
import Sidebar from '@/components/Sidebar'

jest.mock('next/navigation', () => ({
  usePathname: () => '/new-run',
}))

test('renders all nav links', () => {
  render(<Sidebar />)
  expect(screen.getByText('New Run')).toBeInTheDocument()
  expect(screen.getByText('History')).toBeInTheDocument()
  expect(screen.getByText('Settings')).toBeInTheDocument()
})

test('marks active link for current path', () => {
  render(<Sidebar />)
  const newRunLink = screen.getByText('New Run').closest('a')
  // Active link has vault primary colour class
  expect(newRunLink?.className).toContain('text-[#adc6ff]')
})
